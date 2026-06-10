from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from provider_organizations.models import (
    AffirmingFeature,
    OrganizationService,
    ProviderFeature,
    ProviderLocation,
    ProviderOrganization,
    Service,
)
from provider_organizations.scrapers.lgbtq_healthcare_directory import (
    DirectoryScrapeError,
    scrape_providers,
    write_csv,
    write_json,
)


class Command(BaseCommand):
    help = (
        "Scrape provider records from lgbtqhealthcaredirectory.org and export "
        "them as JSON and/or CSV."
    )

    def add_arguments(self, parser):
        range_group = parser.add_mutually_exclusive_group()
        range_group.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Number of records to scrape (default: 100).",
        )
        range_group.add_argument(
            "--range",
            dest="provider_range",
            help=(
                "One-based inclusive record range, for example 1-1000 or "
                "1001-2000."
            ),
        )
        parser.add_argument(
            "--output-dir",
            default="data",
            help="Directory for exported files (default: data).",
        )
        parser.add_argument(
            "--format",
            choices=("both", "json", "csv"),
            default="both",
            help="Export format (default: both).",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=30,
            help="HTTP timeout in seconds (default: 30).",
        )
        parser.add_argument(
            "--retries",
            type=int,
            default=3,
            help=(
                "Retries per failed HTTP request using exponential backoff "
                "(default: 3)."
            ),
        )
        parser.add_argument(
            "--import-db",
            action="store_true",
            help="Import the schema-shaped records into the Django database.",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help=(
                "Update matching organizations and replace their scraped "
                "locations, services, and features. Requires --import-db."
            ),
        )

    def _resolve_range(self, options):
        provider_range = options["provider_range"]
        if not provider_range:
            limit = options["limit"] if options["limit"] is not None else 100
            if limit < 1:
                raise CommandError("--limit must be at least 1.")
            return 1, limit

        try:
            start_text, end_text = provider_range.split("-", 1)
            start = int(start_text.strip())
            end = int(end_text.strip())
        except (AttributeError, TypeError, ValueError) as exc:
            raise CommandError(
                "--range must use START-END, for example 1001-2000."
            ) from exc
        if start < 1:
            raise CommandError("--range START must be at least 1.")
        if end < start:
            raise CommandError(
                "--range END must be greater than or equal to START."
            )
        return start, end

    @transaction.atomic
    def _import_records(self, records, update_existing=False):
        counts = {
            "organizations_created": 0,
            "organizations_updated": 0,
            "organizations_skipped": 0,
            "locations": 0,
            "services": 0,
            "features": 0,
        }
        for record in records:
            organization_data = record["ProviderOrganization"]
            organization, created = ProviderOrganization.objects.get_or_create(
                name=organization_data["name"],
                defaults=organization_data,
            )
            if created:
                counts["organizations_created"] += 1
            elif not update_existing:
                counts["organizations_skipped"] += 1
                continue
            else:
                for field, value in organization_data.items():
                    setattr(organization, field, value)
                organization.save()
                organization.locations.all().delete()
                organization.services.all().delete()
                organization.affirming_features.all().delete()
                counts["organizations_updated"] += 1

            for location_data in record["ProviderLocation"]:
                ProviderLocation.objects.create(
                    organization=organization,
                    **location_data,
                )
                counts["locations"] += 1

            for service_data in record["OrganizationService"]:
                service, _ = Service.objects.get_or_create(
                    name=service_data["service"]
                )
                OrganizationService.objects.create(
                    organization=organization,
                    service=service,
                    delivery_mode=service_data["delivery_mode"],
                    age_group=service_data["age_group"],
                    note=service_data["note"],
                )
                counts["services"] += 1

            for feature_data in record["ProviderFeature"]:
                feature, _ = AffirmingFeature.objects.get_or_create(
                    label=feature_data["feature"],
                    defaults={
                        "description": feature_data["feature_description"]
                    },
                )
                ProviderFeature.objects.create(
                    provider=organization,
                    feature=feature,
                    value=feature_data["value"],
                    evidence_note=feature_data["evidence_note"],
                    source_url=feature_data["source_url"],
                    verified_at=feature_data["verified_at"],
                )
                counts["features"] += 1
        return counts

    def handle(self, *args, **options):
        start, end = self._resolve_range(options)
        limit = end - start + 1
        if options["retries"] < 0:
            raise CommandError("--retries cannot be negative.")
        if options["update_existing"] and not options["import_db"]:
            raise CommandError("--update-existing requires --import-db.")

        self.stdout.write(f"Scraping directory records {start}-{end}...")
        try:
            records = scrape_providers(
                limit=limit,
                timeout=options["timeout"],
                start=start,
                retries=options["retries"],
            )
        except (DirectoryScrapeError, ValueError) as exc:
            raise CommandError(str(exc)) from exc

        output_dir = Path(options["output_dir"])
        base_name = (
            f"lgbtq_healthcare_directory_schema_{start}_{end}"
            if options["provider_range"]
            else f"lgbtq_healthcare_directory_schema_first_{limit}"
        )
        created_files = []
        if options["format"] in ("both", "json"):
            created_files.append(
                write_json(records, output_dir / f"{base_name}.json")
            )
        if options["format"] in ("both", "csv"):
            created_files.append(
                write_csv(records, output_dir / f"{base_name}.csv")
            )

        import_summary = ""
        if options["import_db"]:
            counts = self._import_records(
                records,
                update_existing=options["update_existing"],
            )
            import_summary = (
                " Database import: "
                f"{counts['organizations_created']} created, "
                f"{counts['organizations_updated']} updated, "
                f"{counts['organizations_skipped']} skipped, "
                f"{counts['locations']} locations, "
                f"{counts['services']} services, "
                f"{counts['features']} features."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Scraped {len(records)} records: "
                + ", ".join(str(path) for path in created_files)
                + import_summary
            )
        )

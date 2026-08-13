import csv
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from provider_organizations.models import (
    OrganizationService,
    ProviderOrganization,
    Service,
)


class Command(BaseCommand):
    help = "Import provider organizations from a CSV file safely without duplicates."

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_file",
            type=str,
            help="Path to the provider CSV file.",
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and preview the import without saving anything.",
        )

    def parse_date(self, value):
        if not value:
            return None

        try:
            parsed = datetime.strptime(value.strip(), "%Y-%m-%d")
            return timezone.make_aware(parsed)
        except ValueError:
            return None

    def determine_org_type(self, resource_type, name):
        text = f"{resource_type} {name}".lower()

        if "telehealth" in text:
            return "telehealth"

        if "nonprofit" in text or "community organization" in text:
            return "nonprofit"

        if "hospital" in text or "medical center" in text or "health system" in text:
            return "hospital_program"

        if "private practice" in text:
            return "private_practice"

        return "clinic"

    def determine_delivery_mode(self, service_name):
        text = service_name.lower()

        if "telehealth" in text or "virtual" in text:
            return "telehealth"

        return "in_person"

    def determine_age_group(self, population):
        text = (population or "").lower()

        if any(word in text for word in ["youth", "adolescent", "pediatric", "teen"]):
            return "youth"

        if "adult" in text and not any(
            word in text for word in ["youth", "adolescent", "pediatric"]
        ):
            return "adult"

        return "all"

    def find_existing_organization(self, name, website):
        if website:
            existing = ProviderOrganization.objects.filter(
                website_url__iexact=website
            ).first()

            if existing:
                return existing

        return ProviderOrganization.objects.filter(
            name__iexact=name
        ).first()

    @transaction.atomic
    def handle(self, *args, **options):
        csv_file = options["csv_file"]
        dry_run = options["dry_run"]

        created_orgs = 0
        existing_orgs = 0
        created_services = 0
        created_org_services = 0
        skipped_rows = 0

        try:
            handle = open(csv_file, "r", encoding="utf-8-sig", newline="")
        except FileNotFoundError:
            raise CommandError(f"CSV file not found: {csv_file}")

        with handle:
            reader = csv.DictReader(handle)

            required_columns = {
                "organization_name",
                "website",
                "services",
            }

            missing = required_columns - set(reader.fieldnames or [])

            if missing:
                raise CommandError(
                    "CSV is missing required columns: "
                    + ", ".join(sorted(missing))
                )

            for row_number, row in enumerate(reader, start=2):
                name = (row.get("organization_name") or "").strip()
                website = (row.get("website") or "").strip() or None
                resource_type = (row.get("resource_type") or "").strip()
                services_text = (row.get("services") or "").strip()
                population = (row.get("population") or "").strip()
                source_url = (row.get("source_url") or "").strip()
                source_type = (row.get("source_type") or "").strip()
                verification_status = (
                    row.get("verification_status") or ""
                ).strip()
                notes = (row.get("notes") or "").strip()
                last_checked = (row.get("last_checked") or "").strip()

                if not name:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Row {row_number}: skipped because organization_name is blank."
                        )
                    )
                    skipped_rows += 1
                    continue

                description_parts = []

                if notes:
                    description_parts.append(notes)

                if source_type:
                    description_parts.append(f"Source: {source_type}")

                if verification_status:
                    description_parts.append(
                        f"Verification status: {verification_status}"
                    )

                if source_url:
                    description_parts.append(f"Source URL: {source_url}")

                description = "\n\n".join(description_parts)

                existing = self.find_existing_organization(name, website)

                if existing:
                    organization = existing
                    existing_orgs += 1

                    self.stdout.write(
                        f"EXISTS: {organization.name}"
                    )

                else:
                    organization = ProviderOrganization(
                        name=name,
                        org_type=self.determine_org_type(
                            resource_type,
                            name,
                        ),
                        description=description,
                        website_url=website,
                        is_active=True,
                        last_verified_at=self.parse_date(last_checked),
                    )

                    if not dry_run:
                        organization.save()

                    created_orgs += 1

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"NEW: {name}"
                        )
                    )

                if not services_text:
                    continue

                service_names = [
                    value.strip()
                    for value in services_text.split(";")
                    if value.strip()
                ]

                for service_name in service_names:
                    if dry_run:
                        service = Service.objects.filter(
                            name__iexact=service_name
                        ).first()

                        if service is None:
                            created_services += 1

                        continue

                    service = Service.objects.filter(
                        name__iexact=service_name
                    ).first()

                    if service is None:
                        service = Service.objects.create(
                            name=service_name
                        )
                        created_services += 1

                    _, created = OrganizationService.objects.get_or_create(
                        organization=organization,
                        service=service,
                        defaults={
                            "delivery_mode": self.determine_delivery_mode(
                                service_name
                            ),
                            "age_group": self.determine_age_group(
                                population
                            ),
                            "note": notes,
                        },
                    )

                    if created:
                        created_org_services += 1

        if dry_run:
            transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "Import preview complete."
                if dry_run
                else "Import complete."
            )
        )

        self.stdout.write(
            f"New organizations: {created_orgs}"
        )
        self.stdout.write(
            f"Existing organizations: {existing_orgs}"
        )
        self.stdout.write(
            f"New services: {created_services}"
        )
        self.stdout.write(
            f"New organization-service links: {created_org_services}"
        )
        self.stdout.write(
            f"Skipped rows: {skipped_rows}"
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "DRY RUN: No database changes were saved."
                )
            
                )

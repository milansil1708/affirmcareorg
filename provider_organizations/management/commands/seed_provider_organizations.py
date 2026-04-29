from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.dateparse import parse_datetime

from provider_organizations.models import (
    AffirmingFeature,
    OrganizationService,
    ProviderFeature,
    ProviderLocation,
    ProviderOrganization,
    Service,
)
from provider_organizations.seed_data import SEED_DATA


class Command(BaseCommand):
    help = (
        "Seed provider organization demo data without creating duplicates. "
        "Safe to run multiple times."
    )

    def _parse_dt(self, value):
        if not value:
            return None
        return parse_datetime(value)

    @transaction.atomic
    def handle(self, *args, **options):
        created_counts = {
            "ProviderOrganization": 0,
            "ProviderLocation": 0,
            "Service": 0,
            "OrganizationService": 0,
            "AffirmingFeature": 0,
            "ProviderFeature": 0,
        }

        organizations = {}
        for item in SEED_DATA.get("ProviderOrganization", []):
            defaults = {
                "org_type": item["org_type"],
                "description": item["description"],
                "website_url": item.get("website_url"),
                "booking_url": item.get("booking_url"),
                "phone": item["phone"],
                "email": item["email"],
                "is_active": item.get("is_active", True),
                "last_verified_at": self._parse_dt(item.get("last_verified_at")),
            }
            obj, created = ProviderOrganization.objects.get_or_create(
                name=item["name"],
                defaults=defaults,
            )
            if created:
                created_counts["ProviderOrganization"] += 1
            organizations[item["name"]] = obj

        services = {}
        for item in SEED_DATA.get("Service", []):
            obj, created = Service.objects.get_or_create(name=item["name"])
            if created:
                created_counts["Service"] += 1
            services[item["name"]] = obj

        features = {}
        for item in SEED_DATA.get("AffirmingFeature", []):
            obj, created = AffirmingFeature.objects.get_or_create(
                label=item["label"],
                defaults={"description": item["description"]},
            )
            if created:
                created_counts["AffirmingFeature"] += 1
            features[item["label"]] = obj

        for item in SEED_DATA.get("ProviderLocation", []):
            org = organizations[item["organization"]]
            _, created = ProviderLocation.objects.get_or_create(
                organization=org,
                address_line1=item["address_line1"],
                city=item["city"],
                state_code=item["state_code"],
                zip_code=item["zip_code"],
                defaults={
                    "address_line2": item.get("address_line2") or None,
                    "latitude": item.get("latitude"),
                    "longitude": item.get("longitude"),
                    "is_primary": item.get("is_primary", False),
                    "wheelchair_accessible": item.get("wheelchair_accessible", False),
                    "gender_neutral_restrooms": item.get(
                        "gender_neutral_restrooms", False
                    ),
                    "public_transit_notes": item.get("public_transit_notes", False),
                },
            )
            if created:
                created_counts["ProviderLocation"] += 1

        for item in SEED_DATA.get("OrganizationService", []):
            org = organizations[item["organization"]]
            service = services[item["service"]]
            _, created = OrganizationService.objects.get_or_create(
                organization=org,
                service=service,
                delivery_mode=item["delivery_mode"],
                age_group=item["age_group"],
                defaults={"note": item.get("note", "")},
            )
            if created:
                created_counts["OrganizationService"] += 1

        for item in SEED_DATA.get("ProviderFeature", []):
            org = organizations[item["provider"]]
            feature = features[item["feature"]]
            _, created = ProviderFeature.objects.get_or_create(
                provider=org,
                feature=feature,
                defaults={
                    "value": item.get("value", "unknown"),
                    "evidence_note": item.get("evidence_note", ""),
                    "source_url": item.get("source_url") or None,
                    "verified_at": self._parse_dt(item.get("verified_at")),
                },
            )
            if created:
                created_counts["ProviderFeature"] += 1

        summary = ", ".join(
            f"{model}: {count} created" for model, count in created_counts.items()
        )
        self.stdout.write(self.style.SUCCESS(f"Seed complete. {summary}."))

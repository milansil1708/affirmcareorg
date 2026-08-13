from django.core.management.base import BaseCommand
from django.db import transaction

from provider_organizations.models import (
    ProviderLocation,
    ProviderOrganization,
)


LOCATIONS = {
    "JFK University Medical Center": [
        {
            "address_line1": "65 James Street",
            "address_line2": "",
            "city": "Edison",
            "state_code": "NJ",
            "zip_code": "08820",
        },
    ],

    "Rutgers Center for Transgender Health": [
        {
            "address_line1": "185 South Orange Avenue",
            "address_line2": "",
            "city": "Newark",
            "state_code": "NJ",
            "zip_code": "07103",
        },
    ],

    "VNACJ Community Health Center — LGBTQ Center for Health & Wellness": [
        {
            "address_line1": "1301 Main Street",
            "address_line2": "",
            "city": "Asbury Park",
            "state_code": "NJ",
            "zip_code": "07712",
        },
    ],

    "Penn State Health Internal Medicine": [
        {
            "address_line1": "2626 N Third St",
            "address_line2": "",
            "city": "Harrisburg",
            "state_code": "PA",
            "zip_code": "17110",
        },
        {
            "address_line1": "1150 Cocoa Ave",
            "address_line2": "",
            "city": "Hershey",
            "state_code": "PA",
            "zip_code": "17033",
        },
        {
            "address_line1": "143 Hospital Dr",
            "address_line2": "Suite 207",
            "city": "State College",
            "state_code": "PA",
            "zip_code": "16803",
        },
    ],
}


class Command(BaseCommand):
    help = "Add manually verified physical locations to selected providers."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without saving.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        added = 0
        removed_blank = 0
        missing = 0

        for organization_name, locations in LOCATIONS.items():
            organization = ProviderOrganization.objects.filter(
                name=organization_name
            ).first()

            if not organization:
                self.stdout.write(
                    self.style.WARNING(
                        f"MISSING: {organization_name}"
                    )
                )
                missing += 1
                continue

            # Remove only placeholder locations that contain a state
            # but no address, city, or ZIP.
            blanks = ProviderLocation.objects.filter(
                organization=organization,
                address_line1="",
                city="",
                zip_code="",
            )

            blank_count = blanks.count()

            if blank_count:
                self.stdout.write(
                    f"REMOVE BLANK: {organization_name} ({blank_count})"
                )
                blanks.delete()
                removed_blank += blank_count

            for index, location in enumerate(locations):
                obj, created = ProviderLocation.objects.get_or_create(
                    organization=organization,
                    address_line1=location["address_line1"],
                    city=location["city"],
                    state_code=location["state_code"],
                    zip_code=location["zip_code"],
                    defaults={
                        "address_line2": location["address_line2"] or None,
                        "is_primary": index == 0,
                    },
                )

                if created:
                    added += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"ADD: {organization_name} | "
                            f"{location['address_line1']} | "
                            f"{location['city']}, "
                            f"{location['state_code']} "
                            f"{location['zip_code']}"
                        )
                    )

        if dry_run:
            transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "Location enrichment preview complete."
                if dry_run
                else "Location enrichment complete."
            )
        )
        self.stdout.write(f"Physical locations added: {added}")
        self.stdout.write(f"Blank placeholders removed: {removed_blank}")
        self.stdout.write(f"Missing organizations: {missing}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "DRY RUN: No database changes were saved."
                )
            )

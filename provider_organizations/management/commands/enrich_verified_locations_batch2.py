from django.core.management.base import BaseCommand
from django.db import transaction

from provider_organizations.models import (
    ProviderLocation,
    ProviderOrganization,
)


LOCATIONS = {
    "Planned Parenthood Arizona": [
        ("4751 N 15th Street", "#3", "Phoenix", "AZ", "85014"),
        ("5771 W Eugie Avenue", "", "Glendale", "AZ", "85304"),
        ("2255 N Wyatt Dr", "", "Tucson", "AZ", "85712"),
    ],

    "Planned Parenthood of Maryland": [
        ("929 West St", "Suite 200", "Annapolis", "MD", "21401"),
        ("330 N Howard Street", "", "Baltimore", "MD", "21201"),
        ("8579 Commerce Drive", "Suite 102", "Easton", "MD", "21601"),
        ("170 Thomas Johnson Drive", "Suite 100", "Frederick", "MD", "21702"),
        ("1866 Reisterstown Road", "Suite D", "Pikesville", "MD", "21208"),
        ("8501 LaSalle Road", "Suite 309", "Towson", "MD", "21286"),
        ("3975 St. Charles Parkway", "", "Waldorf", "MD", "20602"),
    ],
}


class Command(BaseCommand):
    help = "Add second batch of verified provider locations."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        added = 0
        removed = 0
        missing = 0

        for name, locations in LOCATIONS.items():
            organization = ProviderOrganization.objects.filter(
                name=name
            ).first()

            if not organization:
                self.stdout.write(f"MISSING: {name}")
                missing += 1
                continue

            blanks = ProviderLocation.objects.filter(
                organization=organization,
                address_line1="",
                city="",
                zip_code="",
            )

            count = blanks.count()

            if count:
                self.stdout.write(
                    f"REMOVE BLANK: {name} ({count})"
                )
                blanks.delete()
                removed += count

            for index, (
                address1,
                address2,
                city,
                state,
                zipcode,
            ) in enumerate(locations):

                _, created = ProviderLocation.objects.get_or_create(
                    organization=organization,
                    address_line1=address1,
                    city=city,
                    state_code=state,
                    zip_code=zipcode,
                    defaults={
                        "address_line2": address2 or None,
                        "is_primary": index == 0,
                    },
                )

                if created:
                    added += 1
                    self.stdout.write(
                        f"ADD: {name} | {city}, {state}"
                    )

        if dry_run:
            transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(
            "Batch 2 preview complete."
            if dry_run
            else "Batch 2 enrichment complete."
        )
        self.stdout.write(f"Locations added: {added}")
        self.stdout.write(f"Blank placeholders removed: {removed}")
        self.stdout.write(f"Missing organizations: {missing}")

        if dry_run:
            self.stdout.write(
                "DRY RUN: No database changes were saved."
            )

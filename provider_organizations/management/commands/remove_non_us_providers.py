from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from provider_organizations.models import ProviderLocation, ProviderOrganization


US_STATES_AND_DC = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DISTRICT OF COLUMBIA", "WASHINGTON DC", "WASHINGTON, DC", "DC",
}


class Command(BaseCommand):
    help = "List stored state codes and remove providers with non-U.S. locations."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without deleting anything.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip the deletion confirmation prompt.",
        )

    def handle(self, *args, **options):
        locations = ProviderLocation.objects.values_list("state_code", flat=True)
        state_counts = Counter((state or "<blank>").strip() for state in locations)

        self.stdout.write("Stored state_code values:")
        for state, count in sorted(state_counts.items(), key=lambda item: item[0].upper()):
            self.stdout.write(f"  {state}: {count} location(s)")

        non_us_states = {
            state for state in state_counts if self.normalize(state) not in US_STATES_AND_DC
        }
        non_us_location_filter = {
            "locations__state_code__in": list(non_us_states)
        }
        organizations = ProviderOrganization.objects.filter(
            **non_us_location_filter
        ).values_list("id", flat=True).distinct()
        organization_ids = list(organizations)

        self.stdout.write(
            self.style.WARNING(
                f"Non-U.S./unrecognized state_code values: {sorted(non_us_states)}"
            )
        )
        self.stdout.write(
            f"Providers with at least one such location: {len(organization_ids)}"
        )

        if options["dry_run"] or not organization_ids:
            return

        if not options["yes"]:
            answer = input("Delete these providers and all related records? [y/N] ")
            if answer.strip().lower() not in {"y", "yes"}:
                self.stdout.write("Deletion cancelled.")
                return

        with transaction.atomic():
            deleted_count, _ = ProviderOrganization.objects.filter(
                id__in=organization_ids
            ).delete()

        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted_count} database records."))

    @staticmethod
    def normalize(value):
        return " ".join((value or "").upper().replace(".", "").split())

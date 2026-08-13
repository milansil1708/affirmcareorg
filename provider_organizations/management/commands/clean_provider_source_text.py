import re

from django.core.management.base import BaseCommand
from django.db import transaction

from provider_organizations.models import ProviderOrganization


SOURCE_RE = re.compile(
    r"Source URL:\s*(https?://\S+)",
    re.IGNORECASE,
)


class Command(BaseCommand):
    help = "Replace imported provider boilerplate with a simple Source: URL line."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without saving them.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        changed = 0

        providers = ProviderOrganization.objects.filter(
            description__icontains="Source URL:"
        )

        for provider in providers:
            match = SOURCE_RE.search(provider.description or "")
            if not match:
                continue

            source_url = match.group(1).rstrip(".,)")
            new_description = f"Source: {source_url}"

            if provider.description == new_description:
                continue

            self.stdout.write(
                f"{provider.name}\n"
                f"  -> {new_description}"
            )

            provider.description = new_description
            provider.save(update_fields=["description"])
            changed += 1

        if dry_run:
            transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"{'Preview' if dry_run else 'Cleanup'} complete. "
                f"{changed} provider descriptions changed."
            )
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "DRY RUN: No database changes were saved."
                )
            )

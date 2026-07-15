import re

from django.core.management.base import BaseCommand
from django.db import transaction

from provider_organizations.models import Service


# These terms identify services directly related to transgender care.
TRANS_SERVICE_TERMS = (
    "gender",
    "hormone",
    "hrt",
    "transition",
    "transgender",
    "transsexual",
    "voice therapy",
    "voice training",
    "chest reconstruction",
    "breast augmentation",
    "gender affirming",
    "gender-affirming",
    "neovaginoplasty",
    "phalloplasty",
    "metoidioplasty",
    "hysterectomy",
    "fertility preservation",
    "name and gender change",
)


class Command(BaseCommand):
    help = "Remove Service records that are not directly related to transgender care."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List services that would be deleted without deleting anything.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip the deletion confirmation prompt.",
        )

    def handle(self, *args, **options):
        services = list(Service.objects.order_by("id"))
        removable = [service for service in services if not self.is_trans_service(service.name)]

        self.stdout.write("Services currently stored:")
        for service in services:
            classification = "KEEP" if service not in removable else "DELETE"
            self.stdout.write(f"  [{classification}] {service.id}: {service.name}")

        self.stdout.write(
            self.style.WARNING(
                f"Services to delete: {len(removable)} of {len(services)}"
            )
        )

        if options["dry_run"] or not removable:
            return

        if not options["yes"]:
            answer = input("Delete these services and their related records? [y/N] ")
            if answer.strip().lower() not in {"y", "yes"}:
                self.stdout.write("Deletion cancelled.")
                return

        with transaction.atomic():
            deleted_count, _ = Service.objects.filter(
                id__in=[service.id for service in removable]
            ).delete()

        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted_count} database records."))

    @staticmethod
    def is_trans_service(name):
        normalized = re.sub(r"[^a-z0-9]+", " ", name.casefold()).strip()
        return any(term in normalized for term in TRANS_SERVICE_TERMS)

from django.core.management.base import BaseCommand
from django.db import transaction

from provider_organizations.models import OrganizationService, Service


CANONICAL_GROUPS = {
    "Primary Care": [
        "Primary Care",
        "Gender-affirming primary care",
        "Gender-affirming primary/consultative care",
        "Transgender primary care",
        "LGBTQ+ primary care",
        "LGBTQ-affirming primary care",
    ],

    "Hormone Therapy": [
        "Hormone Therapy",
        "Gender-affirming hormone therapy",
        "Gender-affirming hormone care",
        "Estrogen and testosterone hormone therapy",
        "Hormonal care",
        "Hormone replacement therapy",
        "Hormone treatment",
        "Transgender/nonbinary hormone therapy",
        "Hormone therapy for eligible patients",
    ],

    "HRT Follow-Up Care": [
        "HRT Follow-Up Care",
        "Ongoing monitoring",
    ],

    "Mental Health Counseling": [
        "Mental Health Counseling",
        "Mental health",
        "Mental health support",
        "Mental health coordination",
        "Behavioral health",
        "Counseling",
    ],

    "Gender-Affirming Care": [
        "Gender-Affirming Care",
        "Gender-affirming care services",
        "Gender-affirming health services",
        "Gender-affirming medicine",
        "Gender & Life-Affirming Medicine",
        "Gender care",
        "Gender health",
        "Gender health services",
        "Gender wellness care",
        "Integrated transgender care",
        "Multidisciplinary gender care",
        "Multidisciplinary transgender health care",
        "Multispecialty gender care",
        "Trans and gender diverse health",
        "Transgender health",
        "Transgender health services",
        "Medical Transitioning Care",
    ],

    "Youth Gender Care": [
        "Youth Gender Care",
        "Child and adolescent gender care",
        "Pediatric and adolescent gender care",
        "Pediatric gender care",
        "Pediatric gender wellness",
        "Gender-focused pediatric care",
        "Gender development care",
        "Gender diversity care",
        "Gender pathway care",
        "Gender and sexual development care",
        "Transyouth health",
    ],

    "Gender-Affirming Surgery": [
        "Gender-affirming surgery",
        "Gender Affirming Surgery",
        "Plastic and reconstructive surgery",
        "Surgical Transitioning Care",
    ],

    "Surgery Consultation": [
        "Surgery Consultation",
        "Surgical assessment",
        "Surgery referrals",
        "Surgery navigation",
        "Surgical navigation",
        "Surgery coordination",
        "Gender-affirming surgery navigation",
    ],

    "Voice Therapy": [
        "Voice Therapy",
        "Voice and specialty services",
    ],

    "Fertility Preservation": [
        "Fertility Preservation",
    ],

    "Care Coordination": [
        "Care Coordination",
        "Case Management",
        "Primary care coordination",
        "Treatment planning",
        "Multidisciplinary care",
    ],

    "Care Navigation": [
        "Care Navigation",
        "Navigation",
        "Patient navigation",
        "Healthcare-navigation leads",
    ],

    "Patient Advocacy": [
        "Patient Advocacy",
        "Advocacy",
    ],

    "Insurance Navigation": [
        "Insurance Navigation",
    ],

    "Sexual and Reproductive Health": [
        "Sexual and Reproductive Health",
        "Sexual health",
        "Sexual/reproductive health",
        "Reproductive and sexual health care",
    ],

    "PrEP and HIV Prevention": [
        "PrEP and HIV Prevention",
        "PrEP",
        "Pre-Exposure Prophylaxis (PrEP)",
        "HIV prevention",
    ],

    "Support Groups & Services": [
        "Support Groups & Services",
        "Support groups",
    ],

    "Telehealth": [
        "Telehealth",
    ],
}


class Command(BaseCommand):
    help = (
        "Merge duplicate provider services into canonical names while "
        "preserving provider-service relationships."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without saving them.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        services_merged = 0
        links_moved = 0
        duplicate_links_removed = 0
        canonical_created = 0
        canonical_renamed = 0

        for canonical_name, aliases in CANONICAL_GROUPS.items():
            aliases_lower = {name.casefold() for name in aliases}
            aliases_lower.add(canonical_name.casefold())

            matching_services = [
                service
                for service in Service.objects.all()
                if service.name.casefold() in aliases_lower
            ]

            if not matching_services:
                continue

            target = next(
                (
                    service
                    for service in matching_services
                    if service.name == canonical_name
                ),
                None,
            )

            if target is None:
                target = matching_services[0]

                old_name = target.name
                target.name = canonical_name
                target.save(update_fields=["name"])

                canonical_renamed += 1
                self.stdout.write(
                    f'RENAME: "{old_name}" -> "{canonical_name}"'
                )

            sources = [
                service
                for service in matching_services
                if service.pk != target.pk
            ]

            for source in sources:
                self.stdout.write(
                    f'MERGE: "{source.name}" -> "{canonical_name}"'
                )

                links = OrganizationService.objects.filter(
                    service=source
                ).select_related("organization")

                for link in links:
                    existing = OrganizationService.objects.filter(
                        organization=link.organization,
                        service=target,
                        delivery_mode=link.delivery_mode,
                        age_group=link.age_group,
                    ).exclude(pk=link.pk).first()

                    if existing:
                        if link.note and link.note not in (existing.note or ""):
                            if existing.note:
                                existing.note = (
                                    existing.note.rstrip()
                                    + "\n\n"
                                    + link.note.strip()
                                )
                            else:
                                existing.note = link.note

                            existing.save(update_fields=["note"])

                        link.delete()
                        duplicate_links_removed += 1

                    else:
                        link.service = target
                        link.save(update_fields=["service"])
                        links_moved += 1

                source.delete()
                services_merged += 1

        if dry_run:
            transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "Service normalization preview complete."
                if dry_run
                else "Service normalization complete."
            )
        )
        self.stdout.write(
            f"Redundant services merged: {services_merged}"
        )
        self.stdout.write(
            f"Provider-service links moved: {links_moved}"
        )
        self.stdout.write(
            f"Duplicate provider-service links removed: {duplicate_links_removed}"
        )
        self.stdout.write(
            f"Canonical names renamed: {canonical_renamed}"
        )
        self.stdout.write(
            f"Canonical services created: {canonical_created}"
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "DRY RUN: No database changes were saved."
                )
            )

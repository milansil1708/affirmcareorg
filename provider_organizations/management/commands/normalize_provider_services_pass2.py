from django.core.management.base import BaseCommand
from django.db import transaction

from provider_organizations.models import OrganizationService, Service


MERGE_GROUPS = {
    "Endocrinology": [
        "Endocrinology",
        "Endocrinologist",
        "endocrinology",
        "endocrine care",
    ],

    "Gender-Affirming Care": [
        "Gender-Affirming Care",
        "adult gender medicine",
        "Gender-affirming adult care",
        "other gender-affirming services",
        "Medical services for transgender/LGBTQIA+ community",
    ],

    "Sexual and Reproductive Health": [
        "Sexual and Reproductive Health",
        "Gender and sexual health",
        "gynecologic care",
    ],

    "Care Navigation": [
        "Care Navigation",
        "referrals",
        "referrals as available",
        "specialty referrals",
        "gender-related care and referrals",
    ],

    "Support Groups & Services": [
        "Support Groups & Services",
        "support",
        "family support",
        "Community resources",
    ],

    "Surgery Consultation": [
        "Surgery Consultation",
        "surgery",
    ],

    "Mental Health Counseling": [
        "Mental Health Counseling",
        "counseling referrals",
    ],
}


RENAME_ONLY = {
    "adolescent care": "Adolescent Care",
    "adolescent medicine": "Adolescent Medicine",
    "gender-related endocrine care": "Gender-Related Endocrine Care",
    "hormone-related specialty care": "Hormone-Related Specialty Care",
    "inclusive care": "Inclusive Care",
    "local LGBTQ+ information": "Local LGBTQ+ Information",
    "pediatric specialty care": "Pediatric Specialty Care",
    "pharmacy": "Pharmacy",
    "prescription management": "Prescription Management",
    "preventive care": "Preventive Care",
    "primary and specialty care": "Primary and Specialty Care",
    "primary-care, mental-health and surgery referrals":
        "Primary Care, Mental Health and Surgery Referrals",
    "specialty care": "Specialty Care",
    "transition-related specialty services":
        "Transition-Related Specialty Services",
    "transition support": "Transition Support",
    "wellness services": "Wellness Services",
    "Pediatric endocrinology": "Pediatric Endocrinology",
    "HIV/STI care": "HIV/STI Care",
    "LGBTQ+ health": "LGBTQ+ Health",
    "LGBTQ+ health services": "LGBTQ+ Health Services",
    "LGBTQ+ supportive care": "LGBTQ+ Supportive Care",
    "Transgender community services": "Transgender Community Services",
}


class Command(BaseCommand):
    help = "Second-pass provider service cleanup and capitalization."

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
        names_renamed = 0

        # Merge obvious duplicates.
        for canonical_name, aliases in MERGE_GROUPS.items():
            aliases_cf = {x.casefold() for x in aliases}
            aliases_cf.add(canonical_name.casefold())

            matches = [
                s for s in Service.objects.all()
                if s.name.casefold() in aliases_cf
            ]

            if not matches:
                continue

            target = next(
                (s for s in matches if s.name == canonical_name),
                None,
            )

            if target is None:
                target = matches[0]
                old_name = target.name
                target.name = canonical_name
                target.save(update_fields=["name"])
                names_renamed += 1
                self.stdout.write(
                    f'RENAME: "{old_name}" -> "{canonical_name}"'
                )

            for source in [s for s in matches if s.pk != target.pk]:
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
                            existing.note = (
                                ((existing.note or "").rstrip() + "\n\n")
                                + link.note.strip()
                            ).strip()
                            existing.save(update_fields=["note"])

                        link.delete()
                        duplicate_links_removed += 1
                    else:
                        link.service = target
                        link.save(update_fields=["service"])
                        links_moved += 1

                source.delete()
                services_merged += 1

        # Capitalization / display-name cleanup only.
        for old_name, new_name in RENAME_ONLY.items():
            service = Service.objects.filter(name=old_name).first()

            if not service:
                continue

            existing = Service.objects.filter(
                name__iexact=new_name
            ).exclude(pk=service.pk).first()

            if existing:
                links = OrganizationService.objects.filter(
                    service=service
                ).select_related("organization")

                for link in links:
                    duplicate = OrganizationService.objects.filter(
                        organization=link.organization,
                        service=existing,
                        delivery_mode=link.delivery_mode,
                        age_group=link.age_group,
                    ).exclude(pk=link.pk).first()

                    if duplicate:
                        link.delete()
                        duplicate_links_removed += 1
                    else:
                        link.service = existing
                        link.save(update_fields=["service"])
                        links_moved += 1

                service.delete()
                services_merged += 1
                self.stdout.write(
                    f'MERGE: "{old_name}" -> "{new_name}"'
                )
            else:
                service.name = new_name
                service.save(update_fields=["name"])
                names_renamed += 1
                self.stdout.write(
                    f'RENAME: "{old_name}" -> "{new_name}"'
                )

        if dry_run:
            transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "Pass 2 preview complete."
                if dry_run
                else "Pass 2 normalization complete."
            )
        )
        self.stdout.write(
            f"Redundant services merged: {services_merged}"
        )
        self.stdout.write(
            f"Provider-service links moved: {links_moved}"
        )
        self.stdout.write(
            f"Duplicate links removed: {duplicate_links_removed}"
        )
        self.stdout.write(
            f"Service names renamed: {names_renamed}"
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "DRY RUN: No database changes were saved."
                )
            )

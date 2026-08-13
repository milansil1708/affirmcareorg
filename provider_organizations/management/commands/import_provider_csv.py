import csv
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from provider_organizations.models import (
    OrganizationService,
    ProviderLocation,
    ProviderOrganization,
    Service,
)


class Command(BaseCommand):
    STATE_CODES = {
        "Alabama": "AL",
        "Alaska": "AK",
        "Arizona": "AZ",
        "Arkansas": "AR",
        "California": "CA",
        "Colorado": "CO",
        "Connecticut": "CT",
        "Delaware": "DE",
        "District of Columbia": "DC",
        "Florida": "FL",
        "Georgia": "GA",
        "Hawaii": "HI",
        "Idaho": "ID",
        "Illinois": "IL",
        "Indiana": "IN",
        "Iowa": "IA",
        "Kansas": "KS",
        "Kentucky": "KY",
        "Louisiana": "LA",
        "Maine": "ME",
        "Maryland": "MD",
        "Massachusetts": "MA",
        "Michigan": "MI",
        "Minnesota": "MN",
        "Mississippi": "MS",
        "Missouri": "MO",
        "Montana": "MT",
        "Nebraska": "NE",
        "Nevada": "NV",
        "New Hampshire": "NH",
        "New Jersey": "NJ",
        "New Mexico": "NM",
        "New York": "NY",
        "North Carolina": "NC",
        "North Dakota": "ND",
        "Ohio": "OH",
        "Oklahoma": "OK",
        "Oregon": "OR",
        "Pennsylvania": "PA",
        "Rhode Island": "RI",
        "South Carolina": "SC",
        "South Dakota": "SD",
        "Tennessee": "TN",
        "Texas": "TX",
        "Utah": "UT",
        "Vermont": "VT",
        "Virginia": "VA",
        "Washington": "WA",
        "West Virginia": "WV",
        "Wisconsin": "WI",
        "Wyoming": "WY",
    }

    def normalize_state(self, value):
        value = (value or "").strip()
        if not value:
            return ""

        if len(value) == 2:
            return value.upper()

        for name, code in self.STATE_CODES.items():
            if value.casefold() == name.casefold():
                return code

        return value

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

    SERVICE_ALIASES = {
        # Primary care
        "primary care": "Primary Care",
        "gender-affirming primary care": "Primary Care",
        "gender-affirming primary/consultative care": "Primary Care",
        "transgender primary care": "Primary Care",
        "lgbtq+ primary care": "Primary Care",
        "lgbtq-affirming primary care": "Primary Care",

        # Hormones
        "hormone therapy": "Hormone Therapy",
        "gender-affirming hormone therapy": "Hormone Therapy",
        "gender-affirming hormone care": "Hormone Therapy",
        "estrogen and testosterone hormone therapy": "Hormone Therapy",
        "hormonal care": "Hormone Therapy",
        "hormone replacement therapy": "Hormone Therapy",
        "hormone treatment": "Hormone Therapy",
        "transgender/nonbinary hormone therapy": "Hormone Therapy",
        "hormone therapy for eligible patients": "Hormone Therapy",
        "hrt follow-up care": "HRT Follow-Up Care",
        "ongoing monitoring": "HRT Follow-Up Care",

        # Broad gender care
        "gender-affirming care": "Gender-Affirming Care",
        "gender-affirming care services": "Gender-Affirming Care",
        "gender-affirming health services": "Gender-Affirming Care",
        "gender-affirming medicine": "Gender-Affirming Care",
        "gender & life-affirming medicine": "Gender-Affirming Care",
        "gender care": "Gender-Affirming Care",
        "gender health": "Gender-Affirming Care",
        "gender health services": "Gender-Affirming Care",
        "gender wellness care": "Gender-Affirming Care",
        "integrated transgender care": "Gender-Affirming Care",
        "multidisciplinary gender care": "Gender-Affirming Care",
        "multidisciplinary transgender health care": "Gender-Affirming Care",
        "multispecialty gender care": "Gender-Affirming Care",
        "trans and gender diverse health": "Gender-Affirming Care",
        "transgender health": "Gender-Affirming Care",
        "transgender health services": "Gender-Affirming Care",
        "medical transitioning care": "Gender-Affirming Care",
        "adult gender medicine": "Gender-Affirming Care",
        "gender-affirming adult care": "Gender-Affirming Care",
        "other gender-affirming services": "Gender-Affirming Care",
        "medical services for transgender/lgbtqia+ community":
            "Gender-Affirming Care",

        # Youth
        "youth gender care": "Youth Gender Care",
        "child and adolescent gender care": "Youth Gender Care",
        "pediatric and adolescent gender care": "Youth Gender Care",
        "pediatric gender care": "Youth Gender Care",
        "pediatric gender wellness": "Youth Gender Care",
        "gender-focused pediatric care": "Youth Gender Care",
        "gender development care": "Youth Gender Care",
        "gender diversity care": "Youth Gender Care",
        "gender pathway care": "Youth Gender Care",
        "gender and sexual development care": "Youth Gender Care",
        "transyouth health": "Youth Gender Care",

        # Mental health
        "mental health counseling": "Mental Health Counseling",
        "mental health": "Mental Health Counseling",
        "mental health support": "Mental Health Counseling",
        "mental health coordination": "Mental Health Counseling",
        "behavioral health": "Mental Health Counseling",
        "counseling": "Mental Health Counseling",
        "counseling referrals": "Mental Health Counseling",

        # Surgery
        "gender-affirming surgery": "Gender-Affirming Surgery",
        "gender affirming surgery": "Gender-Affirming Surgery",
        "plastic and reconstructive surgery": "Gender-Affirming Surgery",
        "surgical transitioning care": "Gender-Affirming Surgery",
        "surgery consultation": "Surgery Consultation",
        "surgical assessment": "Surgery Consultation",
        "surgery referrals": "Surgery Consultation",
        "surgery navigation": "Surgery Consultation",
        "surgical navigation": "Surgery Consultation",
        "surgery coordination": "Surgery Consultation",
        "gender-affirming surgery navigation": "Surgery Consultation",
        "surgery": "Surgery Consultation",

        # Navigation / coordination
        "care coordination": "Care Coordination",
        "case management": "Care Coordination",
        "primary care coordination": "Care Coordination",
        "treatment planning": "Care Coordination",
        "multidisciplinary care": "Care Coordination",
        "care navigation": "Care Navigation",
        "navigation": "Care Navigation",
        "patient navigation": "Care Navigation",
        "healthcare-navigation leads": "Care Navigation",
        "referrals": "Care Navigation",
        "referrals as available": "Care Navigation",
        "specialty referrals": "Care Navigation",
        "gender-related care and referrals": "Care Navigation",

        # Other canonical categories
        "patient advocacy": "Patient Advocacy",
        "advocacy": "Patient Advocacy",
        "insurance navigation": "Insurance Navigation",
        "fertility preservation": "Fertility Preservation",
        "voice therapy": "Voice Therapy",
        "voice and specialty services": "Voice Therapy",
        "telehealth": "Telehealth",

        "sexual and reproductive health": "Sexual and Reproductive Health",
        "sexual health": "Sexual and Reproductive Health",
        "sexual/reproductive health": "Sexual and Reproductive Health",
        "reproductive and sexual health care":
            "Sexual and Reproductive Health",
        "gender and sexual health": "Sexual and Reproductive Health",
        "gynecologic care": "Sexual and Reproductive Health",

        "prep and hiv prevention": "PrEP and HIV Prevention",
        "prep": "PrEP and HIV Prevention",
        "pre-exposure prophylaxis (prep)": "PrEP and HIV Prevention",
        "hiv prevention": "PrEP and HIV Prevention",

        "support groups & services": "Support Groups & Services",
        "support groups": "Support Groups & Services",
        "support": "Support Groups & Services",
        "family support": "Support Groups & Services",
        "community resources": "Support Groups & Services",

        "endocrinology": "Endocrinology",
        "endocrinologist": "Endocrinology",
        "endocrine care": "Endocrinology",

        # Capitalization-only standards
        "adolescent care": "Adolescent Care",
        "adolescent medicine": "Adolescent Medicine",
        "gender-related endocrine care": "Gender-Related Endocrine Care",
        "hormone-related specialty care": "Hormone-Related Specialty Care",
        "inclusive care": "Inclusive Care",
        "local lgbtq+ information": "Local LGBTQ+ Information",
        "pediatric specialty care": "Pediatric Specialty Care",
        "pediatric endocrinology": "Pediatric Endocrinology",
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
        "hiv/sti care": "HIV/STI Care",
        "lgbtq+ health": "LGBTQ+ Health",
        "lgbtq+ health services": "LGBTQ+ Health Services",
        "lgbtq+ supportive care": "LGBTQ+ Supportive Care",
        "transgender community services": "Transgender Community Services",
    }

    def normalize_service_name(self, value):
        value = (value or "").strip()
        if not value:
            return ""

        return self.SERVICE_ALIASES.get(
            value.casefold(),
            value,
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
        created_locations = 0
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
                city = (row.get("city") or "").strip()
                state = self.normalize_state(row.get("state"))
                address_line1 = (row.get("address_line1") or "").strip()
                address_line2 = (row.get("address_line2") or "").strip()
                zip_code = (row.get("zip_code") or "").strip()


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

                description = (
                    f"Source: {source_url}"
                    if source_url
                    else ""
                )

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
                        phone="",
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

                if state:
                    location_lookup = {
                        "organization": organization,
                        "address_line1": address_line1,
                        "city": city,
                        "state_code": state,
                        "zip_code": zip_code,
                    }

                    if dry_run:
                        if organization.pk:
                            location_exists = ProviderLocation.objects.filter(
                                **location_lookup
                            ).exists()
                            if not location_exists:
                                created_locations += 1
                        else:
                            created_locations += 1
                    else:
                        _, location_created = ProviderLocation.objects.get_or_create(
                            **location_lookup,
                            defaults={
                                "address_line2": address_line2 or None,
                                "is_primary": not organization.locations.exists(),
                            },
                        )
                        if location_created:
                            created_locations += 1

                if not services_text:
                    continue

                service_names = [
                    self.normalize_service_name(value)
                    for value in services_text.split(";")
                    if value.strip()
                ]

                # Avoid duplicate aliases within the same CSV row.
                service_names = list(dict.fromkeys(service_names))

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
            f"New locations: {created_locations}"
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

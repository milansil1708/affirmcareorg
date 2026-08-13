import csv
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from provider_organizations.models import (
    OrganizationService,
    ProviderOrganization,
    ProviderLocation,
    Service,
)


# NPPES provider/entity types that are potentially useful for a
# healthcare directory. We deliberately exclude many non-clinical
# supplier/entity types.
ALLOWED_ENTITY_TYPES = {
    "1": "Individual",
    "2": "Organization",
}

# Common NPPES taxonomy descriptions that are useful to Affirm Care.
# This is NOT an assertion that these providers are LGBTQ+ affirming.
USEFUL_TAXONOMY_KEYWORDS = (
    "physician",
    "nurse practitioner",
    "physician assistant",
    "psychiatry",
    "psychiatrist",
    "psychologist",
    "social worker",
    "counselor",
    "behavioral health",
    "mental health",
    "family medicine",
    "internal medicine",
    "obstetrics",
    "gynecology",
    "pediatrics",
    "primary care",
    "endocrinology",
    "urology",
    "surgery",
    "dentist",
    "dental",
    "physical therapist",
    "occupational therapist",
    "speech-language",
)


def clean(value, max_length=None):
    value = re.sub(r"\s+", " ", str(value or "")).strip()

    if max_length and len(value) > max_length:
        value = value[:max_length].rstrip()

    return value


def first_nonempty(*values):
    for value in values:
        value = clean(value)
        if value:
            return value
    return ""


def normalize_phone(value):
    value = clean(value)

    if not value:
        return ""

    value = re.sub(r"[^0-9+(). xX-]", "", value)

    return value[:20]


def normalize_state(value):
    value = clean(value).upper()

    if len(value) == 2:
        return value

    return value[:100]


def make_name(row):
    entity_type = clean(row.get("Entity Type Code"))

    if entity_type == "1":
        first = clean(row.get("Provider First Name"))
        middle = clean(row.get("Provider Middle Name"))
        last = clean(row.get("Provider Last Name"))
        credential = clean(row.get("Provider Credential Text"))

        name_parts = [part for part in (first, middle, last) if part]

        if name_parts:
            name = " ".join(name_parts)

            if credential:
                name = f"{name}, {credential}"

            return name[:100]

    organization_name = clean(
        row.get("Provider Organization Name (Legal Business Name)")
    )

    if organization_name:
        return organization_name[:100]

    other_name = clean(
        row.get("Provider Other Organization Name")
    )

    if other_name:
        return other_name[:100]

    first = clean(row.get("Provider First Name"))
    last = clean(row.get("Provider Last Name"))

    return clean(f"{first} {last}", 100) or "Unnamed Provider"


def get_taxonomy(row):
    taxonomies = []

    for index in range(1, 16):
        taxonomy = clean(
            row.get(f"Healthcare Provider Taxonomy Code_{index}")
        )

        description = clean(
            row.get(
                f"Healthcare Provider Taxonomy Description_{index}"
            )
        )

        if description:
            taxonomies.append(description)
        elif taxonomy:
            taxonomies.append(taxonomy)

    return list(dict.fromkeys(taxonomies))


def is_useful_provider(row):
    entity_type = clean(row.get("Entity Type Code"))

    if entity_type not in ALLOWED_ENTITY_TYPES:
        return False

    taxonomies = get_taxonomy(row)

    searchable = " ".join(taxonomies).casefold()

    return any(
        keyword in searchable
        for keyword in USEFUL_TAXONOMY_KEYWORDS
    )


def get_org_type(row):
    entity_type = clean(row.get("Entity Type Code"))

    if entity_type == "2":
        return "clinic"

    return "private_practice"


def get_description(row, taxonomies):
    name = make_name(row)

    if taxonomies:
        specialty_text = ", ".join(taxonomies[:5])

        return (
            f"{name} is listed in the CMS NPPES public database. "
            f"Listed provider specialties/taxonomies: "
            f"{specialty_text}. "
            f"This record has not been independently verified by "
            f"Affirm Care."
        )

    return (
        f"{name} is listed in the CMS NPPES public database. "
        f"This record has not been independently verified by "
        f"Affirm Care."
    )


def get_email(row):
    # NPPES generally does not provide a provider email address.
    # Leave blank rather than inventing one.
    return ""


def get_website(row):
    # NPPES does not reliably provide a provider website.
    # Leave blank rather than treating unrelated fields as websites.
    return None


def get_service_name(taxonomies):
    if not taxonomies:
        return "Healthcare Provider"

    text = " ".join(taxonomies).casefold()

    if "psychiatr" in text:
        return "Psychiatry"

    if (
        "psychologist" in text
        or "psychology" in text
    ):
        return "Psychology"

    if (
        "social worker" in text
        or "clinical social worker" in text
    ):
        return "Mental Health Counseling"

    if (
        "counselor" in text
        or "behavioral health" in text
        or "mental health" in text
    ):
        return "Mental Health Counseling"

    if (
        "family medicine" in text
        or "family practice" in text
        or "primary care" in text
        or "internal medicine" in text
    ):
        return "Primary Care"

    if "endocrin" in text:
        return "Endocrinology"

    if "gynecology" in text or "obstetric" in text:
        return "Gynecology"

    if "pediatric" in text:
        return "Pediatrics"

    if "dentist" in text or "dental" in text:
        return "Dentistry"

    if "physical therapist" in text:
        return "Physical Therapy"

    if "occupational therapist" in text:
        return "Occupational Therapy"

    if "speech-language" in text:
        return "Speech Therapy"

    if "nurse practitioner" in text:
        return "Nurse Practitioner"

    if "physician assistant" in text:
        return "Physician Assistant"

    if "physician" in text:
        return "Physician"

    return "Healthcare Provider"


def create_service(name):
    service, _ = Service.objects.get_or_create(
        name=name
    )

    return service


class Command(BaseCommand):
    help = (
        "Import selected provider records from the CMS NPPES "
        "CSV into Affirm Care."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_file",
            help="Path to the extracted NPPES CSV file.",
        )

        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help=(
                "Maximum number of qualifying records to process. "
                "Default: 100."
            ),
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=(
                "Read and filter the file without creating "
                "database records."
            ),
        )

    def handle(self, *args, **options):
        csv_file = Path(options["csv_file"])
        limit = options["limit"]
        dry_run = options["dry_run"]

        if not csv_file.exists():
            raise CommandError(
                f"File does not exist: {csv_file}"
            )

        if not csv_file.is_file():
            raise CommandError(
                f"Not a file: {csv_file}"
            )

        if limit < 1:
            raise CommandError(
                "--limit must be at least 1."
            )

        self.stdout.write(
            f"Reading NPPES file: {csv_file}"
        )

        qualifying = 0
        skipped = 0
        duplicates = 0
        created = 0

        with csv_file.open(
            "r",
            encoding="latin-1",
            newline="",
        ) as csv_handle:

            reader = csv.DictReader(csv_handle)

            if not reader.fieldnames:
                raise CommandError(
                    "The CSV does not contain a header row."
                )

            if "NPI" not in reader.fieldnames:
                raise CommandError(
                    "This does not appear to be an NPPES "
                    "main provider file because the NPI column "
                    "was not found."
                )

            for row in reader:

                if qualifying >= limit:
                    break

                if not is_useful_provider(row):
                    skipped += 1
                    continue

                npi = clean(row.get("NPI"))

                if not npi:
                    skipped += 1
                    continue

                qualifying += 1

                name = make_name(row)
                taxonomies = get_taxonomy(row)
                service_name = get_service_name(
                    taxonomies
                )

                existing = ProviderOrganization.objects.filter(
                    npi=npi
                ).first()

                if existing:
                    duplicates += 1
                    continue

                self.stdout.write(
                    f"{qualifying}: {name} "
                    f"(NPI {npi})"
                )

                if dry_run:
                    continue

                organization_data = {
                    "name": name,
                    "org_type": get_org_type(row),
                    "description": get_description(
                        row,
                        taxonomies,
                    ),
                    "website_url": get_website(row),
                    "booking_url": None,
                    "phone": normalize_phone(
                        first_nonempty(
                            row.get(
                                "Provider Business Practice Location Phone Number"
                            ),
                            row.get(
                                "Provider Business Mailing Address Telephone Number"
                            ),
                        )
                    ),
                    "email": get_email(row),
                    "is_active": False,
                    "last_verified_at": None,
                    "npi": npi,
                }

                address_line1 = first_nonempty(
                    row.get(
                        "Provider First Line Business Practice Location Address"
                    ),
                    row.get(
                        "Provider First Line Business Mailing Address"
                    ),
                )

                address_line2 = first_nonempty(
                    row.get(
                        "Provider Second Line Business Practice Location Address"
                    ),
                    row.get(
                        "Provider Second Line Business Mailing Address"
                    ),
                )

                city = first_nonempty(
                    row.get(
                        "Provider Business Practice Location Address City Name"
                    ),
                    row.get(
                        "Provider Business Mailing Address City Name"
                    ),
                )

                state = first_nonempty(
                    row.get(
                        "Provider Business Practice Location Address State Name"
                    ),
                    row.get(
                        "Provider Business Mailing Address State Name"
                    ),
                )

                zip_code = first_nonempty(
                    row.get(
                        "Provider Business Practice Location Address Postal Code"
                    ),
                    row.get(
                        "Provider Business Mailing Address Postal Code"
                    ),
                )

                latitude = first_nonempty(
                    row.get(
                        "Provider Business Practice Location Latitude"
                    )
                )

                longitude = first_nonempty(
                    row.get(
                        "Provider Business Practice Location Longitude"
                    )
                )

                with transaction.atomic():

                    organization = (
                        ProviderOrganization.objects.create(
                            **organization_data
                        )
                    )

                    created += 1

                    if (
                        address_line1
                        or city
                        or state
                        or zip_code
                    ):
                        ProviderLocation.objects.create(
                            organization=organization,
                            address_line1=address_line1
                            or "Address not provided",
                            address_line2=address_line2
                            or None,
                            city=city,
                            state_code=normalize_state(
                                state
                            ),
                            zip_code=zip_code,
                            latitude=(
                                latitude
                                or None
                            ),
                            longitude=(
                                longitude
                                or None
                            ),
                            is_primary=True,
                            wheelchair_accessible=False,
                            gender_neutral_restrooms=False,
                            public_transit_notes=False,
                        )

                    service = create_service(
                        service_name
                    )

                    OrganizationService.objects.create(
                        organization=organization,
                        service=service,
                        delivery_mode="in_person",
                        age_group="all",
                        note=(
                            "Source: CMS NPPES public database. "
                            "This information has not been "
                            "independently verified by Affirm Care."
                        ),
                    )

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    "DRY RUN COMPLETE — no records were created.\n"
                    f"Qualifying records found: {qualifying}\n"
                    f"Skipped: {skipped}\n"
                    f"Existing NPI records: {duplicates}"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "NPPES IMPORT COMPLETE\n"
                    f"Created: {created}\n"
                    f"Qualifying records examined: {qualifying}\n"
                    f"Skipped: {skipped}\n"
                    f"Duplicates: {duplicates}"
                )
            )

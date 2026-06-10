import csv
import json
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


APPLICATION_ID = "SCMERBGKU4"
SEARCH_API_KEY = "e358a47877b821aacbdc990a7412dd36"
INDEX_NAME = "tsf_provider_prod_desc_sort"
DIRECTORY_URL = "https://lgbtqhealthcaredirectory.org"
SEARCH_ENDPOINT = (
    f"https://{APPLICATION_ID}-dsn.algolia.net/1/indexes/*/queries"
)
SEARCH_METADATA_FIELDS = {
    "_highlightResult",
    "_rankingInfo",
    "_snippetResult",
}
APPROACH_DESCRIPTIONS = {
    "Harm Reduction": (
        "The provider reports using harm-reduction principles in patient care."
    ),
    "Informed Consent": (
        "The provider reports using an informed-consent approach."
    ),
    "Racial Equity": (
        "The provider reports centering racial equity in patient care."
    ),
    "Sex Positive": (
        "The provider reports using a sex-positive approach."
    ),
    "Trauma Informed Care": (
        "The provider reports using trauma-informed care principles."
    ),
    "Weight Inclusive": (
        "The provider reports using a weight-inclusive approach."
    ),
}
FEATURE_DESCRIPTIONS = {
    "GLMA Affiliated": "The source directory reports GLMA affiliation.",
    "LGBTQ+ Practice": (
        "The source directory identifies the practice as LGBTQ+ focused."
    ),
    "Multilingual Support": (
        "The provider reports offering care in more than one language."
    ),
    "Telehealth Available": (
        "The provider offers virtual or telehealth services."
    ),
    "Violet Verified": (
        "The source directory reports a Violet verification."
    ),
    "Wheelchair Accessible Location": (
        "At least one listed location reports wheelchair or ADA accessibility."
    ),
}
SERVICE_ALIASES = {
    "Behavioral/Mental Health": "Mental Health Counseling",
    "Mental Health": "Mental Health Counseling",
    "Behavioral Health": "Mental Health Counseling",
    "Therapist": "Mental Health Counseling",
    "Counselor": "Mental Health Counseling",
    "Psychotherapy": "Mental Health Counseling",
    "Psychology": "Mental Health Counseling",
    "Psychologist": "Mental Health Counseling",
    "Licensed Marriage and Family Therapist": "Mental Health Counseling",
    "Art Therapist": "Mental Health Counseling",
    "Music Therapist": "Mental Health Counseling",
    "Sex Therapist": "Mental Health Counseling",
    "Gender Affirming Hormone Therapy": "Hormone Therapy",
    "Gender Affirming Care": "Gender-Affirming Care",
    "Gender Affirming Services": "Gender-Affirming Care",
    "Trans & Nonbinary Health": "Gender-Affirming Care",
    "HIV Prevention & Care": "PrEP and HIV Prevention",
    "Family Medicine": "Primary Care",
    "General Practitioner": "Primary Care",
    "Internal Medicine": "Primary Care",
    "Preventive Care": "Primary Care",
    "Psychiatrist": "Psychiatry",
    "Podiatrist": "Podiatry",
}
GENERIC_PROVIDER_TYPES = {
    "Allied Healthcare",
    "Complementary/Alternative Health",
    "Nurse Practitioner",
    "Specialist",
}
US_STATE_CODES = {
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
CANADA_PROVINCE_CODES = {
    "Alberta": "AB",
    "British Columbia": "BC",
    "Manitoba": "MB",
    "New Brunswick": "NB",
    "Newfoundland and Labrador": "NL",
    "Northwest Territories": "NT",
    "Nova Scotia": "NS",
    "Nunavut": "NU",
    "Ontario": "ON",
    "Prince Edward Island": "PE",
    "Quebec": "QC",
    "Saskatchewan": "SK",
    "Yukon": "YT",
}


class DirectoryScrapeError(RuntimeError):
    """Raised when the directory search service cannot be read."""


def _request_page(
    page,
    hits_per_page,
    timeout,
    max_post_date=None,
    retries=3,
):
    query_params = {
        "query": "",
        "page": page,
        "hitsPerPage": hits_per_page,
        "analytics": "false",
        "clickAnalytics": "false",
    }
    if max_post_date is not None:
        query_params["numericFilters"] = json.dumps(
            [f"post_date_unix<={max_post_date}"]
        )
    params = urlencode(query_params)
    payload = json.dumps(
        {
            "requests": [
                {
                    "indexName": INDEX_NAME,
                    "params": params,
                }
            ]
        }
    ).encode("utf-8")
    request = Request(
        SEARCH_ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Origin": DIRECTORY_URL,
            "Referer": f"{DIRECTORY_URL}/",
            "User-Agent": "AffirmCareDirectoryScraper/1.0",
            "X-Algolia-API-Key": SEARCH_API_KEY,
            "X-Algolia-Application-Id": APPLICATION_ID,
        },
    )

    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            is_transient = exc.code == 429 or 500 <= exc.code < 600
            if not is_transient or attempt == retries:
                raise DirectoryScrapeError(
                    f"Directory search returned HTTP {exc.code}: {details}"
                ) from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == retries:
                attempts = retries + 1
                raise DirectoryScrapeError(
                    "Could not read the directory search service after "
                    f"{attempts} attempts: {exc}"
                ) from exc

        time.sleep(min(2**attempt, 8))


def _normalize_hit(hit, rank):
    record = {
        key: value
        for key, value in hit.items()
        if key not in SEARCH_METADATA_FIELDS
    }
    slug = record.get("slug")
    record["record_rank"] = rank
    record["source_url"] = (
        f"{DIRECTORY_URL}/provider/{slug}" if slug else DIRECTORY_URL
    )
    if record.get("photo") is False:
        record["photo"] = None
    return record


def _extract_search_result(payload):
    try:
        result = payload["results"][0]
        hits = result["hits"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DirectoryScrapeError(
            "Directory search returned an unexpected response."
        ) from exc
    if result.get("message") and not hits:
        raise DirectoryScrapeError(result["message"])
    return result, hits


def scrape_raw_providers(limit=100, timeout=30, start=1, retries=3):
    """Return a one-based range in the directory's newest-first order."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if start < 1:
        raise ValueError("start must be at least 1")
    if retries < 0:
        raise ValueError("retries cannot be negative")

    records = []
    seen_object_ids = set()
    target_end = start + limit - 1
    max_post_date = None

    while len(records) < target_end:
        window_min_post_date = None
        window_added = 0

        # Algolia limits each query to 1,000 hits. A timestamp-filtered
        # window lets the scraper continue beyond that ceiling.
        for page in range(10):
            payload = _request_page(
                page=page,
                hits_per_page=100,
                timeout=timeout,
                max_post_date=max_post_date,
                retries=retries,
            )
            result, hits = _extract_search_result(payload)
            if not hits:
                break

            for hit in hits:
                post_date = hit.get("post_date_unix")
                if post_date is not None:
                    if window_min_post_date is None:
                        window_min_post_date = post_date
                    else:
                        window_min_post_date = min(
                            window_min_post_date,
                            post_date,
                        )

                object_id = hit.get("objectID")
                dedupe_key = object_id or (
                    hit.get("slug"),
                    hit.get("title"),
                    hit.get("post_date_unix"),
                )
                if dedupe_key in seen_object_ids:
                    continue
                seen_object_ids.add(dedupe_key)
                records.append(_normalize_hit(hit, len(records) + 1))
                window_added += 1
                if len(records) == target_end:
                    return records[start - 1 : target_end]

            if len(hits) < 100 or page + 1 >= result.get("nbPages", 10):
                break

        if window_added == 0:
            break
        if window_min_post_date is None:
            raise DirectoryScrapeError(
                "Cannot continue beyond the first 1,000 records because "
                "the directory response has no publication timestamps."
            )
        max_post_date = window_min_post_date

    return records[start - 1 : target_end]


def _clean_text(value, max_length=None):
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    if max_length and len(value) > max_length:
        value = value[: max_length - 3].rstrip() + "..."
    return value


def _clean_url(value):
    value = _clean_text(value, 200)
    return value if value.startswith(("http://", "https://")) else None


def _clean_phone(value):
    value = _clean_text(value)
    value = re.sub(r"[^0-9+(). xX-]", "", value)
    if len(value) > 20:
        value = value.replace(" ", "")
    return value[:20]


def _unique(values):
    return list(dict.fromkeys(value for value in values if value))


def _visible_locations(hit):
    return [
        location
        for location in hit.get("address_repeater") or []
        if not location.get("hide_listing")
    ]


def _practice_name(hit, locations):
    primary_locations = [
        location for location in locations if location.get("primary")
    ]
    candidates = primary_locations + locations
    return next(
        (
            _clean_text(location.get("title"))
            for location in candidates
            if _clean_text(location.get("title"))
        ),
        "",
    )


def _organization_name(hit, locations):
    provider_name = _clean_text(hit.get("title"))
    practice_name = _practice_name(hit, locations)
    if practice_name and practice_name.casefold() != provider_name.casefold():
        return _clean_text(f"{practice_name} ({provider_name})", 100)
    return _clean_text(practice_name or provider_name or "Unnamed Provider", 100)


def _organization_type(hit, locations, organization_name):
    physical_locations = [
        location for location in locations if not location.get("virtual")
    ]
    if hit.get("telehealth") and not physical_locations:
        return "telehealth"

    searchable_text = " ".join(
        [
            organization_name,
            _clean_text(hit.get("details")),
            _clean_text(hit.get("profile_url")),
        ]
    ).casefold()
    if any(
        keyword in searchable_text
        for keyword in (
            "hospital",
            "medical center",
            "health system",
            "university",
        )
    ):
        return "hospital_program"
    if any(
        keyword in searchable_text
        for keyword in ("nonprofit", "non-profit", "community resource")
    ):
        return "nonprofit"
    if any(
        keyword in organization_name.casefold()
        for keyword in ("clinic", "center", "health", "medical", "wellness")
    ):
        return "clinic"
    return "private_practice"


def _organization_description(hit, source_url):
    details = _clean_text(hit.get("details"))
    provider_name = _clean_text(hit.get("title"))
    licenses = _unique(hit.get("licenses") or [])
    specialties = _unique(
        (hit.get("primary_specialty") or []) + (hit.get("specialty") or [])
    )
    languages = _unique(hit.get("language") or [])
    insurance = _unique(
        (hit.get("insurance_types") or [])
        + (hit.get("insurance_public") or [])
        + (hit.get("insurance_private") or [])
    )

    facts = []
    if provider_name:
        facts.append(f"Listed provider: {provider_name}.")
    if licenses:
        facts.append(f"Credentials: {', '.join(licenses)}.")
    if specialties:
        facts.append(f"Areas of care: {', '.join(specialties)}.")
    if languages:
        facts.append(f"Languages: {', '.join(languages)}.")
    if insurance:
        facts.append(f"Payment and insurance: {', '.join(insurance)}.")
    facts.append(f"Source: {source_url}")
    return "\n\n".join(filter(None, [details, " ".join(facts)]))


def _location_records(locations):
    physical_locations = [
        location
        for location in locations
        if not location.get("virtual")
        and any(
            _clean_text(location.get(field))
            for field in (
                "address_line_one",
                "city",
                "state",
                "zip",
            )
        )
    ]
    records = []
    for index, location in enumerate(physical_locations):
        accessibility = {
            value.casefold() for value in location.get("accessibility") or []
        }
        state = _clean_text(location.get("state"))
        records.append(
            {
                "address_line1": _clean_text(
                    location.get("address_line_one"), 255
                ),
                "address_line2": _clean_text(
                    location.get("address_line_two"), 255
                )
                or None,
                "city": _clean_text(location.get("city"), 100),
                "state_code": _clean_text(
                    US_STATE_CODES.get(
                        state,
                        CANADA_PROVINCE_CODES.get(state, state),
                    ),
                    100,
                ),
                "zip_code": _clean_text(location.get("zip"), 20),
                "latitude": _clean_text(location.get("lat")) or None,
                "longitude": _clean_text(location.get("lng")) or None,
                "is_primary": bool(location.get("primary")) or index == 0,
                "wheelchair_accessible": bool(
                    accessibility
                    & {"wheelchair accessible", "ada compliant"}
                ),
                "gender_neutral_restrooms": False,
                "public_transit_notes": False,
            }
        )
    if records and not any(record["is_primary"] for record in records):
        records[0]["is_primary"] = True
    return records


def _service_names(hit):
    source_specialties = _unique(
        (hit.get("primary_specialty") or []) + (hit.get("specialty") or [])
    )
    services = []
    for specialty in source_specialties:
        if specialty in GENERIC_PROVIDER_TYPES:
            continue
        services.append(
            _clean_text(SERVICE_ALIASES.get(specialty, specialty), 100)
        )
    return _unique(services)


def _delivery_mode(hit, locations):
    has_physical = any(not location.get("virtual") for location in locations)
    has_virtual = bool(hit.get("telehealth")) or any(
        location.get("virtual") for location in locations
    )
    if has_physical and has_virtual:
        return "both"
    if has_virtual:
        return "telehealth"
    return "in_person"


def _age_group(hit):
    return "all" if "Youth" in (hit.get("focus") or []) else "adult"


def _service_records(hit, locations, source_url):
    source_specialties = _unique(
        (hit.get("primary_specialty") or []) + (hit.get("specialty") or [])
    )
    note_parts = []
    if source_specialties:
        note_parts.append(
            "Source specialties: " + ", ".join(source_specialties) + "."
        )
    note_parts.append(f"Source: {source_url}")
    note = " ".join(note_parts)
    return [
        {
            "service": service_name,
            "delivery_mode": _delivery_mode(hit, locations),
            "age_group": _age_group(hit),
            "note": note,
        }
        for service_name in _service_names(hit)
    ]


def _yes_value(values):
    return any(str(value).casefold().startswith("yes") for value in values or [])


def _feature_records(hit, locations, source_url):
    features = []

    def add_feature(label, description, evidence):
        if any(feature["feature"] == label for feature in features):
            return
        features.append(
            {
                "feature": label,
                "feature_description": description,
                "value": "yes",
                "evidence_note": evidence,
                "source_url": source_url,
                "verified_at": None,
            }
        )

    for approach in _unique(hit.get("approach") or []):
        add_feature(
            approach,
            APPROACH_DESCRIPTIONS.get(
                approach,
                f"The provider reports using a {approach} approach.",
            ),
            f"Source directory lists the care approach: {approach}.",
        )

    if hit.get("telehealth") or any(
        location.get("virtual") for location in locations
    ):
        add_feature(
            "Telehealth Available",
            FEATURE_DESCRIPTIONS["Telehealth Available"],
            "The source directory marks this provider as offering telehealth.",
        )

    accessible_locations = [
        location
        for location in locations
        if {
            value.casefold()
            for value in location.get("accessibility") or []
        }
        & {"wheelchair accessible", "ada compliant"}
    ]
    if accessible_locations:
        add_feature(
            "Wheelchair Accessible Location",
            FEATURE_DESCRIPTIONS["Wheelchair Accessible Location"],
            "At least one source location is marked Wheelchair Accessible "
            "or ADA Compliant.",
        )

    languages = _unique(hit.get("language") or [])
    if len(languages) > 1:
        add_feature(
            "Multilingual Support",
            FEATURE_DESCRIPTIONS["Multilingual Support"],
            f"Source directory lists these languages: {', '.join(languages)}.",
        )

    if hit.get("lgbtq_practice") or any(
        location.get("lgbtq") for location in locations
    ):
        add_feature(
            "LGBTQ+ Practice",
            FEATURE_DESCRIPTIONS["LGBTQ+ Practice"],
            "The source directory marks the practice as LGBTQ+ focused.",
        )

    if _yes_value(hit.get("glma_affiliated")):
        add_feature(
            "GLMA Affiliated",
            FEATURE_DESCRIPTIONS["GLMA Affiliated"],
            "The source directory reports GLMA affiliation.",
        )
    if _yes_value(hit.get("violet_verified")):
        add_feature(
            "Violet Verified",
            FEATURE_DESCRIPTIONS["Violet Verified"],
            "The source directory reports Violet verification.",
        )
    return features


def map_provider_to_schema(hit):
    """Map a source provider into fields represented by the Django models."""
    source_url = hit.get("source_url") or (
        f"{DIRECTORY_URL}/provider/{hit.get('slug')}"
        if hit.get("slug")
        else DIRECTORY_URL
    )
    locations = _visible_locations(hit)
    organization_name = _organization_name(hit, locations)
    practice_url = next(
        (
            _clean_url(location.get("link"))
            for location in locations
            if _clean_url(location.get("link"))
        ),
        None,
    )
    website_url = _clean_url(hit.get("profile_url")) or practice_url

    return {
        "source": {
            "directory": DIRECTORY_URL,
            "object_id": _clean_text(hit.get("objectID")),
            "provider_name": _clean_text(hit.get("title")),
            "source_url": source_url,
            "source_post_date": hit.get("post_date"),
            "record_rank": hit.get("record_rank"),
        },
        "ProviderOrganization": {
            "name": organization_name,
            "org_type": _organization_type(
                hit,
                locations,
                organization_name,
            ),
            "description": _organization_description(hit, source_url),
            "website_url": website_url,
            "booking_url": _clean_url(hit.get("reservation_link")),
            "phone": _clean_phone(hit.get("phone")),
            "email": _clean_text(hit.get("email"), 100),
            "is_active": bool(
                hit.get("post_status") == "publish"
                and hit.get("is_public_profile", True)
            ),
            "last_verified_at": None,
        },
        "ProviderLocation": _location_records(locations),
        "OrganizationService": _service_records(
            hit,
            locations,
            source_url,
        ),
        "ProviderFeature": _feature_records(hit, locations, source_url),
    }


def scrape_providers(limit=100, timeout=30, start=1, retries=3):
    """Return only source data that can be represented by the local schema."""
    return [
        map_provider_to_schema(record)
        for record in scrape_raw_providers(
            limit=limit,
            timeout=timeout,
            start=start,
            retries=retries,
        )
    ]


def write_json(records, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def write_csv(records, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = []
    for record in records:
        for key in record:
            if key not in fieldnames:
                fieldnames.append(key)

    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            row = {
                key: (
                    json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value
                )
                for key, value in record.items()
            }
            writer.writerow(row)
    return path

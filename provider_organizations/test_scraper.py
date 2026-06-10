import csv
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from provider_organizations.models import (
    AffirmingFeature,
    OrganizationService,
    ProviderFeature,
    ProviderLocation,
    ProviderOrganization,
    Service,
)

from provider_organizations.scrapers.lgbtq_healthcare_directory import (
    DirectoryScrapeError,
    map_provider_to_schema,
    scrape_raw_providers,
    scrape_providers,
    write_csv,
    write_json,
)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


class DirectoryScraperTests(SimpleTestCase):
    @patch(
        "provider_organizations.scrapers."
        "lgbtq_healthcare_directory.urlopen"
    )
    def test_scrape_providers_maps_search_results_to_schema(
        self, mock_urlopen
    ):
        response = {
            "results": [
                {
                    "hits": [
                        {
                            "objectID": "tsf_post#1",
                            "title": "Provider One",
                            "slug": "provider-one",
                            "photo": False,
                            "specialty": ["Primary Care"],
                            "post_status": "publish",
                            "is_public_profile": True,
                            "email": "one@example.com",
                            "phone": "(555) 123-4567",
                            "address_repeater": [],
                            "_highlightResult": {"title": {}},
                        },
                        {
                            "objectID": "tsf_post#2",
                            "title": "Provider Two",
                            "slug": "provider-two",
                            "photo": "https://example.com/photo.jpg",
                            "post_status": "publish",
                            "is_public_profile": True,
                            "address_repeater": [],
                        },
                    ]
                }
            ]
        }
        mock_urlopen.return_value = FakeResponse(
            json.dumps(response).encode("utf-8")
        )

        records = scrape_providers(limit=2)

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["source"]["record_rank"], 1)
        self.assertEqual(
            records[0]["ProviderOrganization"]["name"],
            "Provider One",
        )
        self.assertEqual(
            records[0]["OrganizationService"][0]["service"],
            "Primary Care",
        )
        self.assertEqual(
            records[0]["source"]["source_url"],
            "https://lgbtqhealthcaredirectory.org/provider/provider-one",
        )

        request = mock_urlopen.call_args.args[0]
        request_body = json.loads(request.data)
        self.assertIn("hitsPerPage=100", request_body["requests"][0]["params"])
        self.assertEqual(
            request.headers["Referer"],
            "https://lgbtqhealthcaredirectory.org/",
        )

    @patch(
        "provider_organizations.scrapers."
        "lgbtq_healthcare_directory.urlopen"
    )
    def test_scrape_providers_rejects_unexpected_response(
        self, mock_urlopen
    ):
        mock_urlopen.return_value = FakeResponse(b"{}")

        with self.assertRaises(DirectoryScrapeError):
            scrape_providers(limit=1)

    @patch(
        "provider_organizations.scrapers."
        "lgbtq_healthcare_directory._request_page"
    )
    def test_range_crosses_algolia_limit_without_duplicates(
        self, mock_request_page
    ):
        source_hits = [
            {
                "objectID": f"provider-{number}",
                "title": f"Provider {number}",
                "slug": f"provider-{number}",
                "post_date_unix": 10_000 - number,
            }
            for number in range(1, 1006)
        ]

        def request_page(
            page,
            hits_per_page,
            timeout,
            max_post_date=None,
            retries=3,
        ):
            filtered = source_hits
            if max_post_date is not None:
                filtered = [
                    hit
                    for hit in source_hits
                    if hit["post_date_unix"] <= max_post_date
                ]
            page_start = page * hits_per_page
            hits = filtered[page_start : page_start + hits_per_page]
            return {
                "results": [
                    {
                        "hits": hits,
                        "nbPages": min(
                            10,
                            (len(filtered) + hits_per_page - 1)
                            // hits_per_page,
                        ),
                    }
                ]
            }

        mock_request_page.side_effect = request_page

        records = scrape_raw_providers(start=996, limit=10)

        self.assertEqual(len(records), 10)
        self.assertEqual(records[0]["objectID"], "provider-996")
        self.assertEqual(records[-1]["objectID"], "provider-1005")
        self.assertEqual(
            len({record["objectID"] for record in records}),
            10,
        )

    @patch(
        "provider_organizations.scrapers."
        "lgbtq_healthcare_directory.time.sleep"
    )
    @patch(
        "provider_organizations.scrapers."
        "lgbtq_healthcare_directory.urlopen"
    )
    def test_transient_dns_failure_is_retried(
        self,
        mock_urlopen,
        mock_sleep,
    ):
        response = {
            "results": [
                {
                    "hits": [
                        {
                            "objectID": "provider-1",
                            "title": "Provider One",
                            "slug": "provider-one",
                            "post_date_unix": 100,
                        }
                    ],
                    "nbPages": 1,
                }
            ]
        }
        mock_urlopen.side_effect = [
            URLError("[Errno 11001] getaddrinfo failed"),
            FakeResponse(json.dumps(response).encode("utf-8")),
        ]

        records = scrape_raw_providers(limit=1, retries=3)

        self.assertEqual(len(records), 1)
        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once_with(1)

    def test_export_helpers_write_nested_values(self):
        records = [
            {
            "title": "Provider One",
                "ProviderOrganization": {"name": "Provider One"},
                "ProviderLocation": [{"city": "Boston"}],
            }
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            json_path = write_json(records, output_dir / "providers.json")
            csv_path = write_csv(records, output_dir / "providers.csv")

            self.assertEqual(
                json.loads(json_path.read_text(encoding="utf-8")),
                records,
            )
            with csv_path.open(encoding="utf-8-sig", newline="") as csv_file:
                row = next(csv.DictReader(csv_file))
            self.assertEqual(
                json.loads(row["ProviderOrganization"]),
                {"name": "Provider One"},
            )
            self.assertEqual(
                json.loads(row["ProviderLocation"]),
                [{"city": "Boston"}],
            )

    def test_map_provider_to_schema_uses_only_supported_evidence(self):
        record = map_provider_to_schema(
            {
                "objectID": "tsf_post#10",
                "title": "Alex Provider",
                "slug": "alex-provider",
                "post_status": "publish",
                "is_public_profile": True,
                "telehealth": True,
                "details": "Provides affirming primary care.",
                "profile_url": "https://practice.example",
                "reservation_link": "https://practice.example/book",
                "email": "care@practice.example",
                "phone": "(555) 123-4567 ext 89",
                "primary_specialty": ["Primary Care"],
                "specialty": [
                    "Primary Care",
                    "Gender Affirming Hormone Therapy",
                ],
                "focus": ["Youth"],
                "approach": ["Trauma Informed Care", "Informed Consent"],
                "language": ["English", "Spanish"],
                "address_repeater": [
                    {
                        "title": "Affirming Health Clinic",
                        "address_line_one": "1 Main Street",
                        "address_line_two": "Suite 2",
                        "city": "Boston",
                        "state": "Massachusetts",
                        "zip": "02110",
                        "lat": "42.3601",
                        "lng": "-71.0589",
                        "virtual": False,
                        "primary": True,
                        "hide_listing": False,
                        "accessibility": ["ADA Compliant"],
                    }
                ],
            }
        )

        organization = record["ProviderOrganization"]
        self.assertEqual(
            organization["name"],
            "Affirming Health Clinic (Alex Provider)",
        )
        self.assertEqual(organization["org_type"], "clinic")
        self.assertEqual(organization["phone"], "(555) 123-4567 x 89")

        self.assertEqual(
            record["ProviderLocation"][0]["state_code"],
            "MA",
        )
        self.assertTrue(
            record["ProviderLocation"][0]["wheelchair_accessible"]
        )
        self.assertEqual(
            {service["service"] for service in record["OrganizationService"]},
            {"Primary Care", "Hormone Therapy"},
        )
        self.assertTrue(
            all(
                service["delivery_mode"] == "both"
                for service in record["OrganizationService"]
            )
        )
        self.assertTrue(
            all(
                service["age_group"] == "all"
                for service in record["OrganizationService"]
            )
        )
        self.assertEqual(
            {
                feature["feature"]
                for feature in record["ProviderFeature"]
            },
            {
                "Trauma Informed Care",
                "Informed Consent",
                "Telehealth Available",
                "Wheelchair Accessible Location",
                "Multilingual Support",
            },
        )


class SchemaImportCommandTests(TestCase):
    @patch(
        "provider_organizations.management.commands."
        "scrape_lgbtq_directory.scrape_providers"
    )
    def test_import_db_creates_schema_records_without_duplicates(
        self, mock_scrape
    ):
        mock_scrape.return_value = [
            {
                "source": {
                    "object_id": "tsf_post#10",
                    "source_url": (
                        "https://lgbtqhealthcaredirectory.org/provider/"
                        "provider-one"
                    ),
                },
                "ProviderOrganization": {
                    "name": "Affirming Health (Provider One)",
                    "org_type": "clinic",
                    "description": "Affirming primary care.",
                    "website_url": "https://practice.example",
                    "booking_url": None,
                    "phone": "(555) 123-4567",
                    "email": "care@practice.example",
                    "is_active": True,
                    "last_verified_at": None,
                },
                "ProviderLocation": [
                    {
                        "address_line1": "1 Main Street",
                        "address_line2": None,
                        "city": "Boston",
                        "state_code": "MA",
                        "zip_code": "02110",
                        "latitude": "42.360100",
                        "longitude": "-71.058900",
                        "is_primary": True,
                        "wheelchair_accessible": True,
                        "gender_neutral_restrooms": False,
                        "public_transit_notes": False,
                    }
                ],
                "OrganizationService": [
                    {
                        "service": "Primary Care",
                        "delivery_mode": "both",
                        "age_group": "all",
                        "note": "Source specialties: Primary Care.",
                    }
                ],
                "ProviderFeature": [
                    {
                        "feature": "Telehealth Available",
                        "feature_description": (
                            "The provider offers virtual or telehealth services."
                        ),
                        "value": "yes",
                        "evidence_note": (
                            "The source directory marks this provider as "
                            "offering telehealth."
                        ),
                        "source_url": (
                            "https://lgbtqhealthcaredirectory.org/provider/"
                            "provider-one"
                        ),
                        "verified_at": None,
                    }
                ],
            }
        ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            call_command(
                "scrape_lgbtq_directory",
                limit=1,
                output_dir=temporary_directory,
                format="json",
                import_db=True,
            )
            call_command(
                "scrape_lgbtq_directory",
                limit=1,
                output_dir=temporary_directory,
                format="json",
                import_db=True,
            )

        self.assertEqual(ProviderOrganization.objects.count(), 1)
        self.assertEqual(ProviderLocation.objects.count(), 1)
        self.assertEqual(Service.objects.count(), 1)
        self.assertEqual(OrganizationService.objects.count(), 1)
        self.assertEqual(AffirmingFeature.objects.count(), 1)
        self.assertEqual(ProviderFeature.objects.count(), 1)

    @patch(
        "provider_organizations.management.commands."
        "scrape_lgbtq_directory.scrape_providers"
    )
    def test_range_option_passes_start_and_inclusive_limit(
        self, mock_scrape
    ):
        mock_scrape.return_value = []

        with tempfile.TemporaryDirectory() as temporary_directory:
            call_command(
                "scrape_lgbtq_directory",
                provider_range="1001-2000",
                output_dir=temporary_directory,
                format="json",
            )

        mock_scrape.assert_called_once_with(
            limit=1000,
            timeout=30,
            start=1001,
            retries=3,
        )

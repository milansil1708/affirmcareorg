from datetime import datetime, timezone

from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from provider_organizations.models import (
    AffirmingFeature,
    OrganizationService,
    ProviderFeature,
    ProviderLocation,
    ProviderOrganization,
    ProviderOrganizationClaim,
    Service,
)


class ProviderSearchApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.primary_care = Service.objects.create(name="Primary Care")
        self.mental_health = Service.objects.create(name="Mental Health")
        self.informed_consent = AffirmingFeature.objects.create(
            label="Informed consent",
            description="Uses an informed-consent model.",
        )
        self.harm_reduction = AffirmingFeature.objects.create(
            label="Harm reduction",
            description="Uses harm-reduction practices.",
        )

        self.seattle_provider = self.create_provider(
            name="Affirming Health Center",
            org_type="clinic",
            description="Inclusive community healthcare.",
            city="Seattle",
            state_code="WA",
            zip_code="98101",
            wheelchair_accessible=True,
            gender_neutral_restrooms=True,
            public_transit_access=True,
            website_url="https://affirming.example.com",
            booking_url="https://affirming.example.com/book",
            last_verified_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
        )
        self.add_service(
            self.seattle_provider,
            self.primary_care,
            delivery_mode="both",
            age_group="all",
        )
        self.add_feature(self.seattle_provider, self.informed_consent, "yes")
        self.add_feature(self.seattle_provider, self.harm_reduction, "yes")

        self.portland_provider = self.create_provider(
            name="Remote Wellness Network",
            org_type="nonprofit",
            description="Remote behavioral health support.",
            city="Portland",
            state_code="OR",
            zip_code="97205",
        )
        self.add_service(
            self.portland_provider,
            self.mental_health,
            delivery_mode="telehealth",
            age_group="adult",
        )
        self.add_feature(self.portland_provider, self.informed_consent, "unknown")

        self.inactive_provider = self.create_provider(
            name="Inactive Seattle Provider",
            org_type="clinic",
            description="This provider must never be public.",
            city="Seattle",
            state_code="WA",
            zip_code="98102",
            is_active=False,
        )

    def create_provider(
        self,
        *,
        name,
        org_type,
        description,
        city,
        state_code,
        zip_code,
        is_active=True,
        wheelchair_accessible=False,
        gender_neutral_restrooms=False,
        public_transit_access=False,
        website_url=None,
        booking_url=None,
        last_verified_at=None,
    ):
        provider = ProviderOrganization.objects.create(
            name=name,
            org_type=org_type,
            description=description,
            website_url=website_url,
            booking_url=booking_url,
            phone="555-0100",
            email=f"{name.lower().replace(' ', '-')}@example.com",
            is_active=is_active,
            last_verified_at=last_verified_at,
        )
        ProviderLocation.objects.create(
            organization=provider,
            address_line1="100 Main Street",
            city=city,
            state_code=state_code,
            zip_code=zip_code,
            is_primary=True,
            wheelchair_accessible=wheelchair_accessible,
            gender_neutral_restrooms=gender_neutral_restrooms,
            public_transit_notes=public_transit_access,
        )
        return provider

    def add_service(self, provider, service, *, delivery_mode, age_group):
        return OrganizationService.objects.create(
            organization=provider,
            service=service,
            delivery_mode=delivery_mode,
            age_group=age_group,
        )

    def add_feature(self, provider, feature, value):
        return ProviderFeature.objects.create(
            provider=provider,
            feature=feature,
            value=value,
        )

    def search(self, filters=None, **payload):
        data = {"filters": filters or {}, **payload}
        return self.client.post(reverse("provider_search:search"), data, format="json")

    def result_names(self, response):
        return [provider["name"] for provider in response.data["results"]]

    def test_empty_search_returns_only_active_providers_and_public_fields(self):
        ProviderOrganizationClaim.objects.create(
            organization=self.seattle_provider,
            claimant_email="private-claimant@example.com",
            admin_note="Private administrator note",
        )

        response = self.search()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.result_names(response),
            ["Affirming Health Center", "Remote Wellness Network"],
        )
        serialized = response.content.decode()
        self.assertNotIn("Inactive Seattle Provider", serialized)
        self.assertNotIn("private-claimant@example.com", serialized)
        self.assertNotIn("Private administrator note", serialized)
        for private_field in ("user", "is_active", "claim_requests"):
            self.assertNotIn(private_field, response.data["results"][0])
        result = response.data["results"][0]
        self.assertEqual(
            set(result),
            {"slug", "name", "org_type", "primary_location", "services"},
        )
        self.assertEqual(set(result["primary_location"]), {"city", "state_code"})
        self.assertEqual(set(result["services"][0]), {"service"})
        self.assertEqual(
            set(result["services"][0]["service"]),
            {"slug", "name"},
        )

    def test_rejects_unknown_top_level_and_filter_fields(self):
        top_level = self.client.post(
            reverse("provider_search:search"),
            {"filters": {}, "raw_sql": "SELECT * FROM providers"},
            format="json",
        )
        nested = self.search({"insurance": "Blue Cross"})

        self.assertEqual(top_level.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("raw_sql", top_level.data)
        self.assertEqual(nested.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("insurance", nested.data["filters"])

    def test_rejects_invalid_choices_duplicates_and_unknown_catalog_values(self):
        invalid_choice = self.search({"org_types": ["pharmacy"]})
        duplicates = self.search({"org_types": ["clinic", "clinic"]})
        unknown_service = self.search({"service_slugs": ["not-a-service"]})
        unknown_feature = self.search(
            {"affirming_feature_codes": ["not-a-feature"]}
        )

        for response in (
            invalid_choice,
            duplicates,
            unknown_service,
            unknown_feature,
        ):
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filters_by_keyword_organization_and_location(self):
        keyword = self.search({"keyword": "Mental Health"})
        organization = self.search({"org_types": ["nonprofit"]})
        location = self.search(
            {"city": "seattle", "state_code": "wa", "zip_code": "98101"}
        )

        self.assertEqual(self.result_names(keyword), ["Remote Wellness Network"])
        self.assertEqual(
            self.result_names(organization), ["Remote Wellness Network"]
        )
        self.assertEqual(self.result_names(location), ["Affirming Health Center"])

    def test_location_conditions_must_match_the_same_location(self):
        ProviderLocation.objects.create(
            organization=self.portland_provider,
            address_line1="200 Second Street",
            city="Seattle",
            state_code="WA",
            zip_code="98103",
            wheelchair_accessible=False,
        )
        ProviderLocation.objects.create(
            organization=self.portland_provider,
            address_line1="300 Third Street",
            city="Tacoma",
            state_code="WA",
            zip_code="98402",
            wheelchair_accessible=True,
        )

        response = self.search(
            {"city": "Seattle", "wheelchair_accessible": True}
        )

        self.assertEqual(self.result_names(response), ["Affirming Health Center"])

    def test_service_conditions_must_match_the_same_service_record(self):
        self.add_service(
            self.portland_provider,
            self.primary_care,
            delivery_mode="in_person",
            age_group="youth",
        )

        response = self.search(
            {
                "service_slugs": [self.primary_care.slug],
                "delivery_modes": ["telehealth"],
            }
        )

        self.assertEqual(self.result_names(response), [])

    def test_each_requested_affirming_feature_must_be_yes(self):
        response = self.search(
            {
                "affirming_feature_codes": [
                    self.informed_consent.code,
                    self.harm_reduction.code,
                ]
            }
        )

        self.assertEqual(self.result_names(response), ["Affirming Health Center"])

    def test_filters_accessibility_verification_and_url_presence(self):
        response = self.search(
            {
                "wheelchair_accessible": True,
                "gender_neutral_restrooms": True,
                "public_transit_access": True,
                "verified_after": "2026-01-01T00:00:00Z",
                "has_booking_url": True,
                "has_website_url": True,
            }
        )
        missing_booking = self.search({"has_booking_url": False})

        self.assertEqual(self.result_names(response), ["Affirming Health Center"])
        self.assertEqual(
            self.result_names(missing_booking), ["Remote Wellness Network"]
        )

    def test_search_is_paginated_and_supports_allow_listed_sorting(self):
        response = self.client.post(
            f'{reverse("provider_search:search")}?page_size=1&page=2',
            {"filters": {}, "sort": "-name"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["page"], 2)
        self.assertEqual(response.data["page_size"], 1)
        self.assertEqual(self.result_names(response), ["Affirming Health Center"])

        invalid_sort = self.search(sort="user__email")
        self.assertEqual(invalid_sort.status_code, status.HTTP_400_BAD_REQUEST)

    def test_detail_returns_active_provider_with_all_public_locations(self):
        ProviderLocation.objects.create(
            organization=self.seattle_provider,
            address_line1="200 Branch Street",
            city="Tacoma",
            state_code="WA",
            zip_code="98402",
        )

        response = self.client.get(
            reverse("provider_search:detail", args=(self.seattle_provider.slug,))
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Affirming Health Center")
        self.assertEqual(len(response.data["locations"]), 2)
        self.assertEqual(response.data["primary_location"]["city"], "Seattle")
        self.assertNotIn("user", response.data)
        self.assertNotIn("is_active", response.data)

    def test_inactive_provider_detail_is_not_found(self):
        response = self.client.get(
            reverse("provider_search:detail", args=(self.inactive_provider.slug,))
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_options_returns_only_supported_catalog_values(self):
        response = self.client.get(reverse("provider_search:options"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["states"], ["OR", "WA"])
        self.assertEqual(
            {service["slug"] for service in response.data["services"]},
            {self.primary_care.slug, self.mental_health.slug},
        )
        self.assertEqual(
            {feature["code"] for feature in response.data["affirming_features"]},
            {self.informed_consent.code, self.harm_reduction.code},
        )

        with CaptureQueriesContext(connection) as cached_queries:
            cached_response = self.client.get(reverse("provider_search:options"))

        self.assertEqual(cached_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(cached_queries), 0)

    def test_search_serialization_uses_a_bounded_number_of_queries(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.search()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(queries), 4)
        sql = "\n".join(query["sql"].lower() for query in queries)
        self.assertNotIn("providerfeature", sql)
        self.assertNotIn("evidence_note", sql)
        self.assertNotIn("description", sql)

    def test_search_payload_excludes_large_detail_only_values(self):
        long_private_detail = "detail-only-value-" * 1000
        ProviderOrganization.objects.filter(id=self.seattle_provider.id).update(
            description=long_private_detail
        )
        ProviderFeature.objects.filter(provider=self.seattle_provider).update(
            evidence_note=long_private_detail,
            source_url="https://example.com/detail-only-evidence",
        )

        response = self.search()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn(long_private_detail, response.content.decode())
        self.assertLess(len(response.content), 1500)

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from provider_organizations.models import (
    OrganizationService,
    ProviderLocation,
    ProviderOrganization,
    Service,
)


class PublicPagePerformanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.service = Service.objects.create(name="Primary Care")
        cls.providers = []
        for index in range(20):
            provider = ProviderOrganization.objects.create(
                name=f"Provider {index:02d}",
                org_type="clinic",
                description="Affirming care provider.",
                phone="555-0100",
                email=f"provider-{index}@example.com",
                is_active=True,
            )
            ProviderLocation.objects.create(
                organization=provider,
                address_line1="1 Main Street",
                city="Seattle",
                state_code="WA",
                zip_code="98101",
                is_primary=True,
            )
            OrganizationService.objects.create(
                organization=provider,
                service=cls.service,
                delivery_mode="both",
                age_group="all",
            )
            cls.providers.append(provider)

    def test_home_limits_featured_provider_query_before_prefetch(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["featured_providers"]), 6)
        provider_queries = [
            query["sql"]
            for query in queries.captured_queries
            if "provider_organizations_providerorganization" in query["sql"].lower()
        ]
        self.assertTrue(
            any("LIMIT 6" in query.upper() for query in provider_queries),
            provider_queries,
        )

    def test_provider_detail_limits_similar_providers(self):
        response = self.client.get(
            reverse("provider_detail", args=(self.providers[0].slug,))
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["similar_providers"]), 12)
        self.assertTrue(response.context["offers_telehealth"])
        self.assertEqual(
            response.context["canonical_url"],
            f"http://testserver{reverse('provider_detail', args=(self.providers[0].slug,))}",
        )


class CrawlerControlTests(TestCase):
    def test_abusive_crawler_is_rejected_before_database_access(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(
                reverse("home"),
                HTTP_USER_AGENT="Mozilla/5.0 compatible; PetalBot",
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(queries), 0)

    def test_robots_blocks_expensive_and_private_routes(self):
        response = self.client.get(reverse("robots_txt"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User-agent: SemrushBot")
        self.assertContains(response, "Disallow: /chat/")
        self.assertContains(response, "Disallow: /api/chat/")
        self.assertContains(response, "Sitemap: http://testserver/sitemap.xml")

    def test_sitemap_lists_active_provider_only(self):
        active = ProviderOrganization.objects.create(
            name="Active Provider",
            org_type="clinic",
            description="Public listing.",
            phone="555-0101",
            email="active@example.com",
            is_active=True,
        )
        inactive = ProviderOrganization.objects.create(
            name="Inactive Provider",
            org_type="clinic",
            description="Hidden listing.",
            phone="555-0102",
            email="inactive@example.com",
            is_active=False,
        )

        response = self.client.get(reverse("sitemap"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("provider_detail", args=(active.slug,)))
        self.assertNotContains(
            response,
            reverse("provider_detail", args=(inactive.slug,)),
        )

    def test_search_and_chat_pages_are_not_indexed(self):
        results = self.client.get(reverse("provider_results"))
        chat = self.client.get(reverse("provider_chat_pages:chat"))

        self.assertContains(results, 'content="noindex,follow"')
        self.assertContains(chat, 'content="noindex,nofollow"')

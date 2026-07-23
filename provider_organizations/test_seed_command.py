from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from provider_organizations.models import (
    AffirmingFeature,
    ProviderOrganization,
    Service,
)
from provider_organizations.seed_data import SEED_DATA


class SeedProviderOrganizationsCommandTests(TestCase):
    def test_default_seed_is_idempotent(self):
        call_command("seed_provider_organizations", stdout=StringIO())
        first_count = ProviderOrganization.objects.count()

        call_command("seed_provider_organizations", stdout=StringIO())

        self.assertEqual(first_count, len(SEED_DATA["ProviderOrganization"]))
        self.assertEqual(ProviderOrganization.objects.count(), first_count)

    def test_additional_creates_new_provider_copies_on_every_run(self):
        call_command(
            "seed_provider_organizations",
            additional=3,
            stdout=StringIO(),
        )

        generated = ProviderOrganization.objects.filter(
            name__startswith="Test Provider "
        )
        self.assertEqual(generated.count(), 3)
        for provider in generated:
            self.assertTrue(provider.locations.exists())
            self.assertTrue(provider.services.exists())
            self.assertTrue(provider.affirming_features.exists())

        call_command(
            "seed_provider_organizations",
            additional=2,
            stdout=StringIO(),
        )

        self.assertEqual(
            ProviderOrganization.objects.filter(
                name__startswith="Test Provider "
            ).count(),
            5,
        )
        self.assertEqual(Service.objects.count(), len(SEED_DATA["Service"]))
        self.assertEqual(
            AffirmingFeature.objects.count(),
            len(SEED_DATA["AffirmingFeature"]),
        )

    def test_additional_rejects_negative_values(self):
        with self.assertRaisesMessage(
            CommandError,
            "--additional must be zero or greater.",
        ):
            call_command(
                "seed_provider_organizations",
                additional=-1,
                stdout=StringIO(),
            )

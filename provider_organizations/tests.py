from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .claims import ClaimDecisionError, approve_claim, reject_claim
from .models import (
    AffirmingFeature,
    OrganizationService,
    ProviderFeature,
    ProviderLocation,
    ProviderOrganization,
    ProviderOrganizationClaim,
    Service,
)


User = get_user_model()


class ProviderAccountViewTests(TestCase):
    password = "A-secure-password-2026"

    def setUp(self):
        self.user = User.objects.create_user(
            email="provider@example.com",
            password=self.password,
        )
        self.service = Service.objects.create(name="Primary Care")
        self.feature = AffirmingFeature.objects.create(
            label="Gender-neutral restrooms",
            description="Gender-neutral restrooms are available.",
        )

    def organization_data(self, **overrides):
        data = {
            "step": "organization",
            "name": "Affirming Health Center",
            "org_type": "clinic",
            "description": "Inclusive and affirming primary care.",
            "phone": "555-0100",
            "email": "care@example.com",
            "website_url": "https://example.com",
            "booking_url": "https://example.com/book",
        }
        data.update(overrides)
        return data

    def location_data(self, **overrides):
        data = {
            "step": "location",
            "address_line1": "100 Main Street",
            "address_line2": "Suite 200",
            "city": "Seattle",
            "state_code": "WA",
            "zip_code": "98101",
            "wheelchair_accessible": "on",
            "gender_neutral_restrooms": "on",
            "public_transit_notes": "on",
        }
        data.update(overrides)
        return data

    def service_data(self, **overrides):
        data = {
            "step": "services",
            "services-TOTAL_FORMS": "1",
            "services-INITIAL_FORMS": "0",
            "services-MIN_NUM_FORMS": "0",
            "services-MAX_NUM_FORMS": "1000",
            "services-0-service": str(self.service.pk),
            "services-0-delivery_mode": "both",
            "services-0-age_group": "all",
            "services-0-note": "New patients welcome.",
        }
        data.update(overrides)
        return data

    def create_organization(self):
        return ProviderOrganization.objects.create(
            user=self.user,
            name="Affirming Health Center",
            org_type="clinic",
            description="Inclusive and affirming primary care.",
            phone="555-0100",
            email="care@example.com",
            website_url="https://example.com",
            booking_url="https://example.com/book",
            is_active=False,
        )

    def complete_through_services(self):
        organization = self.create_organization()
        ProviderLocation.objects.create(
            organization=organization,
            address_line1="100 Main Street",
            city="Seattle",
            state_code="WA",
            zip_code="98101",
            is_primary=True,
        )
        OrganizationService.objects.create(
            organization=organization,
            service=self.service,
            delivery_mode="both",
            age_group="all",
        )
        return organization

    def test_account_page_requires_login(self):
        response = self.client.get(reverse("provider_account"))

        self.assertRedirects(
            response,
            f"{reverse('users:login')}?next={reverse('provider_account')}",
        )

    def test_organization_step_creates_inactive_profile_and_advances(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("provider_account"),
            self.organization_data(),
        )

        organization = ProviderOrganization.objects.get(user=self.user)
        self.assertFalse(organization.is_active)
        self.assertRedirects(
            response,
            f"{reverse('provider_account')}?step=location",
        )

    def test_account_resumes_at_first_incomplete_step(self):
        self.create_organization()
        self.client.force_login(self.user)

        response = self.client.get(reverse("provider_account"))

        self.assertContains(response, 'name="step" value="location"')
        self.assertContains(response, "Provider location")

    def test_future_step_is_blocked_until_prerequisites_are_complete(self):
        self.create_organization()
        self.client.force_login(self.user)

        response = self.client.get(f"{reverse('provider_account')}?step=features")

        self.assertContains(response, 'name="step" value="location"')
        self.assertNotContains(response, 'name="step" value="features"')

    def test_location_step_creates_primary_location_and_advances(self):
        organization = self.create_organization()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("provider_account"),
            self.location_data(),
        )

        location = ProviderLocation.objects.get(organization=organization)
        self.assertTrue(location.is_primary)
        self.assertEqual(location.city, "Seattle")
        self.assertRedirects(
            response,
            f"{reverse('provider_account')}?step=services",
        )

    def test_services_step_creates_organization_service_and_advances(self):
        organization = self.create_organization()
        ProviderLocation.objects.create(
            organization=organization,
            address_line1="100 Main Street",
            city="Seattle",
            state_code="WA",
            zip_code="98101",
            is_primary=True,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("provider_account"),
            self.service_data(),
        )

        organization_service = OrganizationService.objects.get(
            organization=organization
        )
        self.assertEqual(organization_service.service, self.service)
        self.assertEqual(organization_service.delivery_mode, "both")
        self.assertRedirects(
            response,
            f"{reverse('provider_account')}?step=features",
        )

    def test_services_step_requires_at_least_one_service(self):
        organization = self.complete_through_services()
        organization.services.all().delete()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("provider_account"),
            self.service_data(
                **{
                    "services-0-service": "",
                    "services-0-delivery_mode": "",
                    "services-0-age_group": "",
                    "services-0-note": "",
                }
            ),
        )

        self.assertContains(response, "Add at least one service.")
        self.assertFalse(organization.services.exists())

    def test_features_step_completes_and_activates_profile(self):
        organization = self.complete_through_services()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("provider_account"),
            {
                "step": "features",
                "features": [str(self.feature.pk)],
            },
        )

        organization.refresh_from_db()
        provider_feature = ProviderFeature.objects.get(provider=organization)
        self.assertEqual(provider_feature.feature, self.feature)
        self.assertEqual(provider_feature.value, "yes")
        self.assertTrue(organization.is_active)
        self.assertRedirects(
            response,
            f"{reverse('provider_account')}?step=features",
        )

    def test_completed_account_allows_sidebar_edits_without_advancing(self):
        organization = self.complete_through_services()
        ProviderFeature.objects.create(
            provider=organization,
            feature=self.feature,
            value="yes",
        )
        organization.is_active = True
        organization.save(update_fields=("is_active",))
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("provider_account"),
            self.organization_data(name="Updated Health Center"),
        )

        organization.refresh_from_db()
        self.assertEqual(organization.name, "Updated Health Center")
        self.assertRedirects(
            response,
            f"{reverse('provider_account')}?step=organization",
        )

        page = self.client.get(reverse("provider_account"))
        self.assertContains(page, "Account settings")
        self.assertContains(page, "Save changes")
        self.assertNotContains(page, "Save and continue")

    def test_update_is_scoped_to_current_users_organization(self):
        organization = self.create_organization()
        other_user = User.objects.create_user(
            email="other@example.com",
            password=self.password,
        )
        other_organization = ProviderOrganization.objects.create(
            user=other_user,
            name="Other Provider",
            org_type="clinic",
            description="Other provider description.",
            phone="555-0199",
            email="other-care@example.com",
        )
        self.client.force_login(self.user)

        self.client.post(
            reverse("provider_account"),
            self.organization_data(name="Updated Health Center"),
        )

        organization.refresh_from_db()
        other_organization.refresh_from_db()
        self.assertEqual(organization.name, "Updated Health Center")
        self.assertEqual(other_organization.name, "Other Provider")

    def test_invalid_step_shows_field_errors_and_error_toast(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("provider_account"),
            self.organization_data(email="not-an-email"),
        )

        self.assertFalse(
            ProviderOrganization.objects.filter(user=self.user).exists()
        )
        self.assertContains(response, "Enter a valid email address.")
        self.assertContains(response, "Please correct the errors below")
        self.assertContains(response, "account-toast-error")

    def test_authenticated_header_account_link_targets_account_page(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertContains(response, reverse("provider_account"))


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    CLAIM_ADMIN_EMAIL="claims-admin@example.com",
    DEFAULT_FROM_EMAIL="noreply@example.com",
)
class ProviderOrganizationClaimTests(TestCase):
    password = "A-secure-password-2026"

    def setUp(self):
        self.claimant = User.objects.create_user(
            email="claimant@example.com",
            password=self.password,
        )
        self.reviewer = User.objects.create_superuser(
            email="reviewer@example.com",
            password=self.password,
        )
        self.organization = ProviderOrganization.objects.create(
            name="North Star Community Health",
            org_type="clinic",
            description="Inclusive community health services.",
            phone="555-0130",
            email="north-star@example.com",
        )

    def detail_url(self):
        return reverse("provider_detail", args=(self.organization.slug,))

    def claim_url(self):
        return reverse(
            "claim_provider_organization",
            args=(self.organization.slug,),
        )

    def create_claim(self, claimant=None):
        claimant = claimant or self.claimant
        return ProviderOrganizationClaim.objects.create(
            organization=self.organization,
            claimant=claimant,
            claimant_email=claimant.email,
        )

    def test_unclaimed_organization_shows_claim_action(self):
        response = self.client.get(self.detail_url())

        self.assertContains(response, "Claim this organization")
        self.assertContains(response, "cdn.jsdelivr.net/npm/sweetalert2")

    def test_owned_organization_hides_claim_action(self):
        self.organization.user = self.claimant
        self.organization.save(update_fields=("user",))

        response = self.client.get(self.detail_url())

        self.assertNotContains(response, "Claim this organization")
        self.assertNotContains(response, "Unclaimed organization")

    def test_anonymous_claim_submission_redirects_to_login(self):
        response = self.client.post(self.claim_url())

        expected = f"{reverse('users:login')}?next={self.claim_url()}"
        self.assertRedirects(response, expected, fetch_redirect_response=False)
        self.assertFalse(ProviderOrganizationClaim.objects.exists())

    def test_claim_submission_creates_one_request_and_emails_admin(self):
        self.client.force_login(self.claimant)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.claim_url())

        claim = ProviderOrganizationClaim.objects.get()
        self.assertRedirects(response, self.detail_url())
        self.assertEqual(claim.claimant, self.claimant)
        self.assertEqual(claim.claimant_email, self.claimant.email)
        self.assertEqual(claim.status, ProviderOrganizationClaim.Status.PENDING)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["claims-admin@example.com"])
        self.assertIn(self.organization.name, mail.outbox[0].subject)

        page = self.client.get(self.detail_url())
        self.assertContains(page, "awaiting administrator review")
        self.assertNotContains(page, "Claim this organization")

    def test_duplicate_submission_does_not_create_or_email_again(self):
        self.client.force_login(self.claimant)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.claim_url())
        mail.outbox.clear()

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.claim_url())

        self.assertRedirects(response, self.detail_url())
        self.assertEqual(ProviderOrganizationClaim.objects.count(), 1)
        self.assertEqual(mail.outbox, [])

    def test_pending_claim_for_another_organization_blocks_new_claim(self):
        other_organization = ProviderOrganization.objects.create(
            name="Existing Pending Claim Provider",
            org_type="nonprofit",
            description="The claimant has already requested this organization.",
            phone="555-0188",
            email="pending@example.com",
        )
        ProviderOrganizationClaim.objects.create(
            organization=other_organization,
            claimant=self.claimant,
            claimant_email=self.claimant.email,
        )
        self.client.force_login(self.claimant)

        page = self.client.get(self.detail_url())

        self.assertContains(page, other_organization.name)
        self.assertContains(page, "Another claim is under review")
        self.assertNotContains(page, "Claim this organization")

        response = self.client.post(self.claim_url())

        self.assertRedirects(response, self.detail_url())
        self.assertEqual(
            ProviderOrganizationClaim.objects.filter(
                claimant=self.claimant,
                status=ProviderOrganizationClaim.Status.PENDING,
            ).count(),
            1,
        )
        self.assertFalse(
            ProviderOrganizationClaim.objects.filter(
                claimant=self.claimant,
                organization=self.organization,
            ).exists()
        )

    def test_rejected_claim_does_not_block_a_new_claim(self):
        other_organization = ProviderOrganization.objects.create(
            name="Rejected Claim Provider",
            org_type="hospital_program",
            description="A previously rejected organization claim.",
            phone="555-0177",
            email="rejected@example.com",
        )
        ProviderOrganizationClaim.objects.create(
            organization=other_organization,
            claimant=self.claimant,
            claimant_email=self.claimant.email,
            status=ProviderOrganizationClaim.Status.REJECTED,
        )
        self.client.force_login(self.claimant)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.claim_url())

        self.assertRedirects(response, self.detail_url())
        self.assertTrue(
            ProviderOrganizationClaim.objects.filter(
                claimant=self.claimant,
                organization=self.organization,
                status=ProviderOrganizationClaim.Status.PENDING,
            ).exists()
        )

    def test_claimant_with_another_organization_cannot_submit(self):
        ProviderOrganization.objects.create(
            user=self.claimant,
            name="Existing Provider",
            org_type="private_practice",
            description="An existing provider account.",
            phone="555-0199",
            email="existing@example.com",
        )
        self.client.force_login(self.claimant)

        response = self.client.post(self.claim_url())

        self.assertRedirects(response, self.detail_url())
        self.assertFalse(ProviderOrganizationClaim.objects.exists())
        page = self.client.get(self.detail_url())
        self.assertContains(page, "account already manages")
        self.assertNotContains(page, "Claim this organization")

    def test_approving_claim_assigns_owner_and_notifies_claimant(self):
        claim = self.create_claim()

        with self.captureOnCommitCallbacks(execute=True):
            approved_claim = approve_claim(
                claim.pk,
                self.reviewer,
                "Identity and employment were verified.",
            )

        self.organization.refresh_from_db()
        approved_claim.refresh_from_db()
        self.assertEqual(self.organization.user, self.claimant)
        self.assertEqual(
            approved_claim.status,
            ProviderOrganizationClaim.Status.APPROVED,
        )
        self.assertEqual(approved_claim.reviewed_by, self.reviewer)
        self.assertIsNotNone(approved_claim.reviewed_at)
        self.assertEqual(mail.outbox[0].to, [self.claimant.email])
        self.assertIn("approved", mail.outbox[0].subject)
        self.assertIn("Identity and employment were verified.", mail.outbox[0].body)

    def test_approval_rejects_and_notifies_competing_claimants(self):
        competing_user = User.objects.create_user(
            email="competing@example.com",
            password=self.password,
        )
        approved_claim = self.create_claim()
        competing_claim = self.create_claim(competing_user)

        with self.captureOnCommitCallbacks(execute=True):
            approve_claim(approved_claim.pk, self.reviewer)

        competing_claim.refresh_from_db()
        self.assertEqual(
            competing_claim.status,
            ProviderOrganizationClaim.Status.REJECTED,
        )
        self.assertIn("Another claim", competing_claim.admin_note)
        self.assertCountEqual(
            [message.to[0] for message in mail.outbox],
            [self.claimant.email, competing_user.email],
        )

    def test_approval_fails_if_organization_was_claimed_in_the_meantime(self):
        claim = self.create_claim()
        other_owner = User.objects.create_user(
            email="owner@example.com",
            password=self.password,
        )
        self.organization.user = other_owner
        self.organization.save(update_fields=("user",))

        with self.assertRaisesMessage(
            ClaimDecisionError,
            "This organization already has an owner.",
        ):
            approve_claim(claim.pk, self.reviewer)

        claim.refresh_from_db()
        self.assertEqual(claim.status, ProviderOrganizationClaim.Status.PENDING)
        self.assertEqual(mail.outbox, [])

    def test_rejecting_claim_records_decision_and_notifies_claimant(self):
        claim = self.create_claim()

        with self.captureOnCommitCallbacks(execute=True):
            rejected_claim = reject_claim(
                claim.pk,
                self.reviewer,
                "The submitted details could not be verified.",
            )

        rejected_claim.refresh_from_db()
        self.organization.refresh_from_db()
        self.assertEqual(
            rejected_claim.status,
            ProviderOrganizationClaim.Status.REJECTED,
        )
        self.assertEqual(rejected_claim.reviewed_by, self.reviewer)
        self.assertIsNone(self.organization.user)
        self.assertEqual(mail.outbox[0].to, [self.claimant.email])
        self.assertIn(
            "The submitted details could not be verified.",
            mail.outbox[0].body,
        )

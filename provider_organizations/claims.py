import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import ProviderOrganization, ProviderOrganizationClaim


logger = logging.getLogger(__name__)


class ClaimDecisionError(Exception):
    pass


def _send_email(subject, message, recipients):
    recipients = [email for email in recipients if email]
    if not recipients:
        logger.warning("Provider claim email skipped because no recipient is configured.")
        return

    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            recipients,
            fail_silently=False,
        )
    except Exception:
        logger.exception("Provider claim email could not be sent.")


def notify_admin_of_claim(claim, request=None):
    if request:
        admin_path = reverse(
            "admin:provider_organizations_providerorganizationclaim_change",
            args=(claim.pk,),
        )
        admin_url = request.build_absolute_uri(admin_path)
    else:
        admin_url = ""

    message = (
        f"A provider organization claim requires review.\n\n"
        f"Organization: {claim.organization.name}\n"
        f"Claimant: {claim.claimant_email}\n"
        f"Submitted: {claim.created_at:%Y-%m-%d %H:%M UTC}\n"
    )
    if admin_url:
        message += f"\nReview claim: {admin_url}\n"

    _send_email(
        f"Provider claim request: {claim.organization.name}",
        message,
        [settings.CLAIM_ADMIN_EMAIL or settings.EMAIL_HOST_USER],
    )


def notify_claimant_of_decision(claim):
    if claim.status == ProviderOrganizationClaim.Status.APPROVED:
        subject = f"Your claim for {claim.organization.name} was approved"
        decision = (
            "Your claim was approved. The organization is now connected to your "
            "Affirm Care account, and you can manage it from the Account page."
        )
    else:
        subject = f"Update on your claim for {claim.organization.name}"
        decision = (
            "Your claim was not approved. The organization has not been connected "
            "to your account."
        )

    if claim.admin_note:
        decision += f"\n\nAdministrator note:\n{claim.admin_note}"

    _send_email(
        subject,
        f"Hello,\n\n{decision}\n\nAffirm Care",
        [claim.claimant_email],
    )


def approve_claim(claim_id, reviewer, admin_note=""):
    with transaction.atomic():
        claim = (
            ProviderOrganizationClaim.objects.select_for_update()
            .select_related("organization")
            .get(pk=claim_id)
        )
        organization = ProviderOrganization.objects.select_for_update().get(
            pk=claim.organization_id
        )

        if claim.status != ProviderOrganizationClaim.Status.PENDING:
            raise ClaimDecisionError("Only pending claims can be approved.")
        if claim.claimant is None:
            raise ClaimDecisionError("The claimant account no longer exists.")
        if organization.user_id and organization.user_id != claim.claimant_id:
            raise ClaimDecisionError("This organization already has an owner.")
        if (
            ProviderOrganization.objects.filter(user=claim.claimant)
            .exclude(pk=organization.pk)
            .exists()
        ):
            raise ClaimDecisionError(
                "The claimant already manages another provider organization."
            )

        organization.user = claim.claimant
        organization.save(update_fields=("user",))

        reviewed_at = timezone.now()
        claim.status = ProviderOrganizationClaim.Status.APPROVED
        claim.reviewed_by = reviewer
        claim.reviewed_at = reviewed_at
        claim.admin_note = admin_note
        claim.save(
            update_fields=("status", "reviewed_by", "reviewed_at", "admin_note")
        )

        competing_claims = list(
            ProviderOrganizationClaim.objects.select_for_update()
            .filter(
                organization=organization,
                status=ProviderOrganizationClaim.Status.PENDING,
            )
            .exclude(pk=claim.pk)
        )
        for competing_claim in competing_claims:
            competing_claim.status = ProviderOrganizationClaim.Status.REJECTED
            competing_claim.reviewed_by = reviewer
            competing_claim.reviewed_at = reviewed_at
            competing_claim.admin_note = (
                "Another claim for this organization was approved."
            )
            competing_claim.save(
                update_fields=(
                    "status",
                    "reviewed_by",
                    "reviewed_at",
                    "admin_note",
                )
            )

        transaction.on_commit(lambda: notify_claimant_of_decision(claim))
        for competing_claim in competing_claims:
            transaction.on_commit(
                lambda rejected_claim=competing_claim: notify_claimant_of_decision(
                    rejected_claim
                )
            )

    return claim


def reject_claim(claim_id, reviewer, admin_note=""):
    with transaction.atomic():
        claim = ProviderOrganizationClaim.objects.select_for_update().get(pk=claim_id)
        if claim.status != ProviderOrganizationClaim.Status.PENDING:
            raise ClaimDecisionError("Only pending claims can be rejected.")

        claim.status = ProviderOrganizationClaim.Status.REJECTED
        claim.reviewed_by = reviewer
        claim.reviewed_at = timezone.now()
        claim.admin_note = admin_note
        claim.save(
            update_fields=("status", "reviewed_by", "reviewed_at", "admin_note")
        )
        transaction.on_commit(lambda: notify_claimant_of_decision(claim))

    return claim

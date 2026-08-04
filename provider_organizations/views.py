from urllib.parse import quote_plus

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from provider_search.services import public_provider_card_queryset

from .claims import notify_admin_of_claim
from .forms import (
    OrganizationServiceFormSet,
    ProviderFeatureSelectionForm,
    ProviderLocationForm,
    ProviderOrganizationForm,
)
from .models import (
    ProviderOrganization,
    ProviderOrganizationClaim,
)


ACCOUNT_STEPS = (
    ("organization", "Provider information", "Organization and contact details"),
    ("location", "Provider location", "Primary location and accessibility"),
    ("services", "Services", "Care offered and delivery details"),
    ("features", "Affirming features", "Inclusive facilities and practices"),
)


def provider_detail_view(request, slug):
    provider = get_object_or_404(
        public_provider_card_queryset(),
        slug=slug,
    )

    provider_services = list(provider.services.all())
    provider_locations = list(provider.locations.all())
    primary_location = provider_locations[0] if provider_locations else None
    if primary_location:
        if primary_location.latitude and primary_location.longitude:
            map_query = f"{primary_location.latitude},{primary_location.longitude}"
        else:
            full_address = ", ".join(
                filter(
                    None,
                    [
                        primary_location.address_line1,
                        primary_location.address_line2,
                        primary_location.city,
                        primary_location.state_code,
                        primary_location.zip_code,
                    ],
                )
            )
            map_query = full_address
        map_embed_url = f"https://www.google.com/maps?q={quote_plus(map_query)}&output=embed"
    else:
        map_embed_url = None

    provider_service_ids = {service.service_id for service in provider_services}
    similar_queryset = (
        public_provider_card_queryset()
        .filter(
            services__service_id__in=provider_service_ids,
        )
        .exclude(id=provider.id)
        .annotate(
            shared_service_count=Count(
                "services__service_id",
                distinct=True,
            )
        )
        .order_by("-shared_service_count", "name", "id")[:12]
    )
    similar_providers = list(similar_queryset)

    offers_telehealth = any(
        service.delivery_mode in {"telehealth", "both"}
        for service in provider_services
    )
    current_claim = None
    pending_claim = None
    claimant_has_other_organization = False
    if request.user.is_authenticated and provider.user_id is None:
        pending_claim = request.user.provider_claim_requests.filter(
            status=ProviderOrganizationClaim.Status.PENDING,
        ).select_related("organization").first()
        current_claim = provider.claim_requests.filter(
            claimant=request.user,
            status=ProviderOrganizationClaim.Status.PENDING,
        ).first()
        claimant_has_other_organization = (
            request.user.provider_organizations.exclude(pk=provider.pk).exists()
        )

    context = {
        "provider": provider,
        "primary_location": primary_location,
        "map_embed_url": map_embed_url,
        "offers_telehealth": offers_telehealth,
        "similar_providers": similar_providers,
        "current_claim": current_claim,
        "pending_claim": pending_claim,
        "claimant_has_other_organization": claimant_has_other_organization,
        "canonical_url": request.build_absolute_uri(
            reverse("provider_detail", args=(provider.slug,))
        ),
    }
    return render(request, "pages/provider_detail.html", context)


@login_required
@require_POST
def claim_provider_organization_view(request, slug):
    provider = get_object_or_404(
        ProviderOrganization.objects.filter(is_active=True),
        slug=slug,
    )

    if provider.user_id is not None:
        messages.error(
            request,
            "This organization has already been claimed.",
        )
        return redirect("provider_detail", slug=provider.slug)

    if request.user.provider_organizations.exclude(pk=provider.pk).exists():
        messages.error(
            request,
            "Your account already manages a provider organization.",
        )
        return redirect("provider_detail", slug=provider.slug)

    pending_claim = (
        request.user.provider_claim_requests.filter(
            status=ProviderOrganizationClaim.Status.PENDING,
        )
        .select_related("organization")
        .first()
    )
    if pending_claim:
        if pending_claim.organization_id == provider.pk:
            messages.info(
                request,
                "You already have a pending claim for this organization.",
            )
        else:
            messages.error(
                request,
                "You already have a pending claim for "
                f"{pending_claim.organization.name}. Wait for an administrator "
                "decision before claiming another organization.",
            )
        return redirect("provider_detail", slug=provider.slug)

    try:
        claim = ProviderOrganizationClaim.objects.create(
            organization=provider,
            claimant=request.user,
            claimant_email=request.user.email,
        )
    except IntegrityError:
        pending_claim = ProviderOrganizationClaim.objects.filter(
            claimant=request.user,
            status=ProviderOrganizationClaim.Status.PENDING,
        ).select_related("organization").first()
        if pending_claim and pending_claim.organization_id == provider.pk:
            message = "You already have a pending claim for this organization."
        else:
            message = (
                "You already have a pending claim. Wait for an administrator "
                "decision before claiming another organization."
            )
        messages.error(request, message)
        return redirect("provider_detail", slug=provider.slug)

    transaction.on_commit(lambda: notify_admin_of_claim(claim, request))
    messages.success(
        request,
        "Your claim request was submitted for administrator review.",
    )

    return redirect("provider_detail", slug=provider.slug)


@login_required
def provider_account_view(request):
    organization = (
        ProviderOrganization.objects.filter(user=request.user).order_by("pk").first()
    )
    primary_location = (
        organization.locations.order_by("-is_primary", "pk").first()
        if organization
        else None
    )

    completion = {
        "organization": organization is not None,
        "location": primary_location is not None,
        "services": bool(organization and organization.services.exists()),
        "features": bool(
            organization and organization.affirming_features.filter(value="yes").exists()
        ),
    }
    is_complete = all(completion.values())
    first_incomplete = next(
        (key for key, _, _ in ACCOUNT_STEPS if not completion[key]),
        "organization",
    )

    requested_step = request.POST.get("step") or request.GET.get("step")
    step_keys = [key for key, _, _ in ACCOUNT_STEPS]
    active_step = requested_step if requested_step in step_keys else first_incomplete

    if not is_complete:
        first_incomplete_index = step_keys.index(first_incomplete)
        if step_keys.index(active_step) > first_incomplete_index:
            active_step = first_incomplete

    form = None
    service_formset = None

    if active_step == "organization":
        form = ProviderOrganizationForm(
            request.POST or None,
            instance=organization,
        )
    elif active_step == "location":
        form = ProviderLocationForm(
            request.POST or None,
            instance=primary_location,
        )
    elif active_step == "services":
        service_formset = OrganizationServiceFormSet(
            request.POST or None,
            instance=organization,
            prefix="services",
        )
    else:
        form = ProviderFeatureSelectionForm(
            request.POST or None,
            organization=organization,
        )

    if request.method == "POST":
        is_valid = service_formset.is_valid() if service_formset else form.is_valid()
        if is_valid:
            with transaction.atomic():
                if active_step == "organization":
                    is_new_organization = organization is None
                    organization = form.save(commit=False)
                    organization.user = request.user
                    if is_new_organization:
                        organization.is_active = False
                    organization.save()
                elif active_step == "location":
                    location = form.save(commit=False)
                    location.organization = organization
                    location.is_primary = True
                    location.save()
                    organization.locations.exclude(pk=location.pk).update(
                        is_primary=False
                    )
                elif active_step == "services":
                    service_formset.save()
                else:
                    form.save()

            updated_completion = {
                "organization": True,
                "location": organization.locations.exists(),
                "services": organization.services.exists(),
                "features": organization.affirming_features.filter(value="yes").exists(),
            }
            now_complete = all(updated_completion.values())
            if now_complete and not organization.is_active:
                organization.is_active = True
                organization.save(update_fields=("is_active",))
            messages.success(request, "Your provider account has been saved.")

            if is_complete or now_complete:
                return redirect(f"{reverse('provider_account')}?step={active_step}")

            current_index = step_keys.index(active_step)
            next_step = step_keys[current_index + 1]
            return redirect(f"{reverse('provider_account')}?step={next_step}")

        messages.error(request, "Please correct the errors below and try again.")

    step_items = []
    first_incomplete_index = step_keys.index(first_incomplete)
    for key, title, subtitle in ACCOUNT_STEPS:
        index = step_keys.index(key)
        step_items.append(
            {
                "key": key,
                "title": title,
                "subtitle": subtitle,
                "complete": completion[key],
                "active": key == active_step,
                "available": is_complete or index <= first_incomplete_index,
            }
        )

    active_index = step_keys.index(active_step)
    previous_step = step_keys[active_index - 1] if active_index > 0 else None

    return render(
        request,
        "provider_organizations/account.html",
        {
            "form": form,
            "service_formset": service_formset,
            "organization": organization,
            "active_step": active_step,
            "steps": step_items,
            "is_complete": is_complete,
            "previous_step": previous_step,
            "step_number": active_index + 1,
            "step_count": len(ACCOUNT_STEPS),
        },
    )

import random

from django.db.models import Prefetch, Q
from django.views.generic import TemplateView

from provider_organizations.models import (
    AffirmingFeature,
    ProviderLocation,
    ProviderOrganization,
    Service,
)


class HomeView(TemplateView):
    template_name = "pages/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        keyword = self.request.GET.get("keyword", "").strip()
        state = self.request.GET.get("state", "").strip()
        service_slug = self.request.GET.get("service", "").strip()
        selected_features = [f for f in self.request.GET.getlist("features") if f]
        is_search = any([keyword, state, service_slug, selected_features])

        base_queryset = ProviderOrganization.objects.filter(is_active=True).prefetch_related(
            Prefetch(
                "locations",
                queryset=ProviderLocation.objects.order_by("-is_primary", "id"),
            ),
            Prefetch("services__service"),
        )

        if is_search:
            providers = base_queryset
            if keyword:
                providers = providers.filter(
                    Q(name__icontains=keyword) | Q(description__icontains=keyword)
                )
            if state:
                providers = providers.filter(locations__state_code__iexact=state)
            if service_slug:
                providers = providers.filter(services__service__slug=service_slug)
            if selected_features:
                providers = providers.filter(
                    affirming_features__feature__code__in=selected_features,
                    affirming_features__value="yes",
                )

            providers = providers.distinct()
            featured_providers = None
        else:
            providers = None
            featured_providers = list(base_queryset.distinct())
            random.shuffle(featured_providers)
            featured_providers = featured_providers[:6]

        states = (
            ProviderLocation.objects.exclude(state_code__isnull=True)
            .exclude(state_code__exact="")
            .order_by("state_code")
            .values_list("state_code", flat=True)
            .distinct()
        )

        context.update(
            {
                "providers": providers,
                "featured_providers": featured_providers,
                "services": Service.objects.order_by("name"),
                "affirming_features": AffirmingFeature.objects.order_by("label"),
                "states": states,
                "is_search": is_search,
                "selected_keyword": keyword,
                "selected_state": state,
                "selected_service": service_slug,
                "selected_features": selected_features,
            }
        )
        return context


about_view = TemplateView.as_view(template_name="pages/about.html")

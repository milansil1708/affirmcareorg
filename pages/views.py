from django.core.paginator import Paginator
from django.http import HttpResponse
from django.urls import reverse
from django.views.generic import TemplateView

from provider_organizations.models import AffirmingFeature, ProviderLocation, Service
from provider_search.services import (
    SORT_EXPRESSIONS,
    public_provider_card_queryset,
    search_providers,
)


PROVIDER_RESULTS_PAGE_SIZE = 12
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def _clean_values(query, *names):
    values = []
    for name in names:
        values.extend(query.getlist(name))
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _boolean_filter(query, name):
    if name not in query:
        return None
    value = query.get(name, "").strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    return None


def provider_search_state(request):
    query = request.GET
    keyword = query.get("keyword", "").strip()
    state = (query.get("state") or query.get("state_code") or "").strip()
    city = query.get("city", "").strip()
    zip_code = query.get("zip_code", "").strip()
    service_slugs = _clean_values(query, "service", "service_slugs")
    selected_features = _clean_values(
        query,
        "features",
        "affirming_feature_codes",
    )
    org_types = _clean_values(query, "org_type", "org_types")
    delivery_modes = _clean_values(query, "delivery_mode", "delivery_modes")
    age_groups = _clean_values(query, "age_group", "age_groups")

    filters = {}
    scalar_filters = {
        "keyword": keyword,
        "state_code": state,
        "city": city,
        "zip_code": zip_code,
        "verified_after": query.get("verified_after", "").strip(),
    }
    filters.update({key: value for key, value in scalar_filters.items() if value})

    list_filters = {
        "service_slugs": service_slugs,
        "affirming_feature_codes": selected_features,
        "org_types": org_types,
        "delivery_modes": delivery_modes,
        "age_groups": age_groups,
    }
    filters.update({key: value for key, value in list_filters.items() if value})

    for name in (
        "wheelchair_accessible",
        "gender_neutral_restrooms",
        "public_transit_access",
        "has_booking_url",
        "has_website_url",
    ):
        value = _boolean_filter(query, name)
        if value is not None:
            filters[name] = value

    sort = query.get("sort", "name")
    if sort not in SORT_EXPRESSIONS:
        sort = "name"

    return {
        "filters": filters,
        "sort": sort,
        "is_search": bool(filters),
        "selected_keyword": keyword,
        "selected_state": state,
        "selected_service": service_slugs[0] if service_slugs else "",
        "selected_features": selected_features,
    }


def paginated_provider_context(request, providers):
    page_obj = Paginator(providers, PROVIDER_RESULTS_PAGE_SIZE).get_page(
        request.GET.get("page")
    )
    pagination_query = request.GET.copy()
    pagination_query.pop("page", None)
    return {
        "providers": page_obj,
        "page_obj": page_obj,
        "provider_count": page_obj.paginator.count,
        "pagination_query": pagination_query.urlencode(),
    }


class HomeView(TemplateView):
    template_name = "pages/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_state = provider_search_state(self.request)

        if search_state["is_search"]:
            providers = search_providers(
                search_state["filters"],
                search_state["sort"],
            )
            result_context = paginated_provider_context(self.request, providers)
            featured_providers = None
        else:
            result_context = {
                "providers": None,
                "page_obj": None,
                "provider_count": 0,
                "pagination_query": "",
            }
            featured_providers = list(
                public_provider_card_queryset().order_by("?")[:6]
            )

        states = (
            ProviderLocation.objects.exclude(state_code__isnull=True)
            .exclude(state_code__exact="")
            .order_by("state_code")
            .values_list("state_code", flat=True)
            .distinct()
        )

        context.update(search_state)
        context.update(result_context)
        context.update(
            {
                "featured_providers": featured_providers,
                "services": Service.objects.order_by("name"),
                "affirming_features": AffirmingFeature.objects.order_by("label"),
                "states": states,
                "show_results_heading": True,
                "canonical_url": self.request.build_absolute_uri(reverse("home")),
            }
        )
        return context


class ProviderResultsView(TemplateView):
    template_name = "pages/provider_results.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_state = provider_search_state(self.request)
        providers = search_providers(
            search_state["filters"],
            search_state["sort"],
        )
        context.update(search_state)
        context.update(paginated_provider_context(self.request, providers))
        context["show_results_heading"] = False
        context["canonical_url"] = self.request.build_absolute_uri(
            reverse("provider_results")
        )
        return context


about_view = TemplateView.as_view(template_name="pages/about.html")


def robots_txt(request):
    sitemap_url = request.build_absolute_uri(reverse("sitemap"))
    body = "\n".join(
        (
            "User-agent: SemrushBot",
            "Disallow: /",
            "",
            "User-agent: PetalBot",
            "Disallow: /",
            "",
            "User-agent: *",
            "Disallow: /admin/",
            "Disallow: /api/chat/",
            "Disallow: /chat/",
            "Disallow: /users/",
            f"Sitemap: {sitemap_url}",
            "",
        )
    )
    return HttpResponse(body, content_type="text/plain; charset=utf-8")

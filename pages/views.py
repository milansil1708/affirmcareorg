import urllib.request
import xml.etree.ElementTree as ET

from django.core.cache import cache
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.urls import reverse
from django.views.generic import TemplateView

from provider_search.services import (
    SORT_EXPRESSIONS,
    get_featured_providers,
    get_public_directory_catalog,
    search_providers,
)


PROVIDER_RESULTS_PAGE_SIZE = 12

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def _clean_values(query, *names):
    values = []

    for name in names:
        values.extend(query.getlist(name))

    return list(
        dict.fromkeys(
            value.strip()
            for value in values
            if value.strip()
        )
    )


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
    state = (
        query.get("state")
        or query.get("state_code")
        or ""
    ).strip()
    city = query.get("city", "").strip()
    zip_code = query.get("zip_code", "").strip()

    service_slugs = _clean_values(
        query,
        "service",
        "service_slugs",
    )

    selected_features = _clean_values(
        query,
        "features",
        "affirming_feature_codes",
    )

    org_types = _clean_values(
        query,
        "org_type",
        "org_types",
    )

    delivery_modes = _clean_values(
        query,
        "delivery_mode",
        "delivery_modes",
    )

    age_groups = _clean_values(
        query,
        "age_group",
        "age_groups",
    )

    filters = {}

    scalar_filters = {
        "keyword": keyword,
        "state_code": state,
        "city": city,
        "zip_code": zip_code,
        "verified_after": query.get(
            "verified_after",
            "",
        ).strip(),
    }

    filters.update(
        {
            key: value
            for key, value in scalar_filters.items()
            if value
        }
    )

    list_filters = {
        "service_slugs": service_slugs,
        "affirming_feature_codes": selected_features,
        "org_types": org_types,
        "delivery_modes": delivery_modes,
        "age_groups": age_groups,
    }

    filters.update(
        {
            key: value
            for key, value in list_filters.items()
            if value
        }
    )

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
        "selected_service": (
            service_slugs[0]
            if service_slugs
            else ""
        ),
        "selected_features": selected_features,
    }


def paginated_provider_context(request, providers):
    page_obj = Paginator(
        providers,
        PROVIDER_RESULTS_PAGE_SIZE,
    ).get_page(
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

        search_state = provider_search_state(
            self.request
        )

        if search_state["is_search"]:
            providers = search_providers(
                search_state["filters"],
                search_state["sort"],
            )

            result_context = paginated_provider_context(
                self.request,
                providers,
            )

            featured_providers = None

        else:
            result_context = {
                "providers": None,
                "page_obj": None,
                "provider_count": 0,
                "pagination_query": "",
            }

            featured_providers = get_featured_providers()

        catalog = get_public_directory_catalog()

        context.update(search_state)
        context.update(result_context)

        context.update(
            {
                "featured_providers": featured_providers,
                "services": catalog["services"],
                "affirming_features": catalog[
                    "affirming_features"
                ],
                "states": catalog["states"],
                "show_results_heading": True,
                "canonical_url": self.request.build_absolute_uri(
                    reverse("home")
                ),
            }
        )

        return context


class ProviderResultsView(TemplateView):
    template_name = "pages/provider_results.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        search_state = provider_search_state(
            self.request
        )

        providers = search_providers(
            search_state["filters"],
            search_state["sort"],
        )

        context.update(search_state)

        context.update(
            paginated_provider_context(
                self.request,
                providers,
            )
        )

        context["show_results_heading"] = False

        context["canonical_url"] = (
            self.request.build_absolute_uri(
                reverse("provider_results")
            )
        )

        return context


about_view = TemplateView.as_view(
    template_name="pages/about.html"
)


# ============================================================
# AFFIRMCARE NEWS / CISION RSS FEEDS
# ============================================================

NEWS_FEEDS = {
    "Latest News": (
        "https://tools.prnewswire.com/"
        "en-us/live/28741/rss/fulltext"
    ),

    "Policy & Legislation": (
        "https://tools.prnewswire.com/"
        "en-us/live/28745/rss/fulltext"
    ),

    "Research": (
        "https://tools.prnewswire.com/"
        "en-us/live/28747/rss/fulltext"
    ),

    "Education": (
        "https://tools.prnewswire.com/"
        "en-us/live/28748/rss/fulltext"
    ),

    "Healthcare": (
        "https://tools.prnewswire.com/"
        "en-us/live/28746/rss/fulltext"
    ),

    "AI & Health Care": (
        "https://tools.prnewswire.com/"
        "en-us/live/28749/rss/fulltext"
    ),
}


def fetch_news_feed(url, limit=6):
    """
    Fetch and parse one Cision/PR Newswire RSS feed.
    """

    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "AffirmCare News/1.0"
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=10,
        ) as response:
            data = response.read()

        root = ET.fromstring(data)

        stories = []

        for item in root.findall(".//item")[:limit]:

            title = item.findtext(
                "title",
                default="",
            ).strip()

            link = item.findtext(
                "link",
                default="",
            ).strip()

            description = item.findtext(
                "description",
                default="",
            ).strip()

            pub_date = item.findtext(
                "pubDate",
                default="",
            ).strip()

            if title and link:
                stories.append(
                    {
                        "title": title,
                        "link": link,
                        "description": description,
                        "pub_date": pub_date,
                    }
                )

        return stories

   except Exception as e:
    print(f"AffirmCare RSS feed error: {url} -> {e}")
    return []


class NewsView(TemplateView):
    template_name = "pages/news.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        news_sections = []

        for category, url in NEWS_FEEDS.items():

            cache_key = (
                "affirmcare_news_"
                + category.lower().replace(" ", "_")
            )

            stories = cache.get(cache_key)

            if stories is None:
                stories = fetch_news_feed(
                    url,
                    limit=6,
                )

                cache.set(
                    cache_key,
                    stories,
                    900,
                )

            news_sections.append(
                {
                    "category": category,
                    "stories": stories,
                }
            )

        context["news_sections"] = news_sections

        context["canonical_url"] = (
            self.request.build_absolute_uri(
                reverse("news")
            )
        )

        return context


news_view = NewsView.as_view()


# ============================================================
# ROBOTS.TXT
# ============================================================

def robots_txt(request):
    sitemap_url = request.build_absolute_uri(
        reverse("sitemap")
    )

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

    return HttpResponse(
        body,
        content_type="text/plain; charset=utf-8",
    )

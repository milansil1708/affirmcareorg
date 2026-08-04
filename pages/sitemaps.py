from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from provider_organizations.models import ProviderOrganization


class StaticViewSitemap(Sitemap):
    protocol = "https"
    priority = 1.0
    changefreq = "weekly"

    def items(self):
        return ("home",)

    def location(self, item):
        return reverse(item)


class ProviderSitemap(Sitemap):
    protocol = "https"
    priority = 0.7
    changefreq = "monthly"

    def items(self):
        return (
            ProviderOrganization.objects.filter(is_active=True)
            .only("slug")
            .order_by("id")
        )

    def location(self, provider):
        return reverse("provider_detail", args=(provider.slug,))


sitemaps = {
    "static": StaticViewSitemap,
    "providers": ProviderSitemap,
}

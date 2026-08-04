from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.views.decorators.cache import cache_page

from pages.sitemaps import sitemaps
from pages.views import robots_txt

urlpatterns = [
    path("robots.txt", robots_txt, name="robots_txt"),
    path(
        "sitemap.xml",
        cache_page(60 * 60 * 24)(sitemap),
        {"sitemaps": sitemaps},
        name="sitemap",
    ),
    path('admin/', admin.site.urls),
    path("tinymce/", include("tinymce.urls")),
    path('users/', include(('users.urls', 'users'), namespace='users')),
    path("", include('pages.urls')),
    path("blogs/", include("blogs.urls")),
    path("providers-organizations/", include('provider_organizations.urls')),
    path("api/providers/", include("provider_search.urls")),
    path("api/chat/", include("provider_chat.urls")),
    path(
        "chat/",
        include(
            ("provider_chat.page_urls", "provider_chat_pages"),
            namespace="provider_chat_pages",
        ),
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

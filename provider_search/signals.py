from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from provider_organizations.models import (
    AffirmingFeature,
    OrganizationService,
    ProviderFeature,
    ProviderLocation,
    ProviderOrganization,
    Service,
)

from .cache_keys import (
    CHAT_SUGGESTIONS_CACHE_KEY,
    DIRECTORY_CATALOG_CACHE_KEY,
    FEATURED_PROVIDER_IDS_CACHE_KEY,
)


CACHE_DEPENDENCY_MODELS = {
    AffirmingFeature,
    OrganizationService,
    ProviderFeature,
    ProviderLocation,
    ProviderOrganization,
    Service,
}


@receiver((post_save, post_delete))
def invalidate_public_directory_caches(sender, **kwargs):
    if sender not in CACHE_DEPENDENCY_MODELS:
        return
    cache.delete_many(
        (
            DIRECTORY_CATALOG_CACHE_KEY,
            FEATURED_PROVIDER_IDS_CACHE_KEY,
            CHAT_SUGGESTIONS_CACHE_KEY,
        )
    )

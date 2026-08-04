from django.apps import AppConfig


class ProviderSearchConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "provider_search"

    def ready(self):
        from . import signals  # noqa: F401

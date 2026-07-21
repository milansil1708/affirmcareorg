from django.urls import path

from .views import (
    ProviderDetailView,
    ProviderSearchOptionsView,
    ProviderSearchView,
)


app_name = "provider_search"

urlpatterns = [
    path("search/", ProviderSearchView.as_view(), name="search"),
    path("options/", ProviderSearchOptionsView.as_view(), name="options"),
    path("<slug:slug>/", ProviderDetailView.as_view(), name="detail"),
]

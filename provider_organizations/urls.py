from django.urls import path
from . import views

urlpatterns = [
    path("account/", views.provider_account_view, name="provider_account"),
    path(
        "claim/<slug:slug>/",
        views.claim_provider_organization_view,
        name="claim_provider_organization",
    ),
    path("<slug:slug>/", views.provider_detail_view, name="provider_detail"),
]

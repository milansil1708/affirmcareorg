from django.urls import path
from . import views

urlpatterns = [
    path("<slug:slug>/", views.provider_detail_view, name="provider_detail"),
]

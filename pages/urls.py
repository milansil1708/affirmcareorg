from django.urls import path
from . import views

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("providers/", views.ProviderResultsView.as_view(), name="provider_results"),
    path("about/", views.about_view, name="about"),
    path("news/", views.news_view, name="news"),
]

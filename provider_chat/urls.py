from django.urls import path

from .views import ProviderChatView


app_name = "provider_chat"

urlpatterns = [
    path("", ProviderChatView.as_view(), name="chat"),
]

from django.urls import path

from .views import ProviderChatPageView


app_name = "provider_chat_pages"

urlpatterns = [
    path("", ProviderChatPageView.as_view(), name="chat"),
]

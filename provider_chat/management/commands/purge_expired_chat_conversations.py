from django.core.management.base import BaseCommand
from django.utils import timezone

from provider_chat.models import ChatConversation


class Command(BaseCommand):
    help = "Delete expired provider-chat conversations and their retained turns."

    def handle(self, *args, **options):
        expired = ChatConversation.objects.filter(expires_at__lte=timezone.now())
        conversation_count = expired.count()
        expired.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {conversation_count} expired chat conversation(s)."
            )
        )

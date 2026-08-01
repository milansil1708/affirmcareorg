import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class ChatConversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="provider_chat_conversations",
    )
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    current_filters = models.JSONField(default=dict, blank=True)
    current_sort = models.CharField(max_length=32, default="name")
    result_provider_slugs = models.JSONField(default=list, blank=True)
    selected_provider_slug = models.SlugField(max_length=255, blank=True)
    pending_clarification = models.CharField(max_length=300, blank=True)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)
        constraints = (
            models.CheckConstraint(
                condition=(
                    (Q(user__isnull=False) & Q(session_key=""))
                    | (Q(user__isnull=True) & ~Q(session_key=""))
                ),
                name="chat_conversation_has_one_owner",
            ),
        )
        indexes = (
            models.Index(
                fields=("user", "expires_at"),
                name="chat_user_expiry_idx",
            ),
        )

    def __str__(self):
        return str(self.id)


class ChatTurn(models.Model):
    class Intent(models.TextChoices):
        INFORMATIONAL = "informational", "Informational"
        SEARCH_PROVIDERS = "search_providers", "Search providers"
        PROVIDER_DETAILS = "provider_details", "Provider details"
        CLARIFICATION = "clarification", "Clarification"

    conversation = models.ForeignKey(
        ChatConversation,
        on_delete=models.CASCADE,
        related_name="turns",
    )
    user_message = models.TextField()
    assistant_message = models.TextField()
    intent = models.CharField(max_length=32, choices=Intent.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")
        indexes = (
            models.Index(
                fields=("conversation", "created_at"),
                name="chat_turn_created_idx",
            ),
        )

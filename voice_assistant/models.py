from django.conf import settings
from django.db import models

from ecommerce.models import OnlineCustomer
from .config import VOICE_RECOGNITION_LANGUAGE, VOICE_RESPONSE_LANGUAGE


class VoiceInteraction(models.Model):
    """
    Append-only log of every voice interaction across the system.

    This model never drives any business logic — it exists purely to
    capture evaluation data for the dissertation (routing accuracy,
    successful vs unsuccessful interactions, interaction history).
    Always insert new rows; never update or delete existing ones.
    """

    INTERACTION_TYPE_CHOICES = [
        ('shopping_assistant', 'AI Shopping Assistant'),
        ('credit_loyalty', 'Smart Credit & Loyalty Assistant'),
        ('advisor_recap', 'AI Business Advisor Recap'),
    ]

    interaction_type = models.CharField(
        max_length=30,
        choices=INTERACTION_TYPE_CHOICES,
    )
    customer = models.ForeignKey(
        OnlineCustomer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='voice_interactions',
        help_text="Set for shopping_assistant and credit_loyalty interactions.",
    )
    staff_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='voice_interactions',
        help_text="Set for advisor_recap interactions.",
    )
    raw_transcript = models.TextField(
        help_text="Raw text produced by the browser's SpeechRecognition API."
    )
    recognition_language = models.CharField(
        max_length=10,
        default=VOICE_RECOGNITION_LANGUAGE,
        help_text="Snapshot of the recognition language used for this interaction.",
    )
    response_language = models.CharField(
        max_length=10,
        default=VOICE_RESPONSE_LANGUAGE,
        help_text="Snapshot of the response language used for this interaction.",
    )
    routed_to = models.CharField(
        max_length=100,
        help_text="Name of the existing service function this transcript was routed to.",
    )
    response_summary = models.TextField(
        help_text="The narrated text that was actually spoken back to the user."
    )
    was_successful = models.BooleanField(
        null=True,
        blank=True,
        help_text="Nullable: unset until manually reviewed/marked during testing.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_interaction_type_display()} — {self.created_at:%Y-%m-%d %H:%M}"
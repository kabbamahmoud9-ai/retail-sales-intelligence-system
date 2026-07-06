"""
voice_assistant/views.py

Thin routing/narration views only. Every view here reads existing,
already-persisted data and calls existing service functions unchanged.
No business logic is duplicated or reimplemented here.
"""

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from ecommerce.views import get_current_customer, customer_login_required
from ai_commerce.models import ShoppingSession

from .config import VOICE_RECOGNITION_LANGUAGE, VOICE_RESPONSE_LANGUAGE
from .language import format_for_speech
from .narration import narrate_shopping_recommendations
from .models import VoiceInteraction


@customer_login_required
@require_POST
def read_recommendations_aloud(request, session_id):
    """
    Reads back an already-persisted ShoppingSession's recommendations.
    Never recomputes anything — only reads existing ShoppingRecommendation
    rows for this session and narrates them.
    """
    customer = get_current_customer(request)
    session = get_object_or_404(ShoppingSession, id=session_id, customer=customer)
    recommendations = session.recommendations.select_related('product').order_by('rank')

    narrated_text = narrate_shopping_recommendations(session, recommendations)
    spoken_text = format_for_speech(narrated_text)

    VoiceInteraction.objects.create(
        interaction_type='shopping_assistant',
        customer=customer,
        raw_transcript='(read-aloud request, no speech captured)',
        recognition_language=VOICE_RECOGNITION_LANGUAGE,
        response_language=VOICE_RESPONSE_LANGUAGE,
        routed_to='voice_assistant.narration.narrate_shopping_recommendations',
        response_summary=spoken_text,
    )

    return JsonResponse({'spoken_text': spoken_text})
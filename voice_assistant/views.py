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

from ai_commerce.models import CreditAssessment
from ai_commerce.services import get_reorder_suggestions

from .config import VOICE_RECOGNITION_LANGUAGE, VOICE_RESPONSE_LANGUAGE
from .language import format_for_speech
from .narration import narrate_shopping_recommendations, narrate_credit_status
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
@customer_login_required
@require_POST
def read_credit_status_aloud(request):
    """
    Reads back the customer's most recent CreditAssessment plus their
    reorder suggestions. Never recalculates eligibility, trust score,
    or loyalty tier — only reads the latest persisted assessment.
    get_reorder_suggestions() is pure historical aggregation (not AI),
    same as it is when called from ai_commerce.views.credit_loyalty_assistant.
    """
    customer = get_current_customer(request)
    assessment = CreditAssessment.objects.filter(customer=customer).first()
    reorder_suggestions = get_reorder_suggestions(customer)

    narrated_text = narrate_credit_status(customer, assessment, reorder_suggestions)
    spoken_text = format_for_speech(narrated_text)

    VoiceInteraction.objects.create(
        interaction_type='credit_loyalty',
        customer=customer,
        raw_transcript='(read-aloud request, no speech captured)',
        recognition_language=VOICE_RECOGNITION_LANGUAGE,
        response_language=VOICE_RESPONSE_LANGUAGE,
        routed_to='voice_assistant.narration.narrate_credit_status',
        response_summary=spoken_text,
    )

    return JsonResponse({'spoken_text': spoken_text})
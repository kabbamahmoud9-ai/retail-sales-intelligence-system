import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.utils import timezone
from django.http import JsonResponse

from .models import Recommendation, AdvisorConversationSession
from .business_health import generate_business_health_summary
from .briefing import generate_daily_briefing
from .conversational import process_message


@login_required
def advisor_list(request):
    priority_filter = request.GET.get('priority', 'all')

    recommendations = Recommendation.objects.select_related('product', 'forecast').order_by('-generated_at')
    if priority_filter in ('critical', 'high', 'medium', 'low'):
        recommendations = recommendations.filter(priority=priority_filter)

    paginator = Paginator(recommendations, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    counts = {
        'all': Recommendation.objects.count(),
        'critical': Recommendation.objects.filter(priority='critical').count(),
        'high': Recommendation.objects.filter(priority='high').count(),
        'medium': Recommendation.objects.filter(priority='medium').count(),
        'low': Recommendation.objects.filter(priority='low').count(),
    }

    # New for Step 19: business health summary, daily briefing, and a
    # fresh conversation session for the chat panel — created once per
    # page load, same pattern as ai_commerce.conversational_chat.
    business_health = generate_business_health_summary()
    daily_briefing = generate_daily_briefing()
    chat_session = AdvisorConversationSession.objects.create(staff_user=request.user)

    return render(request, 'advisor/recommendation_list.html', {
        'page_obj': page_obj,
        'priority_filter': priority_filter,
        'counts': counts,
        'business_health': business_health,
        'daily_briefing': daily_briefing,
        'advisor_chat_session_id': chat_session.id,
    })


@login_required
@require_POST
def mark_actioned(request, pk):
    rec = get_object_or_404(Recommendation, pk=pk)
    rec.is_actioned = True
    rec.actioned_at = timezone.now()
    rec.save()
    return redirect(request.META.get('HTTP_REFERER', '/'))


@login_required
@require_POST
def advisor_message(request, session_id):
    """
    AJAX endpoint for the AI Business Consultant chat panel. Mirrors
    ai_commerce.conversational_message but staff-scoped. Zero business
    logic here — delegates entirely to conversational.process_message().
    """
    session = get_object_or_404(AdvisorConversationSession, id=session_id, staff_user=request.user)

    try:
        body = json.loads(request.body)
        message_text = body.get('message', '').strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)

    if not message_text:
        return JsonResponse({'error': 'Message cannot be empty'}, status=400)

    reply_text = process_message(session, request.user, message_text)

    return JsonResponse({'reply': reply_text})
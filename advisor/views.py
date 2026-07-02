from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.utils import timezone

from .models import Recommendation


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

    return render(request, 'advisor/recommendation_list.html', {
        'page_obj': page_obj,
        'priority_filter': priority_filter,
        'counts': counts,
    })


@login_required
@require_POST
def mark_actioned(request, pk):
    rec = get_object_or_404(Recommendation, pk=pk)
    rec.is_actioned = True
    rec.actioned_at = timezone.now()
    rec.save()
    return redirect(request.META.get('HTTP_REFERER', '/'))
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import Notification
from .services import generate_notifications

@login_required
def notification_list(request):
    # Regenerate notifications every time page is opened
    generate_notifications()
    notifications = Notification.objects.filter(is_read=False).order_by('-created_at')
    all_notifications = Notification.objects.order_by('-created_at')[:50]
    return render(request, 'notifications/notification_list.html', {
        'notifications': notifications,
        'all_notifications': all_notifications,
    })

@login_required
@require_POST
def mark_read(request, pk):
    notif = get_object_or_404(Notification, pk=pk)
    notif.is_read = True
    notif.save()
    return JsonResponse({'status': 'ok'})

@login_required
@require_POST
def mark_all_read(request):
    Notification.objects.filter(is_read=False).update(is_read=True)
    return JsonResponse({'status': 'ok'})

@login_required
def get_unread_count(request):
    count = Notification.objects.filter(is_read=False).count()
    return JsonResponse({'count': count})

@login_required
def get_recent_notifications(request):
    generate_notifications()
    notifications = Notification.objects.filter(is_read=False).order_by('-created_at')[:10]
    data = [{
        'id': n.id,
        'title': n.title,
        'message': n.message,
        'type': n.notification_type,
        'dot_color': n.dot_color,
        'icon': n.icon,
        'action_url': n.action_url or '',
        'action_label': n.action_label or '',
        'created_at': n.created_at.strftime('%b %d, %H:%M'),
    } for n in notifications]
    return JsonResponse({'notifications': data, 'count': len(data)})
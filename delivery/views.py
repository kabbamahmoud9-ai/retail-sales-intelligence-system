"""
delivery/views.py

Staff-facing views for delivery zone management and delivery
profitability analytics (delivery intelligence).
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum

from .models import DeliveryZone
from .forms import DeliveryZoneForm


@login_required
def zone_list(request):
    zones = DeliveryZone.objects.all()
    return render(request, 'delivery/zone_list.html', {
        'zones': zones,
    })


@login_required
def zone_add(request):
    if request.method == 'POST':
        form = DeliveryZoneForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Delivery zone created successfully!')
            return redirect('zone_list')
    else:
        form = DeliveryZoneForm()
    return render(request, 'delivery/zone_form.html', {'form': form, 'title': 'Add Delivery Zone'})


@login_required
def zone_edit(request, pk):
    zone = get_object_or_404(DeliveryZone, pk=pk)
    if request.method == 'POST':
        form = DeliveryZoneForm(request.POST, instance=zone)
        if form.is_valid():
            form.save()
            messages.success(request, 'Delivery zone updated successfully!')
            return redirect('zone_list')
    else:
        form = DeliveryZoneForm(instance=zone)
    return render(request, 'delivery/zone_form.html', {'form': form, 'title': 'Edit Delivery Zone'})


@login_required
def zone_delete(request, pk):
    zone = get_object_or_404(DeliveryZone, pk=pk)
    if request.method == 'POST':
        zone.delete()
        messages.success(request, 'Delivery zone deleted successfully!')
        return redirect('zone_list')
    return render(request, 'delivery/zone_confirm_delete.html', {'zone': zone})


@login_required
def zone_performance(request):
    """
    Delivery intelligence: per-zone order volume, delivery revenue,
    estimated operational cost, and estimated profit.

    Imports OnlineOrder locally (not at module level) to avoid a
    circular import with ecommerce.models, which will hold the FK to
    DeliveryZone once Step 11b lands.
    """
    from ecommerce.models import OnlineOrder

    zones = DeliveryZone.objects.all()
    zone_stats = []

    for zone in zones:
        orders = OnlineOrder.objects.filter(delivery_zone=zone, status__in=['confirmed', 'delivered'])
        order_count = orders.count()
        total_revenue = orders.aggregate(total=Sum('delivery_fee'))['total'] or 0
        total_cost = zone.estimated_operational_cost * order_count
        estimated_profit = total_revenue - total_cost

        zone_stats.append({
            'zone': zone,
            'order_count': order_count,
            'total_revenue': total_revenue,
            'total_cost': total_cost,
            'estimated_profit': estimated_profit,
        })

    return render(request, 'delivery/zone_performance.html', {
        'zone_stats': zone_stats,
    })
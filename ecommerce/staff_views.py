"""
ecommerce/staff_views.py

Staff-facing views (Django auth, not customer session auth) for:
  - Customer intelligence: loyalty tier, trust score, lifetime spending,
    preferred categories, order history
  - Delivery management: updating delivery_status as orders move through
    fulfillment

Kept in a separate module (and separate, non-namespaced urls.py) from
ecommerce/views.py, which is exclusively the customer-facing store.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import OnlineCustomer, OnlineOrder


# ---------------------------------------------------------------------------
# Customer intelligence
# ---------------------------------------------------------------------------

@login_required
def customer_intelligence_list(request):
    """
    Staff view of all online customers with loyalty tier, trust score,
    and lifetime spending at a glance. Supports search by name/email.
    """
    customers = OnlineCustomer.objects.all().order_by('-lifetime_spending')

    query = request.GET.get('q', '').strip()
    if query:
        customers = customers.filter(full_name__icontains=query) | \
                    customers.filter(email__icontains=query)

    return render(request, 'ecommerce/staff/customer_list.html', {
        'customers': customers,
        'query': query,
    })


@login_required
def customer_intelligence_detail(request, pk):
    """
    Full customer intelligence profile: loyalty tier, trust score,
    lifetime spending, preferred categories, and order history.
    """
    customer = get_object_or_404(OnlineCustomer, pk=pk)
    orders = customer.orders.order_by('-order_date')

    return render(request, 'ecommerce/staff/customer_detail.html', {
        'customer': customer,
        'orders': orders,
        'preferred_categories': customer.preferred_categories.all(),
    })


# ---------------------------------------------------------------------------
# Delivery management
# ---------------------------------------------------------------------------

@login_required
def delivery_order_list(request):
    """
    Staff view of confirmed/delivered orders needing delivery management.
    Only orders that have actually reached payment confirmation are shown
    here — pending/cancelled orders have no delivery leg to manage yet.
    """
    orders = OnlineOrder.objects.filter(
        status__in=['confirmed', 'delivered']
    ).select_related('customer', 'delivery_zone').order_by('-order_date')

    status_filter = request.GET.get('delivery_status', '')
    if status_filter:
        orders = orders.filter(delivery_status=status_filter)

    return render(request, 'ecommerce/staff/delivery_order_list.html', {
        'orders': orders,
        'status_choices': OnlineOrder.DELIVERY_STATUS_CHOICES,
        'status_filter': status_filter,
    })


@login_required
def delivery_order_update(request, pk):
    """Update delivery_status / delivery_method / delivery_notes for one order. POST only."""
    order = get_object_or_404(OnlineOrder, pk=pk)

    if request.method == 'POST':
        delivery_status = request.POST.get('delivery_status', '')
        delivery_method = request.POST.get('delivery_method', '')
        delivery_notes  = request.POST.get('delivery_notes', '').strip()

        valid_statuses = [c[0] for c in OnlineOrder.DELIVERY_STATUS_CHOICES]
        valid_methods  = [c[0] for c in OnlineOrder.DELIVERY_METHOD_CHOICES]

        if delivery_status and delivery_status not in valid_statuses:
            messages.error(request, "Invalid delivery status.")
            return redirect('delivery_order_list')

        if delivery_method and delivery_method not in valid_methods:
            messages.error(request, "Invalid delivery method.")
            return redirect('delivery_order_list')

        order.delivery_status = delivery_status
        order.delivery_method = delivery_method
        order.delivery_notes  = delivery_notes
        order.save()

        messages.success(request, f"Delivery status for {order.order_reference} updated.")

    return redirect('delivery_order_list')
"""
ecommerce/staff_views.py

Staff-facing views (Django auth, not customer session auth) for:
  - Customer intelligence: loyalty tier, trust score, lifetime spending,
    preferred categories, order history, credit approval/repayment
  - Delivery management: updating delivery_status as orders move through
    fulfillment

Kept in a separate module (and separate, non-namespaced urls.py) from
ecommerce/views.py, which is exclusively the customer-facing store.
"""

from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone

from .models import OnlineCustomer, OnlineOrder, CreditRepayment
from ai_commerce.models import CreditAssessment
from blockchain.services import create_ledger_entry


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
    lifetime spending, preferred categories, order history, and
    credit approval/repayment.
    """
    customer = get_object_or_404(OnlineCustomer, pk=pk)
    orders = customer.orders.order_by('-order_date')

    latest_credit_assessment = (
        CreditAssessment.objects.filter(customer=customer).order_by('-generated_at').first()
    )
    pending_approval = bool(
        latest_credit_assessment
        and latest_credit_assessment.recommended_credit_limit != customer.credit_limit
    )

    return render(request, 'ecommerce/staff/customer_detail.html', {
        'customer': customer,
        'orders': orders,
        'preferred_categories': customer.preferred_categories.all(),
        'latest_credit_assessment': latest_credit_assessment,
        'pending_approval': pending_approval,
        'repayment_history': customer.credit_repayments.all()[:10],
    })


@login_required
def approve_credit_recommendation(request, pk):
    """
    Staff-triggered approval: copies the latest CreditAssessment's
    recommended_credit_limit into OnlineCustomer.credit_limit. POST only.

    This is the ONLY place OnlineCustomer.credit_limit is ever written
    from an AI recommendation — a deliberate, explicit staff action,
    never automatic. calculate_credit_recommendation() and
    CreditAssessment remain completely untouched by this; this view only
    reads the latest already-generated assessment and copies one number
    across the human-approval boundary.
    """
    if request.method != 'POST':
        return redirect('customer_intelligence_detail', pk=pk)

    customer = get_object_or_404(OnlineCustomer, pk=pk)
    assessment = CreditAssessment.objects.filter(customer=customer).order_by('-generated_at').first()

    if not assessment:
        messages.error(request, "No credit assessment found for this customer.")
        return redirect('customer_intelligence_detail', pk=pk)

    customer.credit_limit = assessment.recommended_credit_limit
    customer.save(update_fields=['credit_limit'])

    messages.success(
        request,
        f"Credit limit approved: {customer.full_name} is now approved for up to "
        f"Le {customer.credit_limit:,.2f} on credit."
    )
    return redirect('customer_intelligence_detail', pk=pk)


@login_required
def record_credit_repayment(request, pk):
    """
    Staff-triggered: records that a customer repaid some or all of their
    outstanding credit balance. Decreases credit_balance (never below
    zero), logs a CreditRepayment row, and writes a blockchain ledger
    entry — mirroring the exact pattern already used for payment
    confirmations, extended to cover the repayment side of the credit
    lifecycle.
    """
    if request.method != 'POST':
        return redirect('customer_intelligence_detail', pk=pk)

    customer = get_object_or_404(OnlineCustomer, pk=pk)

    try:
        amount = Decimal(request.POST.get('amount', '').strip())
    except (InvalidOperation, AttributeError):
        messages.error(request, "Please enter a valid repayment amount.")
        return redirect('customer_intelligence_detail', pk=pk)

    if amount <= 0:
        messages.error(request, "Repayment amount must be greater than zero.")
        return redirect('customer_intelligence_detail', pk=pk)

    balance_before = customer.credit_balance
    balance_after = max(Decimal('0.00'), balance_before - amount)

    customer.credit_balance = balance_after
    customer.save(update_fields=['credit_balance'])

    repayment = CreditRepayment.objects.create(
        customer=customer,
        amount=amount,
        recorded_by=request.user,
        balance_before=balance_before,
        balance_after=balance_after,
    )

    ledger_entry = create_ledger_entry(
        record_type='credit_repayment',
        record_reference=f"CREDIT-{customer.id}-{repayment.id}",
        payload_snapshot={
            'customer_id': customer.id,
            'customer_name': customer.full_name,
            'amount': str(amount),
            'balance_before': str(balance_before),
            'balance_after': str(balance_after),
            'recorded_by': request.user.username,
            'recorded_at': timezone.now().isoformat(),
        },
    )
    repayment.transaction_hash = ledger_entry.current_hash
    repayment.save(update_fields=['transaction_hash'])

    messages.success(
        request,
        f"Repayment of Le {amount:,.2f} recorded for {customer.full_name}. "
        f"New outstanding balance: Le {balance_after:,.2f}."
    )
    return redirect('customer_intelligence_detail', pk=pk)


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
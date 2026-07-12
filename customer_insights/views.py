from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from ecommerce.models import OnlineCustomer
from .models import CustomerInsightSnapshot
from .services import generate_customer_insight


def _latest_snapshot(customer):
    return CustomerInsightSnapshot.objects.filter(customer=customer).order_by('-generated_at').first()


@login_required
def customer_insights_dashboard(request):
    """
    Staff-facing list of all customers with their latest insight snapshot
    (segment, churn risk, prediction method). Read-only — no business
    logic here, just querying the latest CustomerInsightSnapshot per
    customer and rendering it.
    """
    customers = OnlineCustomer.objects.filter(is_active=True).order_by('-lifetime_spending')

    rows = []
    for customer in customers:
        snapshot = _latest_snapshot(customer)
        rows.append({'customer': customer, 'snapshot': snapshot})

    context = {'rows': rows}
    return render(request, 'customer_insights/dashboard.html', context)


@login_required
def customer_insight_detail(request, customer_id):
    """Full insight detail for a single customer, plus the regenerate button."""
    customer = get_object_or_404(OnlineCustomer, id=customer_id)
    snapshot = _latest_snapshot(customer)
    history = CustomerInsightSnapshot.objects.filter(customer=customer).order_by('-generated_at')[:10]

    context = {
        'customer': customer,
        'snapshot': snapshot,
        'history': history,
    }
    return render(request, 'customer_insights/detail.html', context)


@login_required
def regenerate_insight(request, customer_id):
    """
    On-demand single-customer regeneration. Calls the EXACT SAME
    orchestrator function the batch management command uses — zero
    duplicated logic, per the standing thin-layer principle.
    """
    if request.method != 'POST':
        return redirect('customer_insights:detail', customer_id=customer_id)

    customer = get_object_or_404(OnlineCustomer, id=customer_id)
    generate_customer_insight(customer)
    messages.success(request, f"Insights regenerated for {customer.full_name}.")
    return redirect('customer_insights:detail', customer_id=customer.id)
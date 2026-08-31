from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from accounts.decorators import owner_required
from ecommerce.models import OnlineCustomer
from .models import CustomerInsightSnapshot
from .services import generate_customer_insight


def _latest_snapshot(customer):
    return CustomerInsightSnapshot.objects.filter(customer=customer).order_by('-generated_at').first()


@owner_required
def customer_insights_dashboard(request):
    customers = OnlineCustomer.objects.filter(is_active=True).order_by('-lifetime_spending')

    rows = []
    for customer in customers:
        snapshot = _latest_snapshot(customer)
        rows.append({'customer': customer, 'snapshot': snapshot})

    context = {'rows': rows}
    return render(request, 'customer_insights/dashboard.html', context)


@owner_required
def customer_insight_detail(request, customer_id):
    customer = get_object_or_404(OnlineCustomer, id=customer_id)
    snapshot = _latest_snapshot(customer)
    history = CustomerInsightSnapshot.objects.filter(customer=customer).order_by('-generated_at')[:10]

    context = {
        'customer': customer,
        'snapshot': snapshot,
        'history': history,
    }
    return render(request, 'customer_insights/detail.html', context)


@owner_required
def regenerate_insight(request, customer_id):
    if request.method != 'POST':
        return redirect('customer_insights:detail', customer_id=customer_id)

    customer = get_object_or_404(OnlineCustomer, id=customer_id)
    generate_customer_insight(customer)
    messages.success(request, f"Insights regenerated for {customer.full_name}.")
    return redirect('customer_insights:detail', customer_id=customer.id)

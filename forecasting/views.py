from django.shortcuts import render
from django.db.models import Max
from accounts.decorators import owner_required
from .models import DemandForecast


@owner_required
def forecast_list(request):
    # Latest forecast per product: get the max generated_at per product,
    # then fetch the matching rows.
    latest_per_product = (
        DemandForecast.objects
        .values('product')
        .annotate(latest=Max('generated_at'))
    )
    latest_timestamps = {row['product']: row['latest'] for row in latest_per_product}

    forecasts = (
        DemandForecast.objects
        .select_related('product')
        .filter(generated_at__in=latest_timestamps.values())
        .order_by('product__product_name')
    )

    return render(request, 'forecasting/forecast_list.html', {
        'forecasts': forecasts,
    })
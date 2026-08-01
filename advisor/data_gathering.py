"""
advisor/data_gathering.py

Read-only data-gathering functions, one per business question area.
Every function here is a thin wrapper reading from EXISTING models and
services — forecasting, sales, customer_insights, ecommerce, delivery,
expenses, blockchain. Nothing here computes new business logic; it only
retrieves and lightly summarizes what already exists elsewhere.
"""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from django.db.models import Sum, Count, Q

from products.models import Product
from forecasting.models import DemandForecast
from sales.models import Sale, SaleItem
from customer_insights.models import CustomerInsightSnapshot
from ecommerce.models import OnlineCustomer, OnlineOrder
from delivery.models import DeliveryZone
from expenses.models import Expense
from blockchain.services import verify_chain


# ---------------------------------------------------------------------------
# Inventory / Restock
# ---------------------------------------------------------------------------

def get_restock_candidates(limit=10):
    latest_forecasts = (
        DemandForecast.objects
        .filter(has_sufficient_data=True, recommended_restock_quantity__gt=0)
        .select_related('product')
        .order_by('product_id', '-generated_at')
        .distinct('product_id')
    )
    results = sorted(latest_forecasts, key=lambda f: f.recommended_restock_quantity, reverse=True)[:limit]
    return [
        {
            'product': f.product,
            'predicted_quantity': f.predicted_quantity,
            'current_stock': f.product.quantity_in_stock,
            'recommended_restock_quantity': f.recommended_restock_quantity,
            'confidence_score': f.confidence_score,
        }
        for f in results
    ]


def get_slow_moving_products(days=30, limit=10):
    cutoff = timezone.now() - timedelta(days=days)
    sold_quantities = dict(
        SaleItem.objects
        .filter(sale__status='completed', sale__sale_date__gte=cutoff)
        .values('product_id')
        .annotate(total=Sum('quantity'))
        .values_list('product_id', 'total')
    )
    products = Product.objects.filter(is_active=True)
    ranked = sorted(products, key=lambda p: sold_quantities.get(p.id, 0))[:limit]
    return [{'product': p, 'quantity_sold': sold_quantities.get(p.id, 0)} for p in ranked]


def get_overstocked_products(limit=10):
    latest_forecasts = (
        DemandForecast.objects
        .filter(has_sufficient_data=True)
        .select_related('product')
        .order_by('product_id', '-generated_at')
        .distinct('product_id')
    )
    overstocked = [
        f for f in latest_forecasts
        if f.predicted_quantity and f.product.quantity_in_stock > (float(f.predicted_quantity) * 2)
    ]
    overstocked.sort(key=lambda f: f.product.quantity_in_stock, reverse=True)
    return [
        {
            'product': f.product,
            'current_stock': f.product.quantity_in_stock,
            'predicted_quantity': f.predicted_quantity,
        }
        for f in overstocked[:limit]
    ]


# ---------------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------------

def get_top_selling_products(days=7, limit=5):
    cutoff = timezone.now() - timedelta(days=days)
    rows = (
        SaleItem.objects
        .filter(sale__status='completed', sale__sale_date__gte=cutoff)
        .values('product__product_name')
        .annotate(total_quantity=Sum('quantity'))
        .order_by('-total_quantity')[:limit]
    )
    return list(rows)


def get_lowest_selling_products(days=7, limit=5):
    return get_slow_moving_products(days=days, limit=limit)


def get_best_performing_categories(days=7, limit=5):
    cutoff = timezone.now() - timedelta(days=days)
    rows = (
        SaleItem.objects
        .filter(sale__status='completed', sale__sale_date__gte=cutoff)
        .values('product__category__category_name')
        .annotate(revenue=Sum('unit_price'))
        .order_by('-revenue')[:limit]
    )
    return list(rows)


def get_todays_sales_summary():
    today = timezone.localdate()
    todays_sales = Sale.objects.filter(status='completed', sale_date__date=today)
    return {
        'total_sales': todays_sales.count(),
        'total_revenue': todays_sales.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00'),
    }


# ---------------------------------------------------------------------------
# Forecasting
# ---------------------------------------------------------------------------

def get_forecast_trend_summary():
    latest_forecasts = list(
        DemandForecast.objects
        .filter(has_sufficient_data=True)
        .order_by('product_id', '-generated_at')
        .distinct('product_id')
    )
    increasing = [f for f in latest_forecasts if f.trend == DemandForecast.TREND_INCREASING]
    decreasing = [f for f in latest_forecasts if f.trend == DemandForecast.TREND_DECREASING]

    confidence_scores = [float(f.confidence_score) for f in latest_forecasts if f.confidence_score is not None]
    average_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else None

    return {
        'increasing_products': [f.product for f in increasing],
        'decreasing_products': [f.product for f in decreasing],
        'average_confidence': average_confidence,
        'total_forecasted': len(latest_forecasts),
    }


# ---------------------------------------------------------------------------
# Customer Insights
# ---------------------------------------------------------------------------

def _latest_snapshots():
    return (
        CustomerInsightSnapshot.objects
        .select_related('customer')
        .order_by('customer_id', '-generated_at')
        .distinct('customer_id')
    )


def get_customers_by_segment(segment, limit=10):
    snapshots = [s for s in _latest_snapshots() if s.segment == segment][:limit]
    return snapshots


def get_highest_churn_risk_customers(limit=5):
    snapshots = [s for s in _latest_snapshots() if s.churn_risk_score is not None]
    snapshots.sort(key=lambda s: s.churn_risk_score, reverse=True)
    return snapshots[:limit]


# ---------------------------------------------------------------------------
# Credit
# ---------------------------------------------------------------------------

def get_customers_near_credit_limit(threshold_ratio=0.8, limit=10):
    customers = OnlineCustomer.objects.filter(credit_limit__gt=0)
    near_limit = [
        c for c in customers
        if (c.credit_balance / c.credit_limit) >= Decimal(str(threshold_ratio))
    ]
    near_limit.sort(key=lambda c: (c.credit_balance / c.credit_limit), reverse=True)
    return near_limit[:limit]


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def get_delivery_zone_profitability():
    zones = DeliveryZone.objects.filter(is_active=True)
    results = []
    for zone in zones:
        estimated_fee = zone.base_fee + (zone.per_km_rate * zone.average_distance_km)
        estimated_profit_per_delivery = estimated_fee - zone.estimated_operational_cost
        orders = OnlineOrder.objects.filter(delivery_zone=zone)
        order_count = orders.count()
        actual_revenue = orders.aggregate(total=Sum('delivery_fee'))['total'] or Decimal('0.00')
        results.append({
            'zone': zone,
            'estimated_profit_per_delivery': estimated_profit_per_delivery,
            'order_count': order_count,
            'actual_revenue': actual_revenue,
        })
    results.sort(key=lambda r: r['estimated_profit_per_delivery'], reverse=True)
    return results


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------

def get_expense_summary(days=7):
    cutoff = timezone.localdate() - timedelta(days=days)
    expenses = Expense.objects.filter(expense_date__gte=cutoff)
    by_category = (
        expenses.values('category__name')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    return {
        'total': expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00'),
        'by_category': list(by_category),
        'days': days,
    }


# ---------------------------------------------------------------------------
# Blockchain
# ---------------------------------------------------------------------------

def get_blockchain_status():
    return verify_chain()


# ---------------------------------------------------------------------------
# Period-over-period comparison (today's addition)
# ---------------------------------------------------------------------------

def get_period_over_period_comparison():
    """
    Compares this-week/this-month metrics against the immediately
    preceding equivalent period. Purely deterministic — no LLM
    involvement, no invented figures. Every value is either a real
    number computed from the database, or explicitly None when the
    comparison cannot be reliably calculated (e.g. no data in the
    prior period at all), so callers/prompts can honestly say
    "data unavailable" rather than fabricate a percentage against zero.
    """
    now = timezone.now()

    this_week_start = now - timedelta(days=7)
    last_week_start = now - timedelta(days=14)
    last_week_end = this_week_start

    this_week_sales = Sale.objects.filter(status='completed', sale_date__gte=this_week_start)
    last_week_sales = Sale.objects.filter(status='completed', sale_date__gte=last_week_start, sale_date__lt=last_week_end)

    this_week_revenue = this_week_sales.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    last_week_revenue = last_week_sales.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')

    this_week_orders = this_week_sales.count()
    last_week_orders = last_week_sales.count()

    this_week_expenses = Expense.objects.filter(expense_date__gte=this_week_start.date()).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    last_week_expenses = Expense.objects.filter(expense_date__gte=last_week_start.date(), expense_date__lt=last_week_end.date()).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    this_month_start = now - timedelta(days=30)
    last_month_start = now - timedelta(days=60)
    last_month_end = this_month_start

    this_month_sales = Sale.objects.filter(status='completed', sale_date__gte=this_month_start)
    last_month_sales = Sale.objects.filter(status='completed', sale_date__gte=last_month_start, sale_date__lt=last_month_end)

    this_month_revenue = this_month_sales.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    last_month_revenue = last_month_sales.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')

    this_month_orders = this_month_sales.count()
    last_month_orders = last_month_sales.count()

    this_month_expenses = Expense.objects.filter(expense_date__gte=this_month_start.date()).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    last_month_expenses = Expense.objects.filter(expense_date__gte=last_month_start.date(), expense_date__lt=last_month_end.date()).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    def _compare(current, previous):
        current = float(current)
        previous = float(previous)
        if previous == 0:
            return {
                'current': current,
                'previous': previous,
                'change': None,
                'pct_change': None,
                'available': False,
                'note': 'No data in the previous period to compare against.',
            }
        change = current - previous
        pct_change = (change / previous) * 100
        return {
            'current': current,
            'previous': previous,
            'change': round(change, 2),
            'pct_change': round(pct_change, 1),
            'available': True,
        }

    return {
        'week_over_week': {
            'revenue': _compare(this_week_revenue, last_week_revenue),
            'orders': _compare(this_week_orders, last_week_orders),
            'expenses': _compare(this_week_expenses, last_week_expenses),
        },
        'month_over_month': {
            'revenue': _compare(this_month_revenue, last_month_revenue),
            'orders': _compare(this_month_orders, last_month_orders),
            'expenses': _compare(this_month_expenses, last_month_expenses),
        },
    }


# ---------------------------------------------------------------------------
# Cross-module diagnostic aggregator
# ---------------------------------------------------------------------------

def get_business_diagnostic_context():
    """
    Cross-module aggregator for open-ended 'why'/'how is business doing'
    questions — pulls a snapshot from sales, expenses, churn, delivery,
    forecast confidence, and period comparisons into one structured
    dict. Never computes new business logic itself; purely composes
    results from the functions above.
    """
    sales = get_todays_sales_summary()
    top_sellers = get_top_selling_products(days=7, limit=3)
    slow_movers = get_slow_moving_products(days=30, limit=3)
    forecast = get_forecast_trend_summary()
    expenses = get_expense_summary(days=30)
    churn = get_highest_churn_risk_customers(limit=3)
    delivery = get_delivery_zone_profitability()
    blockchain = get_blockchain_status()
    period_comparison = get_period_over_period_comparison()

    return {
        'todays_sales': sales,
        'top_sellers_7d': top_sellers,
        'slow_movers_30d': slow_movers,
        'forecast_trend': forecast,
        'expenses_30d': expenses,
        'highest_churn_risk_customers': churn,
        'delivery_zone_profitability': delivery[:3] if delivery else [],
        'blockchain_status': blockchain,
        'period_over_period_comparison': period_comparison,
    }
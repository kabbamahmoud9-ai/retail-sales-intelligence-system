from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from products.models import Product
from sales.models import Sale
from expenses.models import Expense
from advisor.services import get_latest_recommendations


@login_required
def dashboard_view(request):
    total_products = Product.objects.count()
    total_sales = Sale.objects.count()
    low_stock_items = Product.objects.filter(quantity_in_stock__lte=5).count()
    total_revenue = sum(sale.total_amount for sale in Sale.objects.all())
    total_expenses = sum(e.amount for e in Expense.objects.all())
    net_profit = total_revenue - total_expenses
    recent_sales = Sale.objects.select_related('served_by').order_by('-sale_date')[:5]

    ai_recommendations = get_latest_recommendations(limit=5)
    critical_high_count = get_latest_recommendations().filter(
        priority__in=['critical', 'high']
    ).count()

    context = {
        'total_products': total_products,
        'total_sales': total_sales,
        'low_stock_items': low_stock_items,
        'total_revenue': total_revenue,
        'total_expenses': total_expenses,
        'net_profit': net_profit,
        'recent_sales': recent_sales,
        'ai_recommendations': ai_recommendations,
        'critical_high_count': critical_high_count,
    }
    return render(request, 'dashboard/index.html', context)
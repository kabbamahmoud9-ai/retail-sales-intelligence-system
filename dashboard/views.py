from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from products.models import Product
from sales.models import Sale

@login_required
def dashboard_view(request):
    total_products = Product.objects.count()
    total_sales = Sale.objects.count()
    low_stock_items = Product.objects.filter(quantity_in_stock__lte=5).count()
    total_revenue = sum(sale.total_amount for sale in Sale.objects.all())
    recent_sales = Sale.objects.select_related('served_by').order_by('-sale_date')[:5]

    context = {
        'total_products': total_products,
        'total_sales': total_sales,
        'low_stock_items': low_stock_items,
        'total_revenue': total_revenue,
        'recent_sales': recent_sales,
    }
    return render(request, 'dashboard/index.html', context)
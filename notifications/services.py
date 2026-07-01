"""
Notification generator — scans all modules and creates
smart notifications. Run on dashboard load and notification page.
"""
from django.db.models import Sum, Count, F
from django.utils import timezone
from datetime import timedelta
from .models import Notification
from products.models import Product
from sales.models import Sale
from demand.models import CustomerRequest
from expenses.models import Expense


def create_notif(title, message, notif_type, action_url='', action_label=''):
    today = timezone.now().date()
    exists = Notification.objects.filter(
        title=title,
        created_at__date=today
    ).exists()
    if not exists:
        Notification.objects.create(
            title=title,
            message=message,
            notification_type=notif_type,
            action_url=action_url,
            action_label=action_label,
        )


def generate_notifications():

    # ===== LOW STOCK ALERTS =====
    low_stock_products = Product.objects.filter(
        quantity_in_stock__lte=F('reorder_level')
    )
    for product in low_stock_products:
        create_notif(
            title=f"Low Stock: {product.product_name}",
            message=f"{product.product_name} has only {product.quantity_in_stock} units left (reorder level: {product.reorder_level}). Restock soon.",
            notif_type='danger',
            action_url='/inventory/receive/',
            action_label='Restock Now',
        )

    # ===== OUT OF STOCK =====
    out_of_stock = Product.objects.filter(quantity_in_stock__lte=0)
    for product in out_of_stock:
        create_notif(
            title=f"Out of Stock: {product.product_name}",
            message=f"{product.product_name} is completely out of stock. Customers cannot purchase this item.",
            notif_type='danger',
            action_url='/inventory/receive/',
            action_label='Restock Now',
        )

    # ===== SALES TREND =====
    today = timezone.now().date()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)

    today_sales = Sale.objects.filter(
        sale_date__date=today, status='completed'
    ).aggregate(total=Sum('total_amount'))['total'] or 0

    yesterday_sales = Sale.objects.filter(
        sale_date__date=yesterday, status='completed'
    ).aggregate(total=Sum('total_amount'))['total'] or 0

    if yesterday_sales > 0 and today_sales > 0:
        change = ((today_sales - yesterday_sales) / yesterday_sales) * 100
        if change >= 10:
            create_notif(
                title=f"Sales Up {change:.0f}% Today!",
                message=f"Today's sales (Le {today_sales:,.2f}) are {change:.0f}% higher than yesterday (Le {yesterday_sales:,.2f}). Great performance!",
                notif_type='success',
                action_url='/sales/',
                action_label='View Sales',
            )
        elif change <= -20:
            create_notif(
                title=f"Sales Down {abs(change):.0f}% Today",
                message=f"Today's sales (Le {today_sales:,.2f}) are {abs(change):.0f}% lower than yesterday. Consider running a promotion.",
                notif_type='warning',
                action_url='/sales/',
                action_label='View Sales',
            )

    # ===== DEMAND INTELLIGENCE =====
    week_requests = CustomerRequest.objects.filter(
        requested_at__date__gte=week_ago,
        status='pending'
    ).values('product_name_requested').annotate(
        count=Count('id')
    ).order_by('-count')[:3]

    for req in week_requests:
        if req['count'] >= 2:
            create_notif(
                title=f"High Demand: {req['product_name_requested']}",
                message=f"Customers requested '{req['product_name_requested']}' {req['count']} times this week. Consider stocking this product.",
                notif_type='info',
                action_url='/demand/',
                action_label='View Requests',
            )

    # ===== WEEKLY SUMMARY =====
    week_revenue = Sale.objects.filter(
        sale_date__date__gte=week_ago,
        status='completed'
    ).aggregate(total=Sum('total_amount'))['total'] or 0

    week_expenses = Expense.objects.filter(
        expense_date__gte=week_ago
    ).aggregate(total=Sum('amount'))['total'] or 0

    week_profit = week_revenue - week_expenses

    if week_revenue > 0:
        create_notif(
            title="Weekly Business Summary",
            message=f"This week: Revenue Le {week_revenue:,.2f} | Expenses Le {week_expenses:,.2f} | Net Profit Le {week_profit:,.2f}.",
            notif_type='ai',
            action_url='/',
            action_label='View Dashboard',
        )
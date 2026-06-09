from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import models
from .models import StockReceipt, InventoryAdjustment
from .forms import StockReceiptForm, InventoryAdjustmentForm
from products.models import Product

@login_required
def inventory_list(request):
    products = Product.objects.select_related('category', 'supplier').all()
    return render(request, 'inventory/inventory_list.html', {'products': products})

@login_required
def stock_receive(request):
    if request.method == 'POST':
        form = StockReceiptForm(request.POST)
        if form.is_valid():
            receipt = form.save(commit=False)
            receipt.received_by = request.user
            receipt.save()
            messages.success(request, 'Stock received successfully!')
            return redirect('inventory_list')
    else:
        form = StockReceiptForm()
    return render(request, 'inventory/stock_receive.html', {'form': form, 'title': 'Receive Stock'})

@login_required
def stock_adjust(request):
    if request.method == 'POST':
        form = InventoryAdjustmentForm(request.POST)
        if form.is_valid():
            adjustment = form.save(commit=False)
            adjustment.adjusted_by = request.user
            adjustment.save()
            messages.success(request, 'Inventory adjusted successfully!')
            return redirect('inventory_list')
    else:
        form = InventoryAdjustmentForm()
    return render(request, 'inventory/stock_adjust.html', {'form': form, 'title': 'Adjust Stock'})

@login_required
def low_stock(request):
    products = Product.objects.filter(quantity_in_stock__lte=models.F('reorder_level'))
    return render(request, 'inventory/low_stock.html', {'products': products})
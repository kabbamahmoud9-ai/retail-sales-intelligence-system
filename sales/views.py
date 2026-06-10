from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.forms import formset_factory
from .models import Sale, SaleItem
from .forms import SaleForm, SaleItemForm
from products.models import Product

@login_required
def sale_list(request):
    sales = Sale.objects.select_related('served_by').order_by('-sale_date')
    return render(request, 'sales/sale_list.html', {'sales': sales})

@login_required
def sale_new(request):
    SaleItemFormSet = formset_factory(SaleItemForm, extra=3)
    if request.method == 'POST':
        form = SaleForm(request.POST)
        formset = SaleItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            sale = form.save(commit=False)
            sale.served_by = request.user
            sale.save()
            for f in formset:
                if f.cleaned_data.get('product'):
                    item = f.save(commit=False)
                    item.sale = sale
                    item.save()
            sale.calculate_total()
            messages.success(request, 'Sale recorded successfully!')
            return redirect('sale_list')
    else:
        form = SaleForm()
        formset = SaleItemFormSet()
    return render(request, 'sales/sale_new.html', {
        'form': form,
        'formset': formset,
        'products': Product.objects.all()
    })

@login_required
def sale_detail(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    items = sale.saleitem_set.select_related('product').all()
    return render(request, 'sales/sale_detail.html', {'sale': sale, 'items': items})

@login_required
def sale_delete(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    if request.method == 'POST':
        sale.delete()
        messages.success(request, 'Sale deleted successfully!')
        return redirect('sale_list')
    return render(request, 'sales/sale_confirm_delete.html', {'sale': sale})
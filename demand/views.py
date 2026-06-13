from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import CustomerRequest
from .forms import CustomerRequestForm

@login_required
def request_list(request):
    requests = CustomerRequest.objects.select_related('product', 'recorded_by').all()
    pending_count = requests.filter(status='pending').count()
    return render(request, 'demand/request_list.html', {
        'requests': requests,
        'pending_count': pending_count,
    })

@login_required
def request_add(request):
    if request.method == 'POST':
        form = CustomerRequestForm(request.POST)
        if form.is_valid():
            req = form.save(commit=False)
            req.recorded_by = request.user
            req.save()
            messages.success(request, 'Customer request logged successfully!')
            return redirect('request_list')
    else:
        form = CustomerRequestForm()
    return render(request, 'demand/request_form.html', {'form': form, 'title': 'Log Customer Request'})

@login_required
def request_edit(request, pk):
    req = get_object_or_404(CustomerRequest, pk=pk)
    if request.method == 'POST':
        form = CustomerRequestForm(request.POST, instance=req)
        if form.is_valid():
            form.save()
            messages.success(request, 'Request updated successfully!')
            return redirect('request_list')
    else:
        form = CustomerRequestForm(instance=req)
    return render(request, 'demand/request_form.html', {'form': form, 'title': 'Edit Request'})

@login_required
def request_delete(request, pk):
    req = get_object_or_404(CustomerRequest, pk=pk)
    if request.method == 'POST':
        req.delete()
        messages.success(request, 'Request deleted successfully!')
        return redirect('request_list')
    return render(request, 'demand/request_confirm_delete.html', {'request_obj': req})
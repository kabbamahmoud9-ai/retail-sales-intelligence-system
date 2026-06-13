from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Expense, ExpenseCategory
from .forms import ExpenseForm, ExpenseCategoryForm

@login_required
def expense_list(request):
    expenses = Expense.objects.select_related('category', 'recorded_by').order_by('-expense_date')
    total = sum(e.amount for e in expenses)
    return render(request, 'expenses/expense_list.html', {'expenses': expenses, 'total': total})

@login_required
def expense_add(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.recorded_by = request.user
            expense.save()
            messages.success(request, 'Expense recorded successfully!')
            return redirect('expense_list')
    else:
        form = ExpenseForm()
    return render(request, 'expenses/expense_form.html', {'form': form, 'title': 'Add Expense'})

@login_required
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        expense.delete()
        messages.success(request, 'Expense deleted successfully!')
        return redirect('expense_list')
    return render(request, 'expenses/expense_confirm_delete.html', {'expense': expense})

@login_required
def expense_category_list(request):
    categories = ExpenseCategory.objects.all()
    return render(request, 'expenses/expense_category_list.html', {'categories': categories})

@login_required
def expense_category_add(request):
    if request.method == 'POST':
        form = ExpenseCategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Expense category added successfully!')
            return redirect('expense_category_list')
    else:
        form = ExpenseCategoryForm()
    return render(request, 'expenses/expense_category_form.html', {'form': form, 'title': 'Add Expense Category'})
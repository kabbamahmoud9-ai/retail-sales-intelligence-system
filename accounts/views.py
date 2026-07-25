from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .forms import RegisterForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import render, redirect 


def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password')
    return render(request, 'accounts/login.html')

def logout_view(request):
    logout(request)
    return redirect('login')

def register_view(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Account created successfully!')
            return redirect('login')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})



@login_required
def staff_profile(request):
    """Staff profile view/edit + avatar upload."""
    user = request.user

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip().lower()

        if not email:
            messages.error(request, "Email is required.")
        else:
            user.first_name = first_name
            user.last_name = last_name
            user.email = email
            if 'profile_picture' in request.FILES:
                user.profile_picture = request.FILES['profile_picture']
            user.save()
            messages.success(request, "Profile updated successfully.")
            return redirect('staff_profile')

    return render(request, 'accounts/profile.html', {'staff_user': user})


@login_required
def staff_change_password(request):
    """
    Staff password change — reuses Django's built-in PasswordChangeForm,
    which already handles current-password verification and validation
    rules correctly, rather than reimplementing that logic a second time
    (the customer side needed its own version since OnlineCustomer isn't
    a Django auth user at all; CustomUser already is one).
    """
    if request.method == 'POST':
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # keeps the user logged in after password change
            messages.success(request, "Password changed successfully.")
            return redirect('staff_profile')
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
    else:
        form = PasswordChangeForm(user=request.user)

    return render(request, 'accounts/change_password.html', {'form': form})

@login_required
def staff_remove_profile_picture(request):
    """Same pattern as the customer-side equivalent — file cleanup + field clear only."""
    if request.method != 'POST':
        return redirect('staff_profile')

    user = request.user
    if user.profile_picture:
        user.profile_picture.delete(save=False)
        user.profile_picture = None
        user.save(update_fields=['profile_picture'])
        messages.success(request, "Profile picture removed. Using default avatar.")
    return redirect('staff_profile')
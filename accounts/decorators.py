from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def owner_required(view_func):
    """
    Restricts a view to shop-owner/admin accounts. Stacks login_required
    underneath, so an anonymous user is redirected to login as usual;
    an authenticated user whose role isn't 'admin' (and who isn't a
    Django superuser) gets a 403 instead of the view ever running.
    """
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.role != 'admin' and not request.user.is_superuser:
            raise PermissionDenied("This section is restricted to shop owner accounts.")
        return view_func(request, *args, **kwargs)
    return _wrapped

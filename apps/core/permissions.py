from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse


def is_console_staff(user) -> bool:
    """Checks whether the user is an authenticated staff member."""
    return bool(user and user.is_authenticated and user.is_staff)


def is_operations_manager(user) -> bool:
    """
    Checks if user is an Operations Manager or Administrator.
    Superusers automatically qualify. Staff members qualify unless strictly restricted to Support/Production.
    """
    if not is_console_staff(user):
        return False
    if user.is_superuser:
        return True
    # If in specific Manager group, or general staff not restricted to Support
    user_groups = set(user.groups.values_list("name", flat=True))
    if "Operations Manager" in user_groups or "Administrator" in user_groups:
        return True
    if "Support Staff" in user_groups:
        return False
    return True


def can_manage_pins(user) -> bool:
    """Only managers and admins can view one-time packaging PINs or trigger PIN regeneration."""
    return is_operations_manager(user)


def console_staff_required(view_func):
    """Decorator requiring staff credentials. Redirects unauthenticated to login."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('accounts:login')}?next={request.path}")
        if not request.user.is_staff:
            raise PermissionDenied("Staff credentials required to access STRIDE Console.")
        return view_func(request, *args, **kwargs)
    return _wrapped


def manager_required(view_func):
    """Decorator requiring Operations Manager or Superuser credentials."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('accounts:login')}?next={request.path}")
        if not is_operations_manager(request.user):
            raise PermissionDenied("Operations Manager or Administrator authorization required for this action.")
        return view_func(request, *args, **kwargs)
    return _wrapped

import time
from functools import wraps
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.shortcuts import redirect

def get_client_ip(request):
    """Safely extracts client IP address, handling proxy headers if present."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '')
    return ip or '127.0.0.1'


def check_rate_limit(key: str, limit: int = 5, window_seconds: int = 300):
    """
    Cache-backed sliding/window rate limiting helper.
    Returns: (is_allowed: bool, remaining: int, retry_after: int)
    """
    now = int(time.time())
    cache_key = f"rl:{key}"
    data = cache.get(cache_key)

    if data is None:
        # First hit in the window
        cache.set(cache_key, {'count': 1, 'start': now}, timeout=window_seconds)
        return True, limit - 1, 0

    count = data.get('count', 0)
    start = data.get('start', now)
    elapsed = now - start

    if elapsed >= window_seconds:
        # Window expired, reset
        cache.set(cache_key, {'count': 1, 'start': now}, timeout=window_seconds)
        return True, limit - 1, 0

    if count >= limit:
        retry_after = max(1, window_seconds - elapsed)
        return False, 0, retry_after

    # Increment counter
    new_count = count + 1
    remaining_time = max(1, window_seconds - elapsed)
    cache.set(cache_key, {'count': new_count, 'start': start}, timeout=remaining_time)
    return True, max(0, limit - new_count), 0


def rate_limited(key_prefix: str, limit: int = 5, window_seconds: int = 300, redirect_url: str = None):
    """
    Decorator for views to enforce rate limiting by IP (or user ID if authenticated).
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            ident = str(request.user.id) if request.user.is_authenticated else get_client_ip(request)
            key = f"{key_prefix}:{ident}"
            allowed, remaining, retry_after = check_rate_limit(key, limit=limit, window_seconds=window_seconds)

            if not allowed:
                msg = f"Too many requests. Please try again in {retry_after} seconds."
                if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
                    resp = JsonResponse({'status': 'error', 'message': msg, 'retry_after': retry_after}, status=429)
                    resp['Retry-After'] = str(retry_after)
                    return resp

                messages.error(request, msg)
                if redirect_url:
                    return redirect(redirect_url)
                resp = HttpResponse(msg, status=429)
                resp['Retry-After'] = str(retry_after)
                return resp

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

import logging
import time
from functools import wraps
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

logger = logging.getLogger('stride.security')

SENSITIVE_RATE_LIMIT_PREFIXES = {
    'login',
    'reg',
    'card_act',
    'card_act_card',
    'card_act_ip',
    'otp_verify',
    'otp_resend',
    'pwd_reset',
}


class RateLimitServiceUnavailable(Exception):
    """
    Raised when the rate limiting backend (Redis) is unavailable for a sensitive security operation.
    Converted by RateLimitResilienceMiddleware into a controlled HTTP 503 response.
    """
    def __init__(self, message="Security verification service is temporarily unavailable. Please retry in a few moments.", retry_after=30):
        self.message = message
        self.retry_after = retry_after
        super().__init__(message)


class RateLimitResilienceMiddleware:
    """
    Catches RateLimitServiceUnavailable exceptions and renders a safe, controlled
    HTTP 503 Service Unavailable response without leaking tracebacks, Redis credentials,
    or internal topology details.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if isinstance(exception, RateLimitServiceUnavailable):
            retry_after = getattr(exception, 'retry_after', 30)
            msg = getattr(exception, 'message', "Security verification service is temporarily unavailable. Please retry in a few moments.")
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
                resp = JsonResponse({'status': 'error', 'message': msg, 'retry_after': retry_after}, status=503)
                resp['Retry-After'] = str(retry_after)
                return resp

            html_content = (
                "<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'>"
                "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
                "<title>Service Temporarily Unavailable — STRIDE</title>"
                "<style>"
                "body { background: #0A0A0A; color: #FFFFFF; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 24px; box-sizing: border-box; text-align: center; }"
                ".card { background: #121214; border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; padding: 40px; max-width: 480px; width: 100%; box-shadow: 0 20px 40px rgba(0,0,0,0.6); }"
                "h1 { font-size: 1.25rem; font-weight: 700; margin: 0 0 12px; letter-spacing: -0.01em; }"
                "p { color: #A1A1AA; font-size: 0.9375rem; line-height: 1.5; margin: 0 0 24px; }"
                ".btn { display: inline-block; background: #FFFFFF; color: #0A0A0A; padding: 10px 24px; border-radius: 9999px; font-weight: 600; font-size: 0.875rem; text-decoration: none; }"
                "</style></head><body>"
                "<div class='card'>"
                "<h1>Security Service Temporarily Unavailable</h1>"
                f"<p>{msg}</p>"
                "<a href='javascript:location.reload()' class='btn'>Retry Connection</a>"
                "</div></body></html>"
            )
            resp = HttpResponse(html_content, status=503, content_type="text/html; charset=utf-8")
            resp['Retry-After'] = str(retry_after)
            return resp
        return None


def get_client_ip(request):
    """Safely extracts client IP address, handling proxy headers if present."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '')
    return ip or '127.0.0.1'


def check_rate_limit(key: str, limit: int = 5, window_seconds: int = 300, sensitive: bool = None):
    """
    Cache-backed sliding/window rate limiting helper.
    Returns: (is_allowed: bool, remaining: int, retry_after: int)

    Resilience Policy:
    - If Redis is unavailable:
      * Sensitive operations (login, registration, card activation, OTP, password reset):
        Raises RateLimitServiceUnavailable, converted by RateLimitResilienceMiddleware into a controlled 503 response.
        Fails closed to protect against brute-force attacks during cache outages.
      * Non-sensitive operations (contact, complaints, analytics beacons):
        Logs degraded operation and fails open (allowed=True), preventing disruption to public inquiries.
    - Exceptions never leak IP addresses, credentials, or internal topology.
    """
    prefix = key.split(':')[0] if ':' in key else key
    if sensitive is None:
        sensitive = prefix in SENSITIVE_RATE_LIMIT_PREFIXES

    now = int(time.time())
    cache_key = f"rl:{key}"

    try:
        data = cache.get(cache_key)
    except Exception as exc:
        if sensitive:
            logger.warning(
                "Rate limiting backend unavailable for sensitive operation (prefix: '%s', error: %s). Failing closed with 503.",
                prefix, type(exc).__name__
            )
            raise RateLimitServiceUnavailable(
                message="Security verification service is temporarily unavailable. Please retry in a few moments.",
                retry_after=30
            ) from exc
        else:
            logger.warning(
                "Rate limiting backend unavailable for operation (prefix: '%s', error: %s). Operating in degraded mode.",
                prefix, type(exc).__name__
            )
            return True, limit, 0

    if data is None:
        try:
            cache.set(cache_key, {'count': 1, 'start': now}, timeout=window_seconds)
        except Exception as exc:
            if sensitive:
                logger.warning(
                    "Rate limiting backend write failure for sensitive operation (prefix: '%s', error: %s). Failing closed with 503.",
                    prefix, type(exc).__name__
                )
                raise RateLimitServiceUnavailable(
                    message="Security verification service is temporarily unavailable. Please retry in a few moments.",
                    retry_after=30
                ) from exc
            else:
                logger.warning(
                    "Rate limiting backend write failure for operation (prefix: '%s', error: %s).",
                    prefix, type(exc).__name__
                )
        return True, limit - 1, 0

    count = data.get('count', 0)
    start = data.get('start', now)
    elapsed = now - start

    if elapsed >= window_seconds:
        try:
            cache.set(cache_key, {'count': 1, 'start': now}, timeout=window_seconds)
        except Exception as exc:
            if sensitive:
                raise RateLimitServiceUnavailable() from exc
        return True, limit - 1, 0

    if count >= limit:
        retry_after = max(1, window_seconds - elapsed)
        return False, 0, retry_after

    new_count = count + 1
    remaining_time = max(1, window_seconds - elapsed)
    try:
        cache.set(cache_key, {'count': new_count, 'start': start}, timeout=remaining_time)
    except Exception as exc:
        if sensitive:
            raise RateLimitServiceUnavailable() from exc
    return True, max(0, limit - new_count), 0


def rate_limited(key_prefix: str, limit: int = 5, window_seconds: int = 300, redirect_url: str = None, sensitive: bool = None):
    """
    Decorator for views to enforce rate limiting by IP (or user ID if authenticated).
    Handles RateLimitServiceUnavailable gracefully by returning HTTP 503.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            ident = str(request.user.id) if request.user.is_authenticated else get_client_ip(request)
            key = f"{key_prefix}:{ident}"
            try:
                allowed, remaining, retry_after = check_rate_limit(key, limit=limit, window_seconds=window_seconds, sensitive=sensitive)
            except RateLimitServiceUnavailable as e:
                retry_after = getattr(e, 'retry_after', 30)
                msg = str(e)
                if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
                    resp = JsonResponse({'status': 'error', 'message': msg, 'retry_after': retry_after}, status=503)
                    resp['Retry-After'] = str(retry_after)
                    return resp
                resp = HttpResponse(msg, status=503)
                resp['Retry-After'] = str(retry_after)
                return resp

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


def is_safe_redirect_url(request, url):
    """
    Validates that a URL is safe for internal redirection.
    Guards:
    1. Must be a non-empty string.
    2. Must not contain null bytes or control/newline characters.
    3. Must not be protocol-relative (cannot start with '//', '/\\', '\\\\').
    4. Must pass Django's url_has_allowed_host_and_scheme for request.get_host().
    """
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if not url:
        return False
    # Check for null bytes or control characters
    if any(ord(c) < 32 or ord(c) == 127 for c in url):
        return False
    # Explicitly disallow protocol-relative and backslash evasion attempts
    if url.startswith('//') or url.startswith('/\\') or url.startswith('\\\\'):
        return False
    # Django host & scheme validation
    return url_has_allowed_host_and_scheme(
        url=url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure()
    )


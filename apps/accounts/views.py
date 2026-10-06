from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash, get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode, url_has_allowed_host_and_scheme
from django.utils.encoding import force_bytes, force_str
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import (
    UserRegisterForm,
    UserLoginForm,
    UserUpdateForm,
    PasswordResetRequestForm,
    OTPVerifyForm,
)
from .models import OTPCode
from apps.profiles.models import Profile
from apps.core.security import check_rate_limit, get_client_ip
from apps.core.services.email_service import BrevoEmailService

User = get_user_model()


def register_view(request):
    """Register new customer, dispatch welcome email + OTP, and auto-provision digital profile."""
    if request.user.is_authenticated:
        return redirect('dashboard:overview')

    ip = get_client_ip(request)
    # Rate limit: max 5 registrations per IP per hour
    allowed, remaining, retry_after = check_rate_limit(f"reg:{ip}", limit=5, window_seconds=3600)
    if not allowed:
        messages.error(request, f"Too many registration attempts. Please try again in {retry_after} seconds.")
        return render(request, 'accounts/register.html', {'form': UserRegisterForm()})

    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.is_email_verified = False
            user.save()

            # Auto-provision profile
            profile, _ = Profile.objects.get_or_create(user=user)
            full_name = f"{user.first_name} {user.last_name}".strip() or user.email.split('@')[0]
            profile.full_name = full_name
            profile.email = user.email
            if user.phone:
                profile.phone = user.phone
                profile.whatsapp = user.phone
            profile.save()

            # Generate OTP code & send Welcome email via Brevo
            plain_code = None
            email_res = {}
            try:
                otp, plain_code = OTPCode.generate_otp(
                    user=user,
                    email=user.email,
                    purpose=OTPCode.PURPOSE_EMAIL_VERIFICATION,
                    duration_minutes=10,
                    ip=ip,
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
                email_res = BrevoEmailService.send_welcome_email(user, verification_otp=plain_code)
                print(f"\n[UZYRA OTP] Email: {user.email} | Code: {plain_code} | Brevo Result: {email_res}\n", flush=True)
            except Exception as e:
                import logging
                logging.getLogger('uzyra.auth').error(f"Failed to dispatch welcome email: {e}")

            login(request, user)
            request.session['pending_verification_email'] = user.email
            if email_res.get('success') and email_res.get('mode') == 'live':
                messages.success(request, f"Welcome to UZYRA, {user.first_name or 'there'}! A 6-digit verification code has been sent to your email.")
            elif email_res.get('mode') == 'simulated':
                messages.info(request, f"Welcome to UZYRA! (Staging note: Brevo API key not set in environment). Your verification code is: {plain_code}")
            elif plain_code:
                messages.warning(request, f"Welcome to UZYRA! Brevo email notice: {email_res.get('error', 'Check sender verification')}. Staging code: {plain_code}")
            else:
                messages.success(request, f"Welcome to UZYRA! Please verify your email.")
            return redirect('accounts:verify_otp')
    else:
        form = UserRegisterForm()

    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    """Customer & Admin login with brute-force rate-limiting and Open Redirect protection."""
    if request.user.is_authenticated:
        return redirect('dashboard:overview')

    ip = get_client_ip(request)

    if request.method == 'POST':
        # Rate limit: max 5 failed attempts per IP per 5 minutes
        allowed, remaining, retry_after = check_rate_limit(f"login:{ip}", limit=5, window_seconds=300)
        if not allowed:
            messages.error(request, f"Too many failed login attempts. Account access is throttled. Please try again in {retry_after} seconds.")
            return render(request, 'accounts/login.html', {'form': UserLoginForm()})

        form = UserLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Welcome back, {user.display_name}!")

            # Open Redirect defense: validate destination host strictly
            next_url = request.GET.get('next') or request.POST.get('next')
            if next_url and url_has_allowed_host_and_scheme(
                url=next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure()
            ):
                return redirect(next_url)
            return redirect('dashboard:overview')
        else:
            messages.error(request, "Invalid email or password. Please check your credentials.")
    else:
        form = UserLoginForm()

    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    """Sign out securely and clear session."""
    logout(request)
    messages.info(request, "You have been securely signed out.")
    return redirect('core:home')


# =============================================================================
# EMAIL VERIFICATION & OTP VIEWS
# =============================================================================

def verify_email_otp_view(request):
    """
    Validates a 6-digit OTP to verify user email address.
    Enforces expiration, attempt tracking, single-use invalidation, and rate limiting.
    """
    target_email = None
    if request.user.is_authenticated:
        target_email = request.user.email
    elif 'pending_verification_email' in request.session:
        target_email = request.session['pending_verification_email']

    if not target_email:
        messages.info(request, "Please log in to verify your email address.")
        return redirect('accounts:login')

    if request.user.is_authenticated and getattr(request.user, 'is_email_verified', False):
        messages.info(request, "Your email is already verified.")
        return redirect('dashboard:overview')

    ip = get_client_ip(request)

    if request.method == 'POST':
        # Rate limit OTP verify: max 5 attempts per IP per 5 minutes
        allowed, remaining, retry_after = check_rate_limit(f"otp_verify:{ip}", limit=5, window_seconds=300)
        if not allowed:
            messages.error(request, f"Too many verification attempts. Please wait {retry_after} seconds before trying again.")
            return render(request, 'accounts/verify_otp.html', {'form': OTPVerifyForm(), 'email': target_email})

        form = OTPVerifyForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['otp_code']
            success, msg = OTPCode.verify_code(target_email, OTPCode.PURPOSE_EMAIL_VERIFICATION, code)
            if success:
                if request.user.is_authenticated:
                    request.user.is_email_verified = True
                    request.user.save(update_fields=['is_email_verified'])
                else:
                    User.objects.filter(email__iexact=target_email).update(is_email_verified=True)

                if 'pending_verification_email' in request.session:
                    del request.session['pending_verification_email']

                messages.success(request, "Email verified successfully! Your account is now fully active.")
                return redirect('dashboard:overview')
            else:
                messages.error(request, msg)
    else:
        form = OTPVerifyForm()

    return render(request, 'accounts/verify_otp.html', {'form': form, 'email': target_email})


def resend_otp_view(request):
    """Throttled resend endpoint with 60-second cooldown."""
    target_email = None
    if request.user.is_authenticated:
        target_email = request.user.email
    elif 'pending_verification_email' in request.session:
        target_email = request.session['pending_verification_email']

    if not target_email:
        return redirect('accounts:login')

    ip = get_client_ip(request)
    # Cooldown rate limit: max 1 per 60 seconds
    allowed, remaining, retry_after = check_rate_limit(f"otp_resend:{target_email}", limit=1, window_seconds=60)
    if not allowed:
        messages.warning(request, f"Please wait {retry_after} seconds before requesting another code.")
        return redirect('accounts:verify_otp')

    try:
        user = request.user if request.user.is_authenticated else User.objects.filter(email__iexact=target_email).first()
        otp, plain_code = OTPCode.generate_otp(
            user=user,
            email=target_email,
            purpose=OTPCode.PURPOSE_EMAIL_VERIFICATION,
            duration_minutes=10,
            ip=ip,
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        email_res = BrevoEmailService.send_email_verification_otp(target_email, plain_code, user.display_name if user else None)
        print(f"\n[UZYRA OTP RESEND] Email: {target_email} | Code: {plain_code} | Brevo Result: {email_res}\n", flush=True)
        if email_res.get('success'):
            if email_res.get('mode') == 'simulated':
                messages.info(request, f"Staging Note: Brevo in simulated mode. Your verification code is: {plain_code}")
            else:
                messages.success(request, "A fresh verification code has been dispatched to your email.")
        else:
            messages.warning(request, f"Brevo delivery issue ({email_res.get('error')}). Staging code: {plain_code}")
    except Exception as e:
        messages.error(request, f"Could not send verification email at this time: {e}")

    return redirect('accounts:verify_otp')


# =============================================================================
# PASSWORD RESET VIEWS (GENERIC RESPONSES, NO USER ENUMERATION)
# =============================================================================

def password_reset_request_view(request):
    """
    Step 1: User enters email.
    GENERIC RESPONSE: Never reveals whether the email exists in the database.
    Rate limited: max 5 requests per IP per hour.
    """
    if request.user.is_authenticated:
        return redirect('dashboard:overview')

    ip = get_client_ip(request)

    if request.method == 'POST':
        # Rate limit: max 5 per IP per hour
        allowed, remaining, retry_after = check_rate_limit(f"pwd_reset:{ip}", limit=5, window_seconds=3600)
        if not allowed:
            messages.error(request, f"Too many password reset requests. Please wait {retry_after} seconds before trying again.")
            return redirect('accounts:password_reset')

        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            user = User.objects.filter(email__iexact=email).first()
            if user and user.is_active:
                token = default_token_generator.make_token(user)
                uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
                reset_path = reverse('accounts:password_reset_confirm', kwargs={'uidb64': uidb64, 'token': token})
                reset_url = request.build_absolute_uri(reset_path)
                BrevoEmailService.send_password_reset_email(user, reset_url)

            # ALWAYS redirect to done with generic message (no user enumeration)
            return redirect('accounts:password_reset_done')
    else:
        form = PasswordResetRequestForm()

    return render(request, 'accounts/password_reset.html', {'form': form})


def password_reset_done_view(request):
    """Step 2: Generic instruction notice rendered after reset request."""
    return render(request, 'accounts/password_reset_done.html')


def password_reset_confirm_view(request, uidb64, token):
    """
    Step 3: User clicks link with cryptographic one-time token.
    Token is invalidated immediately upon successful password change or expiration.
    """
    if request.user.is_authenticated:
        return redirect('dashboard:overview')

    user = None
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is None or not default_token_generator.check_token(user, token):
        return render(request, 'accounts/password_reset_confirm.html', {'validlink': False})

    if request.method == 'POST':
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            user = form.save()
            # Send security notification email via Brevo
            BrevoEmailService.send_password_changed_notification(user)
            messages.success(request, "Your password has been successfully reset! You may now sign in.")
            return redirect('accounts:password_reset_complete')
    else:
        form = SetPasswordForm(user)

    return render(request, 'accounts/password_reset_confirm.html', {'form': form, 'validlink': True})


def password_reset_complete_view(request):
    """Step 4: Password reset completed successfully."""
    return render(request, 'accounts/password_reset_complete.html')


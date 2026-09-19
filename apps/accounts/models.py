from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _

class UserManager(BaseUserManager):
    """Define a model manager for User model with no username field."""

    def _create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('The Email must be set'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Custom User model where email is the unique identifier for authentication."""
    username = None
    email = models.EmailField(_('email address'), unique=True)
    phone = models.CharField(_('phone number'), max_length=30, blank=True, null=True)
    is_email_verified = models.BooleanField(_('email verified'), default=False)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    objects = UserManager()

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['-date_joined']

    def __str__(self):
        full = f"{self.first_name} {self.last_name}".strip()
        return full if full else self.email

    @property
    def display_name(self):
        full = f"{self.first_name} {self.last_name}".strip()
        return full if full else self.email.split('@')[0]


import hashlib
import hmac
import secrets
from datetime import timedelta
from django.utils import timezone

class OTPCode(models.Model):
    """
    Cryptographically secure, single-use, scoped OTP token storage.
    Codes are hashed with SHA-256 before storage — plaintext codes are never stored in the database.
    """
    PURPOSE_EMAIL_VERIFICATION = 'email_verification'
    PURPOSE_PASSWORD_RESET = 'password_reset'
    PURPOSE_CARD_ACTIVATION = 'card_activation'
    PURPOSE_EMAIL_CHANGE = 'email_change'
    PURPOSE_HIGH_RISK = 'high_risk'

    PURPOSE_CHOICES = (
        (PURPOSE_EMAIL_VERIFICATION, 'Email Verification'),
        (PURPOSE_PASSWORD_RESET, 'Password Reset'),
        (PURPOSE_CARD_ACTIVATION, 'Card Activation'),
        (PURPOSE_EMAIL_CHANGE, 'Email Address Change'),
        (PURPOSE_HIGH_RISK, 'High Risk Action Verification'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='otp_codes')
    email = models.EmailField(db_index=True)
    purpose = models.CharField(max_length=30, choices=PURPOSE_CHOICES, db_index=True)
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    is_consumed = models.BooleanField(default=False, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email', 'purpose', 'is_consumed', 'expires_at']),
        ]

    def __str__(self):
        return f"OTP [{self.purpose}] for {self.email} (Consumed: {self.is_consumed})"

    @staticmethod
    def hash_code(plain_code: str) -> str:
        return hashlib.sha256(plain_code.strip().encode('utf-8')).hexdigest()

    def check_code(self, plain_code: str) -> bool:
        expected = self.code_hash
        actual = self.hash_code(plain_code)
        return hmac.compare_digest(expected, actual)

    @classmethod
    def generate_otp(cls, user=None, email='', purpose=PURPOSE_EMAIL_VERIFICATION, duration_minutes=10, ip=None, user_agent=''):
        """
        Generates a cryptographically random 6-digit OTP, invalidates existing active OTPs for the same
        recipient & purpose, hashes the code, and returns (otp_record, plaintext_code).
        """
        target_email = (email or (user.email if user else '')).strip().lower()
        if not target_email:
            raise ValueError("An email address must be provided for OTP generation.")

        # Invalidate existing unconsumed active OTPs for this email and purpose
        cls.objects.filter(
            email__iexact=target_email,
            purpose=purpose,
            is_consumed=False
        ).update(is_consumed=True)

        # Cryptographically secure 6-digit code
        plaintext_code = "".join([secrets.choice('0123456789') for _ in range(6)])
        code_hash = cls.hash_code(plaintext_code)
        expires_at = timezone.now() + timedelta(minutes=duration_minutes)

        otp = cls.objects.create(
            user=user,
            email=target_email,
            purpose=purpose,
            code_hash=code_hash,
            expires_at=expires_at,
            max_attempts=5,
            is_consumed=False,
            ip_address=ip,
            user_agent=user_agent[:255] if user_agent else ''
        )
        return otp, plaintext_code

    @classmethod
    def verify_code(cls, email_or_user, purpose: str, plain_code: str):
        """
        Authoritative server-side verification of an OTP:
        Enforces expiration, max attempts, single-use invalidation, and constant-time comparison.
        Returns: (success: bool, message: str)
        """
        if hasattr(email_or_user, 'email'):
            target_email = email_or_user.email.strip().lower()
        else:
            target_email = str(email_or_user).strip().lower()

        now = timezone.now()
        candidate = cls.objects.filter(
            email__iexact=target_email,
            purpose=purpose,
            expires_at__gt=now
        ).order_by('-created_at').first()

        if not candidate or candidate.is_consumed:
            if candidate and candidate.attempts >= candidate.max_attempts:
                return False, "Too many failed attempts. This code has been invalidated for security."
            return False, "Verification code has expired or is invalid. Please request a new code."

        if candidate.attempts >= candidate.max_attempts:
            candidate.is_consumed = True
            candidate.save()
            return False, "Too many failed attempts. This code has been invalidated for security."

        candidate.attempts += 1

        if candidate.check_code(plain_code):
            candidate.is_consumed = True
            candidate.save()
            return True, "Verification successful."
        else:
            candidate.save()
            remaining = candidate.max_attempts - candidate.attempts
            if remaining <= 0:
                candidate.is_consumed = True
                candidate.save()
                return False, "Too many failed attempts. Code has been locked. Please request a new code."
            return False, f"Incorrect code. {remaining} attempt{'s' if remaining != 1 else ''} remaining."


import logging
import os
import requests
from django.conf import settings

logger = logging.getLogger('uzyra.email_service')

def _render_email_template(title: str, subtitle: str, body_html: str, cta_text: str = None, cta_url: str = None) -> str:
    """
    Renders high-contrast luxury graphite/silver branded HTML email template for UZYRA.
    """
    brand_name = getattr(settings, 'BRAND_NAME', 'UZYRA')
    support_email = getattr(settings, 'BRAND_SUPPORT_EMAIL', 'contact@uzyra.com')

    cta_section = ""
    if cta_text and cta_url:
        cta_section = f"""
        <div style="margin: 32px 0; text-align: center;">
            <a href="{cta_url}" target="_blank" style="background: linear-gradient(135deg, #FFFFFF 0%, #E2E8F0 100%); color: #0A0A0A; padding: 14px 32px; border-radius: 9999px; font-weight: 700; font-size: 15px; text-decoration: none; display: inline-block; letter-spacing: 0.05em; box-shadow: 0 4px 14px rgba(255,255,255,0.15);">
                {cta_text} &rarr;
            </a>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0A0A0A; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #FFFFFF; -webkit-font-smoothing: antialiased;">
<table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #0A0A0A; padding: 40px 16px;">
<tr>
<td align="center">
    <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 580px; background-color: #121214; border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 20px; overflow: hidden; box-shadow: 0 20px 40px rgba(0,0,0,0.6);">
        <!-- Header -->
        <tr>
            <td style="padding: 36px 36px 24px 36px; border-bottom: 1px solid rgba(255,255,255,0.06); text-align: center;">
                <div style="font-size: 22px; font-weight: 800; letter-spacing: 0.25em; color: #FFFFFF; text-transform: uppercase;">
                    {brand_name}
                </div>
                <div style="font-size: 11px; letter-spacing: 0.15em; color: #8E95A3; margin-top: 4px; text-transform: uppercase;">
                    Tactile Digital Identity
                </div>
            </td>
        </tr>
        <!-- Content -->
        <tr>
            <td style="padding: 36px;">
                <h1 style="font-size: 22px; font-weight: 700; color: #FFFFFF; margin: 0 0 8px 0; letter-spacing: -0.01em;">{title}</h1>
                {f'<p style="font-size: 14px; color: #BFC5CF; margin: 0 0 24px 0; line-height: 1.5;">{subtitle}</p>' if subtitle else ''}
                
                <div style="font-size: 15px; color: #E2E8F0; line-height: 1.6;">
                    {body_html}
                </div>

                {cta_section}

                <div style="margin-top: 32px; padding-top: 24px; border-top: 1px solid rgba(255,255,255,0.06); font-size: 12px; color: #71717A; line-height: 1.5;">
                    Security Note: If you did not initiate this request or have security concerns, please contact our security team immediately at <a href="mailto:{support_email}" style="color: #BFC5CF; text-decoration: underline;">{support_email}</a>.
                </div>
            </td>
        </tr>
        <!-- Footer -->
        <tr>
            <td style="padding: 24px 36px; background-color: #0E0E10; border-top: 1px solid rgba(255,255,255,0.04); text-align: center; font-size: 11px; color: #52525B;">
                &copy; 2026 {brand_name}. All rights reserved.<br>
                Secure Contactless NFC Systems & Premium Digital Architecture.
            </td>
        </tr>
    </table>
</td>
</tr>
</table>
</body>
</html>
"""


class BrevoEmailService:
    """
    Centralized Brevo (Sendinblue) Transactional Email Service.
    Safe, resilient, non-blocking fallback in development and testing.
    """

    @classmethod
    def get_api_key(cls) -> str:
        return os.environ.get('BREVO_API_KEY') or getattr(settings, 'BREVO_API_KEY', '')

    @classmethod
    def get_sender(cls) -> dict:
        sender_email = os.environ.get('BREVO_SENDER_EMAIL') or getattr(settings, 'BREVO_SENDER_EMAIL', 'contact@uzyra.com')
        sender_name = os.environ.get('BREVO_SENDER_NAME') or getattr(settings, 'BREVO_SENDER_NAME', 'UZYRA')
        return {"name": sender_name, "email": sender_email}

    @classmethod
    def send_transactional_email(cls, to_email: str, subject: str, html_content: str, to_name: str = None) -> dict:
        """
        Dispatches email via Brevo REST API v3.
        Gracefully falls back to local logging when API key is not configured or in tests.
        """
        api_key = cls.get_api_key()
        recipient_name = to_name or to_email.split('@')[0]
        sender = cls.get_sender()

        # Development / Testing fallback
        if not api_key or api_key == 'test_brevo_api_key' or getattr(settings, 'EMAIL_BACKEND', '').endswith('console.EmailBackend'):
            logger.info(
                f"[SIMULATED EMAIL via Brevo] To: {to_email} | Subject: '{subject}' | Sender: {sender['email']}"
            )
            return {"success": True, "mode": "simulated", "message_id": f"sim_{to_email}"}

        # Live Brevo API Dispatch
        endpoint = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        }
        payload = {
            "sender": sender,
            "to": [{"email": to_email, "name": recipient_name}],
            "subject": subject,
            "htmlContent": html_content,
        }

        try:
            response = requests.post(endpoint, json=payload, headers=headers, timeout=8)
            if response.status_code in [200, 201, 202]:
                data = response.json()
                logger.info(f"Brevo email sent successfully to {to_email}. MessageId: {data.get('messageId')}")
                return {"success": True, "mode": "live", "message_id": data.get('messageId')}
            else:
                logger.error(f"Brevo API error ({response.status_code}): {response.text}")
                return {"success": False, "mode": "live", "error": f"API {response.status_code}: {response.text}"}
        except Exception as e:
            logger.error(f"Brevo connection failure to {to_email}: {str(e)}")
            return {"success": False, "mode": "live", "error": str(e)}

    # -------------------------------------------------------------------------
    # 1. Welcome Email & Account Creation
    # -------------------------------------------------------------------------
    @classmethod
    def send_welcome_email(cls, user, verification_otp: str = None):
        first_name = user.first_name or "there"
        otp_block = ""
        if verification_otp:
            otp_block = f"""
            <div style="background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 20px; text-align: center; margin: 24px 0;">
                <div style="font-size: 12px; letter-spacing: 0.1em; color: #8E95A3; text-transform: uppercase; margin-bottom: 8px;">Verification Security Code</div>
                <div style="font-family: monospace; font-size: 32px; font-weight: 800; letter-spacing: 0.25em; color: #FFFFFF;">{verification_otp}</div>
                <div style="font-size: 12px; color: #71717A; margin-top: 8px;">Expires in 10 minutes. Single-use only.</div>
            </div>
            """

        body = f"""
        <p>Hello {first_name},</p>
        <p>Welcome to UZYRA. Your digital identity account and contactless NFC ecosystem have been initialized.</p>
        {otp_block}
        <p>From your dashboard, you can customize your digital business profile, link custom web presence packages, and manage your physical smart cards.</p>
        """
        html = _render_email_template(
            title="Welcome to UZYRA",
            subtitle="Your luxury digital identity platform",
            body_html=body,
            cta_text="Access Your Dashboard",
            cta_url=getattr(settings, 'SITE_URL', 'https://uzyra.com') + "/dashboard/"
        )
        return cls.send_transactional_email(user.email, "Welcome to UZYRA — Your Digital Identity", html, user.display_name)

    # -------------------------------------------------------------------------
    # 2. Email Verification OTP
    # -------------------------------------------------------------------------
    @classmethod
    def send_email_verification_otp(cls, email: str, code: str, user_name: str = None):
        name = user_name or "there"
        body = f"""
        <p>Hello {name},</p>
        <p>Please enter the 6-digit verification code below to verify your email address and secure your account:</p>
        <div style="background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 24px; text-align: center; margin: 24px 0;">
            <div style="font-size: 11px; letter-spacing: 0.15em; color: #8E95A3; text-transform: uppercase; margin-bottom: 8px;">Email Verification Code</div>
            <div style="font-family: monospace; font-size: 36px; font-weight: 800; letter-spacing: 0.3em; color: #FFFFFF;">{code}</div>
            <div style="font-size: 12px; color: #71717A; margin-top: 8px;">This code expires in 10 minutes and can only be used once.</div>
        </div>
        <p>If you did not request this verification code, please disregard this email.</p>
        """
        html = _render_email_template(
            title="Verify Your Email Address",
            subtitle="UZYRA One-Time Verification Code",
            body_html=body
        )
        return cls.send_transactional_email(email, f"{code} is your UZYRA verification code", html, user_name)

    # -------------------------------------------------------------------------
    # 3. Password Reset Request
    # -------------------------------------------------------------------------
    @classmethod
    def send_password_reset_email(cls, user, reset_url: str):
        first_name = user.first_name or "there"
        body = f"""
        <p>Hello {first_name},</p>
        <p>We received a request to reset the password for your UZYRA account associated with <strong>{user.email}</strong>.</p>
        <p>Click the button below to choose a new password. For security reasons, this link is single-use and will expire in 30 minutes:</p>
        """
        html = _render_email_template(
            title="Reset Your Account Password",
            subtitle="Secure cryptographic recovery link",
            body_html=body,
            cta_text="Reset Password",
            cta_url=reset_url
        )
        return cls.send_transactional_email(user.email, "Reset Your UZYRA Password", html, user.display_name)

    # -------------------------------------------------------------------------
    # 4. Password Changed Notification
    # -------------------------------------------------------------------------
    @classmethod
    def send_password_changed_notification(cls, user):
        first_name = user.first_name or "there"
        body = f"""
        <p>Hello {first_name},</p>
        <p>The password for your UZYRA account (<strong>{user.email}</strong>) was successfully updated.</p>
        <p>If you made this change, no further action is required.</p>
        <div style="background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.25); border-radius: 12px; padding: 16px; margin: 20px 0; color: #FCA5A5; font-size: 13px;">
            <strong>Important:</strong> If you did NOT initiate this change, your account may be compromised. Please contact support immediately to lock your account.
        </div>
        """
        html = _render_email_template(
            title="Password Changed Successfully",
            subtitle="Account Security Notification",
            body_html=body
        )
        return cls.send_transactional_email(user.email, "Security Alert: UZYRA Password Changed", html, user.display_name)

    # -------------------------------------------------------------------------
    # 5. Card Activation Confirmation
    # -------------------------------------------------------------------------
    @classmethod
    def send_card_activation_notification(cls, user, card):
        first_name = user.first_name or "there"
        body = f"""
        <p>Hello {first_name},</p>
        <p>Your physical NFC Smart Card <strong>{card.card_code}</strong> has been successfully activated and linked to your digital profile.</p>
        <div style="background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 20px; margin: 20px 0;">
            <div style="font-size: 12px; color: #8E95A3; text-transform: uppercase; margin-bottom: 4px;">Hardware Details</div>
            <div style="font-size: 16px; font-weight: 700; color: #FFFFFF; font-family: monospace;">Card ID: {card.card_code}</div>
            <div style="font-size: 13px; color: #BFC5CF; margin-top: 4px;">Status: Active & Routing to Public Profile</div>
        </div>
        <p>Whenever someone taps your physical smart card or scans its QR code, your interactive profile will appear instantly on their smartphone.</p>
        """
        html = _render_email_template(
            title="Smart Card Activated",
            subtitle=f"Hardware {card.card_code} is now live",
            body_html=body,
            cta_text="Manage Card Settings",
            cta_url=getattr(settings, 'SITE_URL', 'https://uzyra.com') + "/dashboard/card/"
        )
        return cls.send_transactional_email(user.email, f"Smart Card {card.card_code} Activated — UZYRA", html, user.display_name)

    # -------------------------------------------------------------------------
    # 6. Order Confirmation
    # -------------------------------------------------------------------------
    @classmethod
    def send_order_confirmation_email(cls, order):
        user = order.user
        first_name = user.first_name or "there"
        body = f"""
        <p>Hello {first_name},</p>
        <p>Thank you for your order! We have received order <strong>#{order.order_number}</strong> for <strong>{order.package.name}</strong>.</p>
        <div style="background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 20px; margin: 20px 0;">
            <div style="font-size: 13px; color: #BFC5CF;"><strong>Order:</strong> #{order.order_number}</div>
            <div style="font-size: 13px; color: #BFC5CF; margin-top: 4px;"><strong>Package:</strong> {order.package.name}</div>
            <div style="font-size: 13px; color: #BFC5CF; margin-top: 4px;"><strong>Total:</strong> &#8358;{order.amount:,.0f}</div>
            <div style="font-size: 13px; color: #BFC5CF; margin-top: 4px;"><strong>Status:</strong> {order.get_order_status_display()}</div>
        </div>
        <p>You can track the progress of your physical card engraving and website design directly in your customer dashboard.</p>
        """
        html = _render_email_template(
            title="Order Received",
            subtitle=f"Order #{order.order_number}",
            body_html=body,
            cta_text="View Order Details",
            cta_url=getattr(settings, 'SITE_URL', 'https://uzyra.com') + f"/dashboard/orders/{order.order_number}/"
        )
        return cls.send_transactional_email(user.email, f"Order Confirmed: #{order.order_number} — UZYRA", html, user.display_name)

    # -------------------------------------------------------------------------
    # 7. Payment Confirmation
    # -------------------------------------------------------------------------
    @classmethod
    def send_payment_confirmation_email(cls, payment):
        order = payment.order
        user = order.user
        first_name = user.first_name or "there"
        body = f"""
        <p>Hello {first_name},</p>
        <p>Your payment of <strong>&#8358;{payment.amount:,.0f}</strong> for order <strong>#{order.order_number}</strong> has been confirmed.</p>
        <div style="background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 20px; margin: 20px 0;">
            <div style="font-size: 13px; color: #BFC5CF;"><strong>Transaction Reference:</strong> {payment.reference}</div>
            <div style="font-size: 13px; color: #BFC5CF; margin-top: 4px;"><strong>Payment Method:</strong> {payment.channel or 'Paystack Secure Checkout'}</div>
            <div style="font-size: 13px; color: #BFC5CF; margin-top: 4px;"><strong>Amount Paid:</strong> &#8358;{payment.amount:,.0f}</div>
        </div>
        <p>Please ensure you have submitted your design specifications and information intake form so our production team can begin work immediately.</p>
        """
        html = _render_email_template(
            title="Payment Confirmed",
            subtitle=f"Receipt for Order #{order.order_number}",
            body_html=body,
            cta_text="Submit Design Information",
            cta_url=getattr(settings, 'SITE_URL', 'https://uzyra.com') + f"/dashboard/orders/{order.order_number}/submit-info/"
        )
        return cls.send_transactional_email(user.email, f"Payment Confirmed for #{order.order_number} — UZYRA", html, user.display_name)

    # -------------------------------------------------------------------------
    # 8. Card Status Change (Lost / Suspended)
    # -------------------------------------------------------------------------
    @classmethod
    def send_card_status_email(cls, user, card, action='suspended'):
        first_name = user.first_name or "there"
        status_label = "Reported Lost" if action == 'lost' else "Suspended"
        body = f"""
        <p>Hello {first_name},</p>
        <p>Your smart card <strong>{card.card_code}</strong> has been marked as <strong>{status_label}</strong>.</p>
        <p>For your security, taps or QR scans of this physical card will no longer route to your public profile. Anyone scanning the card will see a secure inactive notice.</p>
        <p>If you recover the card or need to order a replacement, you can manage your hardware directly from your dashboard.</p>
        """
        html = _render_email_template(
            title=f"Smart Card {status_label}",
            subtitle=f"Hardware {card.card_code}",
            body_html=body,
            cta_text="Manage Cards",
            cta_url=getattr(settings, 'SITE_URL', 'https://uzyra.com') + "/dashboard/card/"
        )
        return cls.send_transactional_email(user.email, f"Security Alert: Card {card.card_code} {status_label}", html, user.display_name)

    # -------------------------------------------------------------------------
    # 9. Security Notification
    # -------------------------------------------------------------------------
    @classmethod
    def send_security_alert_email(cls, user, alert_type: str, details: str):
        first_name = user.first_name or "there"
        body = f"""
        <p>Hello {first_name},</p>
        <p>We detected a security event associated with your UZYRA account:</p>
        <div style="background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.25); border-radius: 12px; padding: 20px; margin: 20px 0; color: #FFFFFF;">
            <div style="font-size: 14px; font-weight: 700; margin-bottom: 6px;">{alert_type}</div>
            <div style="font-size: 13px; color: #D4D4D8;">{details}</div>
        </div>
        <p>If you recognize this activity, no action is needed. If you suspect unauthorized access, please reset your password immediately and contact support.</p>
        """
        html = _render_email_template(
            title="Account Security Alert",
            subtitle="Important notice regarding your UZYRA account",
            body_html=body,
            cta_text="Security Settings",
            cta_url=getattr(settings, 'SITE_URL', 'https://uzyra.com') + "/dashboard/settings/"
        )
        return cls.send_transactional_email(user.email, f"Security Alert: {alert_type} — UZYRA", html, user.display_name)

import json
import hmac
import hashlib
import requests
import uuid
from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import Payment
from apps.orders.models import Order
from apps.core.services.email_service import BrevoEmailService


@login_required
def initialize_payment_view(request, order_number):
    """
    Initialize Paystack Transaction.
    Strictly isolated to authenticated user who owns the order.
    """
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    
    if order.payment_status == Order.PAYMENT_PAID:
        messages.info(request, "This order is already paid.")
        return redirect('dashboard:order_detail', order_number=order.order_number)

    # Generate unique payment reference
    reference = f"ULV-{order.order_number}-{uuid.uuid4().hex[:6].upper()}"
    payment, _ = Payment.objects.get_or_create(
        order=order,
        reference=reference,
        defaults={
            'amount': order.amount,
            'provider': 'paystack',
            'status': Payment.STATUS_PENDING,
        }
    )

    return render(request, 'payments/checkout_gateway.html', {
        'order': order,
        'payment': payment,
        'reference': reference,
        'paystack_public_key': getattr(settings, 'PAYSTACK_PUBLIC_KEY', 'pk_test_sample_key'),
        'test_mode': getattr(settings, 'PAYSTACK_TEST_MODE', True),
    })


@login_required
def verify_payment_view(request):
    """
    Server-Side Authoritative Paystack Payment Verification (/payments/verify/).
    Validates:
    1. User ownership of the underlying order.
    2. Replay attack prevention (cannot re-verify already successful payment).
    3. Authoritative server-to-server query to Paystack API.
    4. Exact currency ('NGN') and price matching (amount in kobo == order.amount * 100).
    5. Brevo payment receipt dispatch.
    """
    reference = request.GET.get('reference') or request.GET.get('trxref') or request.POST.get('reference')
    if not reference:
        messages.error(request, "No payment reference provided for verification.")
        return redirect('dashboard:orders_list')

    payment = get_object_or_404(Payment, reference=reference)
    order = payment.order

    # IDOR check: Verify caller owns this order
    if order.user != request.user:
        messages.error(request, "Access denied. You do not own this order.")
        return redirect('dashboard:orders_list')

    # Replay defense: If already successfully confirmed, do not re-process
    if payment.status == Payment.STATUS_SUCCESS and order.payment_status == Order.PAYMENT_PAID:
        messages.info(request, "This payment has already been verified and processed.")
        return redirect('dashboard:order_detail', order_number=order.order_number)

    # Check if this is test mode simulator action
    is_test_sim = request.GET.get('simulated') == 'true' or request.POST.get('simulated') == 'true'

    if is_test_sim and getattr(settings, 'PAYSTACK_TEST_MODE', True):
        # Successful verified test simulation
        payment.status = Payment.STATUS_SUCCESS
        payment.paid_at = timezone.now()
        payment.gateway_response = "Successful (Simulated Sandbox)"
        payment.save()

        order.payment_status = Order.PAYMENT_PAID
        order.order_status = Order.STATUS_PAID
        order.save()

        # Dispatch confirmation email via Brevo
        try:
            BrevoEmailService.send_payment_confirmation_email(payment)
        except Exception as e:
            import logging
            logging.getLogger('uzyra.payments').error(f"Failed to dispatch payment confirmation email: {e}")

        messages.success(request, f"Payment of ₦{order.amount:,.0f} verified successfully!")
        return redirect('dashboard:order_submit_info', order_number=order.order_number)

    # Live / Authoritative Paystack API Verification
    secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {"Authorization": f"Bearer {secret_key}"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()

        if data.get('status') and data.get('data', {}).get('status') == 'success':
            paystack_data = data['data']
            actual_amount_kobo = paystack_data.get('amount')
            actual_currency = paystack_data.get('currency', '').upper()
            expected_amount_kobo = order.amount * 100

            # Strict Price & Currency Verification
            if actual_amount_kobo != expected_amount_kobo or actual_currency != 'NGN':
                payment.status = Payment.STATUS_FAILED
                payment.gateway_response = f"Amount mismatch: Expected {expected_amount_kobo} kobo NGN, got {actual_amount_kobo} kobo {actual_currency}"
                payment.raw_response = data
                payment.save()

                messages.error(request, "Payment verification failed: Amount or currency mismatch detected.")
                return redirect('dashboard:order_detail', order_number=order.order_number)

            payment.status = Payment.STATUS_SUCCESS
            payment.paid_at = timezone.now()
            payment.channel = paystack_data.get('channel', '')
            payment.currency = actual_currency
            payment.gateway_response = paystack_data.get('gateway_response', 'Successful')
            payment.raw_response = data
            payment.save()

            order.payment_status = Order.PAYMENT_PAID
            order.order_status = Order.STATUS_PAID
            order.save()

            # Dispatch confirmation email via Brevo
            try:
                BrevoEmailService.send_payment_confirmation_email(payment)
            except Exception as e:
                import logging
                logging.getLogger('uzyra.payments').error(f"Failed to dispatch payment email: {e}")

            messages.success(request, f"Payment of ₦{order.amount:,.0f} confirmed! Please complete your design requirements.")
            return redirect('dashboard:order_submit_info', order_number=order.order_number)
        else:
            payment.status = Payment.STATUS_FAILED
            payment.gateway_response = data.get('message', 'Payment failed')
            payment.save()
            messages.error(request, "Payment verification failed or was declined.")
            return redirect('dashboard:order_detail', order_number=order.order_number)
            
    except Exception as e:
        messages.error(request, f"Could not verify transaction: {str(e)}")
        return redirect('dashboard:order_detail', order_number=order.order_number)


@csrf_exempt
@require_POST
def paystack_webhook_view(request):
    """
    Secure Paystack Webhook Handler.
    Verifies HMAC SHA512 signature against PAYSTACK_SECRET_KEY.
    Ensures idempotent execution and amount validation.
    """
    secret = getattr(settings, 'PAYSTACK_SECRET_KEY', '').encode('utf-8')
    paystack_signature = request.META.get('HTTP_X_PAYSTACK_SIGNATURE')

    if not paystack_signature:
        return HttpResponse("Missing signature", status=400)

    # Verify signature in constant time
    computed_signature = hmac.new(secret, request.body, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(computed_signature, paystack_signature):
        return HttpResponse("Invalid signature", status=400)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return HttpResponse("Invalid JSON payload", status=400)

    event = payload.get('event')

    if event == 'charge.success':
        data = payload.get('data', {})
        reference = data.get('reference')
        if reference:
            try:
                payment = Payment.objects.get(reference=reference)
                
                # Idempotency check: Ignore duplicate webhook delivery
                if payment.status == Payment.STATUS_SUCCESS:
                    return HttpResponse("Event already processed", status=200)

                expected_kobo = payment.order.amount * 100
                webhook_kobo = data.get('amount')
                currency = data.get('currency', '').upper()

                if webhook_kobo == expected_kobo and currency == 'NGN':
                    payment.status = Payment.STATUS_SUCCESS
                    payment.paid_at = timezone.now()
                    payment.currency = currency
                    payment.channel = data.get('channel', '')
                    payment.gateway_response = data.get('gateway_response', 'Successful')
                    payment.raw_response = payload
                    payment.save()

                    order = payment.order
                    order.payment_status = Order.PAYMENT_PAID
                    order.order_status = Order.STATUS_PAID
                    order.save()

                    # Dispatch Brevo receipt
                    try:
                        BrevoEmailService.send_payment_confirmation_email(payment)
                    except Exception as e:
                        import logging
                        logging.getLogger('uzyra.payments').error(f"Webhook payment email failed: {e}")
                else:
                    payment.status = Payment.STATUS_FAILED
                    payment.gateway_response = f"Webhook amount mismatch: got {webhook_kobo} {currency}, expected {expected_kobo} NGN"
                    payment.raw_response = payload
                    payment.save()

            except Payment.DoesNotExist:
                pass

    return HttpResponse(status=200)


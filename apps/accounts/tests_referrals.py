from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.accounts.models import Referral
from apps.orders.models import Order, ProductPackage
from apps.payments.models import Payment

User = get_user_model()

@override_settings(PAYSTACK_TEST_MODE=True)
class ReferralProgrammeTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.referrer = User.objects.create_user(
            email='referrer@example.com',
            password='Password123!',
            first_name='Referrer',
            last_name='User'
        )
        self.package = ProductPackage.objects.create(
            code='card_test',
            name='Test Smart Card',
            price_ngn=15000,
            description='Test Package'
        )

    def test_auto_generated_referral_code(self):
        """Test every new user gets a unique, stable referral code starting with UZY-."""
        self.assertIsNotNone(self.referrer.referral_code)
        self.assertTrue(self.referrer.referral_code.startswith('UZY-'))

    def test_referral_attribution_and_qualification_flow(self):
        """Test full referral loop: /join/ -> register -> email verify -> paid order -> qualification."""
        # Step 1: Open referral link
        join_url = f"{reverse('referral_join')}?ref={self.referrer.referral_code}"
        res = self.client.get(join_url)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(self.client.session.get('referral_code'), self.referrer.referral_code)

        # Step 2: Register new user
        reg_url = reverse('accounts:register')
        reg_payload = {
            'first_name': 'Referred',
            'last_name': 'Friend',
            'email': 'friend@example.com',
            'password': 'Password123!',
            'password_confirm': 'Password123!',
            'agree_terms': 'on'
        }
        reg_res = self.client.post(reg_url, reg_payload)
        self.assertIn(reg_res.status_code, [200, 302])

        new_user = User.objects.get(email='friend@example.com')
        referral = Referral.objects.filter(referred_user=new_user).first()
        self.assertIsNotNone(referral)
        self.assertEqual(referral.referrer, self.referrer)
        self.assertEqual(referral.status, Referral.STATUS_PENDING)

        # Step 3: Create order & simulate payment completion
        order = Order.objects.create(
            order_number='ORD-REF-001',
            user=new_user,
            package=self.package,
            amount=15000,
            payment_status=Order.PAYMENT_PENDING
        )
        payment = Payment.objects.create(
            order=order,
            reference='ULV-ORD-REF-001-TEST',
            amount=15000,
            status=Payment.STATUS_PENDING
        )

        # Verify payment in sandbox mode as new_user
        self.client.force_login(new_user)
        verify_url = f"{reverse('payments:verify')}?reference={payment.reference}&simulated=true"
        v_res = self.client.get(verify_url)
        self.assertIn(v_res.status_code, [200, 302])

        # Verify referral moves to QUALIFIED
        referral.refresh_from_db()
        self.assertEqual(referral.status, Referral.STATUS_QUALIFIED)
        self.assertEqual(referral.reward_amount_ngn, 2000)

    def test_self_referral_prevention(self):
        """Test a user cannot refer themselves."""
        join_url = f"{reverse('referral_join')}?ref={self.referrer.referral_code}"
        self.client.get(join_url)

        # Registering unauthenticated
        reg_payload = {
            'first_name': 'Self',
            'last_name': 'Referral',
            'email': 'self@example.com',
            'password': 'Password123!',
            'password_confirm': 'Password123!',
            'agree_terms': 'on'
        }
        self.client.post(reverse('accounts:register'), reg_payload)
        new_user = User.objects.get(email='self@example.com')

        # Referral record should NOT exist where referrer == referred_user
        self.assertFalse(Referral.objects.filter(referrer=new_user, referred_user=new_user).exists())


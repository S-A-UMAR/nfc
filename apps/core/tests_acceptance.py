"""
STRIDE Comprehensive Product Acceptance Tests
==============================================
Validates complete multi-application customer workflows across the entire platform:
  Journey A: Register → Verify OTP → Onboarding → Profile Edit → Purchase Card →
             Payment Confirm → Card Assign/Reserve → Card Activation → NFC Tap → Public Profile.
  Journey B: Update Profile & Appearance → NFC Tap → Public Profile reflects changes.
  Journey C: Report Lost Card → Routing Blocked (Lost Page) → Support Replaces Card →
             New Card Active & Old Card forwards to replacement.
  Journey D: 10 Referrals → 1 Paid & Activated → Admin Approve & Make Available →
             Customer Claims → Staff Fulfills.
  Journey E: Submit Formal Complaint/Support Request → Admin Review & Resolution.
"""
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

from apps.accounts.models import Referral, ReferralReward, OTPCode
from apps.profiles.models import Profile, SocialLink
from apps.cards.models import Card, CardEvent
from apps.orders.models import Order, ProductPackage
from apps.payments.models import Payment
from apps.core.models import ContactMessage, AdminAuditLog

User = get_user_model()


@override_settings(
    PAYSTACK_TEST_MODE=True,
    PAYSTACK_ALLOW_SIMULATION_IN_TESTS=True,
    SITE_URL='http://testserver',
)
class ComprehensiveProductAcceptanceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.package = ProductPackage.objects.create(
            code='smart-card-acc',
            name='Smart NFC Card',
            package_type=ProductPackage.TYPE_CARD,
            price_ngn=25000,
            description='Test package',
            features='Feature 1\nFeature 2',
            is_active=True,
        )
        self.staff_user = User.objects.create_superuser(
            email='admin@stride.ng',
            password='Password123!',
            first_name='Admin',
            last_name='Staff',
        )

    # ─────────────────────────────────────────────────────────────────────────
    # JOURNEY A: Full Onboarding, Purchase, Activation, and Public NFC Tap
    # ─────────────────────────────────────────────────────────────────────────
    def test_journey_a_complete_customer_lifecycle(self):
        """
        New customer registers → verifies OTP → completes onboarding →
        updates profile → orders card → verifies payment → staff assigns card →
        customer activates physical card with PIN → NFC tap loads public profile.
        """
        # 1. Registration
        reg_payload = {
            'first_name': 'Kola',
            'last_name': 'Adeleke',
            'email': 'kola@example.com',
            'password': 'Password123!',
            'password_confirm': 'Password123!',
            'agree_terms': 'on',
        }
        res_reg = self.client.post(reverse('accounts:register'), reg_payload)
        self.assertIn(res_reg.status_code, [200, 302])

        user = User.objects.get(email='kola@example.com')
        self.assertFalse(user.is_email_verified)

        # 2. Verify OTP
        otp_record, plain_otp = OTPCode.generate_otp(
            user=user,
            email=user.email,
            purpose=OTPCode.PURPOSE_EMAIL_VERIFICATION,
        )
        session = self.client.session
        session['pending_verification_email'] = user.email
        session.save()

        res_otp = self.client.post(reverse('accounts:verify_otp'), {'otp_code': plain_otp})
        self.assertIn(res_otp.status_code, [200, 302])
        user.refresh_from_db()
        self.assertTrue(user.is_email_verified)

        # Log in customer
        self.client.force_login(user)

        # 3. Complete Onboarding
        onboard_payload = {
            'profile_type': 'personal',
            'full_name': 'Kola Adeleke',
            'title': 'Creative Director',
            'bio': 'Designing tactile experiences in Lagos.',
            'phone': '+2348011223344',
            'whatsapp': '+2348011223344',
            'email': 'kola@example.com',
            'location': 'Lagos, Nigeria',
            'website_url': 'https://kola.design',
        }
        res_onboard = self.client.post(reverse('dashboard:onboarding'), onboard_payload)
        self.assertRedirects(res_onboard, reverse('dashboard:overview'), fetch_redirect_response=False)

        profile = user.profile
        profile.refresh_from_db()
        self.assertEqual(profile.title, 'Creative Director')
        self.assertTrue(bool(profile.slug))

        # 4. Checkout Card Package
        checkout_payload = {
            'shipping_name': 'Kola Adeleke',
            'shipping_phone': '+2348011223344',
            'shipping_address': '12 Victoria Island Blvd, Lagos',
            'shipping_city': 'Lagos',
            'shipping_state': 'Lagos State',
        }
        res_checkout = self.client.post(
            reverse('orders:checkout', kwargs={'package_code': self.package.code}),
            checkout_payload,
        )
        order = Order.objects.filter(user=user).latest('id')
        self.assertEqual(order.amount, 25000)
        self.assertEqual(order.payment_status, Order.PAYMENT_PENDING)
        self.assertRedirects(res_checkout, reverse('payments:initialize', kwargs={'order_number': order.order_number}), fetch_redirect_response=False)

        # 5. Initialize Payment & Verify via Paystack Sandbox
        res_init = self.client.get(reverse('payments:initialize', kwargs={'order_number': order.order_number}))
        self.assertEqual(res_init.status_code, 200)

        payment = Payment.objects.get(order=order)
        verify_url = f"{reverse('payments:verify')}?reference={payment.reference}&simulated=true"
        res_verify = self.client.get(verify_url)
        self.assertIn(res_verify.status_code, [200, 302])

        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PAYMENT_PAID)

        # 6. Staff assigns physical card to order in operations
        card = Card(card_code='ST-ACC-000001', status=Card.STATUS_UNASSIGNED)
        plain_pin = card.generate_activation_code()
        card.save()

        self.client.force_login(self.staff_user)
        res_assign = self.client.post(
            reverse('operations:order_update_status', kwargs={'order_number': order.order_number}),
            {
                'order_status': Order.STATUS_PRODUCTION,
                'assign_card_id': card.id,
            }
        )
        self.assertRedirects(res_assign, reverse('operations:order_detail', kwargs={'order_number': order.order_number}), fetch_redirect_response=False)
        order.refresh_from_db()
        self.assertEqual(order.card_assigned, card)
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_RESERVED)
        self.assertEqual(card.user, user)

        # 7. Customer receives card and activates with security PIN
        self.client.force_login(user)
        act_payload = {
            'card_code': card.card_code,
            'activation_code': plain_pin,
        }
        res_act = self.client.post(reverse('cards:card_activate'), act_payload)
        self.assertRedirects(res_act, reverse('dashboard:card_manage'), fetch_redirect_response=False)

        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_ACTIVE)
        self.assertEqual(card.user, user)
        self.assertEqual(card.profile, profile)
        self.assertIsNotNone(card.activated_at)

        # 8. External visitor taps physical NFC card (/c/ST-ACC-000001/)
        visitor_client = Client()
        res_tap = visitor_client.get(f'/c/{card.card_code}/')
        expected_profile_url = reverse('profiles:public_profile', kwargs={'slug': profile.slug})
        self.assertRedirects(res_tap, expected_profile_url, fetch_redirect_response=False)

        # 9. Public profile page renders successfully with customer details
        res_profile = visitor_client.get(expected_profile_url)
        self.assertEqual(res_profile.status_code, 200)
        self.assertContains(res_profile, 'Kola Adeleke')
        self.assertContains(res_profile, 'Creative Director')

    # ─────────────────────────────────────────────────────────────────────────
    # JOURNEY B: Profile Updates & Appearance Changes Reflected on Public NFC
    # ─────────────────────────────────────────────────────────────────────────
    def test_journey_b_appearance_updates_reflected_on_nfc_tap(self):
        """
        Customer updates title and switches appearance theme.
        NFC scan routes to profile displaying the updated information and theme.
        """
        user = User.objects.create_user(
            email='maya@example.com', password='Password123!',
            first_name='Maya', last_name='Design', is_email_verified=True,
        )
        profile, _ = Profile.objects.get_or_create(
            user=user, defaults={'full_name': 'Maya Design', 'email': user.email, 'title': 'Junior Designer'}
        )
        card = Card.objects.create(
            card_code='ST-MAYA-01', user=user, profile=profile, status=Card.STATUS_ACTIVE,
            activated_at=timezone.now()
        )

        self.client.force_login(user)

        # 1. Update personal details
        edit_payload = {
            'full_name': 'Maya Design, Lead',
            'title': 'Head of Product Design',
            'bio': 'Leading UX at scale.',
            'phone': '+2348099887766',
            'whatsapp': '+2348099887766',
            'email': 'maya@example.com',
            'location': 'Abuja, Nigeria',
            'website_url': 'https://maya.ux',
            'slug': profile.slug,
        }
        res_edit = self.client.post(reverse('dashboard:profile_edit'), edit_payload)
        self.assertRedirects(res_edit, reverse('dashboard:profile_edit'), fetch_redirect_response=False)

        # 2. Update appearance to 'midnight'
        app_payload = {
            'profile_type': 'personal',
            'theme': 'midnight',
            'profile_layout': 'modern_split',
        }
        res_app = self.client.post(reverse('dashboard:appearance'), app_payload)
        self.assertRedirects(res_app, reverse('dashboard:appearance'), fetch_redirect_response=False)

        profile.refresh_from_db()
        self.assertEqual(profile.title, 'Head of Product Design')
        self.assertEqual(profile.theme, 'midnight')

        # 3. External visitor taps card
        visitor = Client()
        res_tap = visitor.get(f'/c/{card.card_code}/')
        profile_url = reverse('profiles:public_profile', kwargs={'slug': profile.slug})
        self.assertRedirects(res_tap, profile_url, fetch_redirect_response=False)

        res_view = visitor.get(profile_url)
        self.assertEqual(res_view.status_code, 200)
        self.assertContains(res_view, 'Head of Product Design')
        self.assertContains(res_view, 'data-theme="midnight"')

    # ─────────────────────────────────────────────────────────────────────────
    # JOURNEY C: Lost Card Reporting, Routing Block, and Staff Replacement
    # ─────────────────────────────────────────────────────────────────────────
    def test_journey_c_lost_card_and_replacement_workflow(self):
        """
        Customer reports card lost → NFC tap shows card lost page →
        staff issues replacement card → new card is active →
        old card redirects to replacement.
        """
        user = User.objects.create_user(
            email='tunde@example.com', password='Password123!',
            first_name='Tunde', last_name='Bakare', is_email_verified=True,
        )
        profile, _ = Profile.objects.get_or_create(
            user=user, defaults={'full_name': 'Tunde Bakare', 'email': user.email}
        )
        old_card = Card.objects.create(
            card_code='ST-TUNDE-LOST', user=user, profile=profile,
            status=Card.STATUS_ACTIVE, activated_at=timezone.now()
        )

        # 1. Customer reports card lost
        self.client.force_login(user)
        res_lost = self.client.post(reverse('cards:card_report_lost', kwargs={'card_id': old_card.id}))
        self.assertRedirects(res_lost, reverse('dashboard:card_manage'), fetch_redirect_response=False)

        old_card.refresh_from_db()
        self.assertEqual(old_card.status, Card.STATUS_LOST)

        # 2. External NFC tap on lost card renders lost page (blocked!)
        visitor = Client()
        res_tap_lost = visitor.get(f'/c/{old_card.card_code}/')
        self.assertEqual(res_tap_lost.status_code, 200)
        self.assertTemplateUsed(res_tap_lost, 'cards/card_lost.html')

        # 3. Staff in operations issues replacement card
        new_card = Card.objects.create(card_code='ST-TUNDE-NEW', status=Card.STATUS_UNASSIGNED)
        new_card.generate_activation_code()
        new_card.save()

        self.client.force_login(self.staff_user)
        res_replace = self.client.post(
            reverse('operations:card_replace', kwargs={'card_id': old_card.id}),
            {'replacement_card_id': new_card.id}
        )
        self.assertRedirects(res_replace, reverse('operations:card_detail', kwargs={'card_id': new_card.id}), fetch_redirect_response=False)

        old_card.refresh_from_db()
        new_card.refresh_from_db()
        self.assertEqual(old_card.status, Card.STATUS_REPLACED)
        self.assertEqual(old_card.replacement_for, new_card)
        self.assertEqual(new_card.status, Card.STATUS_ACTIVE)
        self.assertEqual(new_card.user, user)
        self.assertEqual(new_card.profile, profile)

        # 4. Old card tap forwards to replacement card
        res_old_tap = visitor.get(f'/c/{old_card.card_code}/')
        self.assertRedirects(res_old_tap, f'/c/{new_card.card_code}/', fetch_redirect_response=False)

        # 5. New card tap routes to customer's public profile
        res_new_tap = visitor.get(f'/c/{new_card.card_code}/')
        self.assertRedirects(res_new_tap, reverse('profiles:public_profile', kwargs={'slug': profile.slug}), fetch_redirect_response=False)

    # ─────────────────────────────────────────────────────────────────────────
    # JOURNEY D: Referrals, Qualification, Claim, and Fulfilment
    # ─────────────────────────────────────────────────────────────────────────
    def test_journey_d_referral_rewards_full_lifecycle(self):
        """
        10 referrals made & verified → 1 card purchase & activation →
        reward created in pending_review → admin approves & makes available →
        customer claims reward with delivery address → staff fulfills.
        """
        referrer = User.objects.create_user(
            email='influencer@example.com', password='Password123!',
            first_name='Top', last_name='Referrer', is_email_verified=True,
        )

        from apps.accounts.services import referral_service

        # Create 9 verified referrals
        for i in range(9):
            friend = User.objects.create_user(
                email=f'friend_{i}@example.com', password='Password123!',
                first_name='Friend', last_name=str(i), is_email_verified=True,
            )
            Referral.objects.create(
                referrer=referrer, referred_user=friend, code_used=referrer.referral_code,
                status=Referral.STATUS_VERIFIED
            )

        # 10th friend: purchases and activates card
        friend_10 = User.objects.create_user(
            email='friend_buyer@example.com', password='Password123!',
            first_name='Buyer', last_name='Ten', is_email_verified=True,
        )
        ref_10 = Referral.objects.create(
            referrer=referrer, referred_user=friend_10, code_used=referrer.referral_code,
            status=Referral.STATUS_VERIFIED
        )
        order = Order.objects.create(
            order_number='ORD-REF-BUY', user=friend_10, package=self.package,
            amount=25000, payment_status=Order.PAYMENT_PAID
        )
        referral_service.process_referral_qualification(order)

        card_10 = Card.objects.create(card_code='ST-REF-CARD', user=friend_10, status=Card.STATUS_ACTIVE, activated_at=timezone.now())
        reward = referral_service.record_card_activation(card_10)

        # 1. Reward created in STATUS_PENDING_REVIEW
        self.assertIsNotNone(reward)
        self.assertEqual(reward.status, ReferralReward.STATUS_PENDING_REVIEW)

        # 2. Admin approves and makes available
        from apps.accounts.admin import ReferralRewardAdmin
        from django.contrib.admin.sites import AdminSite
        from unittest.mock import MagicMock

        site = AdminSite()
        reward_admin = ReferralRewardAdmin(ReferralReward, site)
        req = MagicMock()
        req.user = self.staff_user

        reward_admin.approve_reward(req, ReferralReward.objects.filter(id=reward.id))
        reward.refresh_from_db()
        self.assertEqual(reward.status, ReferralReward.STATUS_APPROVED)

        reward_admin.make_available(req, ReferralReward.objects.filter(id=reward.id))
        reward.refresh_from_db()
        self.assertEqual(reward.status, ReferralReward.STATUS_AVAILABLE)

        # 3. Customer claims reward with delivery details
        self.client.force_login(referrer)
        claim_payload = {
            'delivery_name': 'Top Referrer',
            'delivery_phone': '+2348055667788',
            'delivery_address': 'Plot 4, Lekki Expressway',
            'delivery_city': 'Lagos',
            'delivery_state': 'Lagos State',
        }
        res_claim = self.client.post(reverse('dashboard:referrals_claim'), claim_payload)
        self.assertRedirects(res_claim, reverse('dashboard:referrals'), fetch_redirect_response=False)

        reward.refresh_from_db()
        self.assertEqual(reward.status, ReferralReward.STATUS_CLAIMED)
        self.assertEqual(reward.delivery_name, 'Top Referrer')

        # 4. Staff fulfills reward
        reward_admin.mark_fulfilled(req, ReferralReward.objects.filter(id=reward.id))
        reward.refresh_from_db()
        self.assertEqual(reward.status, ReferralReward.STATUS_FULFILLED)

    # ─────────────────────────────────────────────────────────────────────────
    # JOURNEY E: Customer Complaint Submission and Resolution
    # ─────────────────────────────────────────────────────────────────────────
    def test_journey_e_complaint_intake_and_staff_resolution(self):
        """
        Customer submits a formal complaint/inquiry → ContactMessage record is created →
        staff reviews and records resolution.
        """
        complaint_payload = {
            'full_name': 'Amara Okon',
            'email': 'amara@example.com',
            'phone': '+2348033445566',
            'subject': '[NFC Hardware] Defective Chip / Delivery Issue',
            'message': 'My smart card chip is unreadable on iPhone 15 Pro. Please assist.',
        }
        res_post = self.client.post(reverse('legal:complaints'), complaint_payload, follow=True)
        self.assertEqual(res_post.status_code, 200)
        self.assertContains(res_post, 'Your inquiry / formal complaint has been received')

        msg = ContactMessage.objects.filter(email='amara@example.com').latest('id')
        self.assertEqual(msg.subject, '[NFC Hardware] Defective Chip / Delivery Issue')
        self.assertFalse(msg.is_resolved)

        # Staff marks resolved
        msg.is_resolved = True
        msg.save()

        msg.refresh_from_db()
        self.assertTrue(msg.is_resolved)

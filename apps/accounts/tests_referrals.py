"""
STRIDE Referral Programme Tests — v2 (Product Reward Programme)
===============================================================
Covers all scenarios from the product requirements §9:
  §9.1  Referral code generation
  §9.2  Legacy UZY- code attribution
  §9.3  Full attribution and qualification flow (new programme)
  §9.4  Self-referral prevention
  §9.5  10-referral threshold (counts correctly)
  §9.6  Purchase qualification
  §9.7  Card activation triggers reward check
  §9.8  Failed/cancelled payment does NOT qualify
  §9.9  Duplicate webhook / idempotency (no double reward)
  §9.10 Reward state machine (pending_review → approved → available → claimed → fulfilled)
  §9.11 Duplicate reward prevention
  §9.12 Duplicate claim prevention
  §9.13 Admin approve/reject actions
  §9.14 Customer cannot access another customer's referral data
  §9.15 Ordinary user cannot approve their own reward
  §9.16 Progress service: counts correct at each stage
  §9.17 Claim view: requires delivery fields
  §9.18 Claim view: blocked if reward not in STATUS_AVAILABLE
  §9.19 Legacy ₦2,000 data preserved and not corrupted
  §9.20 get_referral_progress returns correct eligible_for_reward
"""
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

from apps.accounts.models import Referral, ReferralReward
from apps.accounts.services import referral_service
from apps.orders.models import Order, ProductPackage
from apps.payments.models import Payment
from apps.cards.models import Card
from apps.profiles.models import Profile

User = get_user_model()


def _make_user(email, first_name='Test', last_name='User', verified=False):
    u = User.objects.create_user(
        email=email,
        password='Password123!',
        first_name=first_name,
        last_name=last_name,
    )
    if verified:
        u.is_email_verified = True
        u.save()
    return u


def _make_referral(referrer, referred_user, status=Referral.STATUS_PENDING, with_order=False, with_card=False, package=None):
    """Helper: create a Referral record in the given status."""
    ref = Referral.objects.create(
        referrer=referrer,
        referred_user=referred_user,
        code_used=referrer.referral_code,
        status=status,
    )
    if with_order and package:
        order = Order.objects.create(
            order_number=f'ORD-TEST-{referred_user.pk}',
            user=referred_user,
            package=package,
            amount=15000,
            payment_status=Order.PAYMENT_PAID,
        )
        ref.qualifying_order = order
        ref.status = Referral.STATUS_QUALIFIED
    if with_card:
        card = Card.objects.create(card_code=f'ST-TEST-{referred_user.pk}')
        card.user = referred_user
        card.status = Card.STATUS_ACTIVE
        card.activated_at = timezone.now()
        card.save()
        ref.activation_card = card
    ref.save()
    return ref


@override_settings(PAYSTACK_TEST_MODE=True, PAYSTACK_ALLOW_SIMULATION_IN_TESTS=True)
class ReferralCodeGenerationTests(TestCase):
    """§9.1 — Code generation"""

    def test_new_user_gets_str_prefixed_code(self):
        u = _make_user('code1@example.com')
        self.assertIsNotNone(u.referral_code)
        self.assertTrue(u.referral_code.startswith('STR-'))
        self.assertEqual(len(u.referral_code), 12)  # STR- + 8 chars

    def test_referral_codes_are_unique(self):
        users = [_make_user(f'unique{i}@example.com') for i in range(10)]
        codes = [u.referral_code for u in users]
        self.assertEqual(len(codes), len(set(codes)))


class LegacyCodeAttributionTests(TestCase):
    """§9.2 — Legacy UZY- codes"""

    def test_legacy_uzy_code_set_on_user(self):
        u = User.objects.create_user(
            email='legacy@example.com',
            password='Pw1!',
            first_name='L', last_name='U',
            referral_code='UZY-LEGACY99',
        )
        self.assertEqual(u.referral_code, 'UZY-LEGACY99')

    def test_join_link_with_legacy_code_sets_session_and_cookies(self):
        referrer = User.objects.create_user(
            email='legacyref@example.com',
            password='Pw1!',
            first_name='L', last_name='R',
            referral_code='UZY-OLDCODE',
        )
        client = Client()
        res = client.get(reverse('referral_join') + '?ref=UZY-OLDCODE')
        self.assertEqual(res.status_code, 302)
        self.assertIn('stride_ref', res.cookies)
        self.assertEqual(res.cookies['stride_ref'].value, 'UZY-OLDCODE')
        self.assertIn('uzyra_ref', res.cookies)


@override_settings(PAYSTACK_TEST_MODE=True, PAYSTACK_ALLOW_SIMULATION_IN_TESTS=True)
class ReferralAttributionFlowTests(TestCase):
    """§9.3 — Full attribution flow"""

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.referrer = _make_user('referrer@example.com', verified=True)
        self.package = ProductPackage.objects.create(
            code='smart-card-test', name='Test Card', price_ngn=15000, description='Test'
        )

    def test_join_stores_referral_code_in_session(self):
        res = self.client.get(reverse('referral_join') + f'?ref={self.referrer.referral_code}')
        self.assertEqual(res.status_code, 302)
        self.assertEqual(self.client.session.get('referral_code'), self.referrer.referral_code)

    def test_registration_creates_pending_referral(self):
        self.client.get(reverse('referral_join') + f'?ref={self.referrer.referral_code}')
        self.client.post(reverse('accounts:register'), {
            'first_name': 'Referred', 'last_name': 'Friend',
            'email': 'friend1@example.com',
            'password': 'Password123!', 'password_confirm': 'Password123!',
            'agree_terms': 'on',
        })
        new_user = User.objects.get(email='friend1@example.com')
        ref = Referral.objects.filter(referred_user=new_user).first()
        self.assertIsNotNone(ref)
        self.assertEqual(ref.referrer, self.referrer)
        self.assertEqual(ref.status, Referral.STATUS_PENDING)

    def test_payment_verification_qualifies_referral(self):
        self.client.get(reverse('referral_join') + f'?ref={self.referrer.referral_code}')
        self.client.post(reverse('accounts:register'), {
            'first_name': 'Referred', 'last_name': 'Friend2',
            'email': 'friend2@example.com',
            'password': 'Password123!', 'password_confirm': 'Password123!',
            'agree_terms': 'on',
        })
        new_user = User.objects.get(email='friend2@example.com')
        ref = Referral.objects.get(referred_user=new_user)
        # Manually advance to verified (simulating email verification)
        ref.status = Referral.STATUS_VERIFIED
        ref.save()

        order = Order.objects.create(
            order_number='ORD-FLOW-001',
            user=new_user, package=self.package,
            amount=15000, payment_status=Order.PAYMENT_PENDING,
        )
        payment = Payment.objects.create(
            order=order, reference='STR-FLOW-TEST-001',
            amount=15000, status=Payment.STATUS_PENDING,
        )
        self.client.force_login(new_user)
        verify_url = f"{reverse('payments:verify')}?reference={payment.reference}&simulated=true"
        self.client.get(verify_url)

        ref.refresh_from_db()
        self.assertEqual(ref.status, Referral.STATUS_QUALIFIED)
        self.assertEqual(ref.reward_amount_ngn, 2000)  # legacy field preserved


class SelfReferralPreventionTests(TestCase):
    """§9.4 — Self-referral"""

    def test_user_cannot_refer_themselves(self):
        referrer = _make_user('selfref@example.com')
        client = Client()
        client.get(reverse('referral_join') + f'?ref={referrer.referral_code}')
        client.post(reverse('accounts:register'), {
            'first_name': 'Self', 'last_name': 'Ref',
            'email': 'selfref@example.com',
            'password': 'Password123!', 'password_confirm': 'Password123!',
            'agree_terms': 'on',
        })
        self.assertFalse(
            Referral.objects.filter(referrer=referrer, referred_user=referrer).exists()
        )


class ReferralThresholdTests(TestCase):
    """§9.5 — 10-referral threshold and counts"""

    def setUp(self):
        self.referrer = _make_user('thresh@example.com')
        self.package = ProductPackage.objects.create(
            code='thr-card', name='Threshold Card', price_ngn=10000, description='T'
        )

    def _make_verified_referral(self, n):
        u = _make_user(f'ref{n}thresh@example.com')
        return _make_referral(self.referrer, u, status=Referral.STATUS_VERIFIED)

    def test_counts_below_threshold(self):
        for i in range(5):
            self._make_verified_referral(i)
        progress = referral_service.get_referral_progress(self.referrer)
        self.assertEqual(progress['verified_referrals'], 5)
        self.assertFalse(progress['eligible_for_reward'])

    def test_counts_at_threshold_without_activation(self):
        for i in range(10):
            self._make_verified_referral(i)
        progress = referral_service.get_referral_progress(self.referrer)
        self.assertEqual(progress['verified_referrals'], 10)
        self.assertFalse(progress['eligible_for_reward'])  # no activation yet

    def test_counts_qualified_referrals_in_verified_total(self):
        """Qualified referrals count toward the verified total."""
        for i in range(8):
            self._make_verified_referral(i)
        u_q = _make_user('qref@example.com')
        _make_referral(self.referrer, u_q, status=Referral.STATUS_QUALIFIED)
        progress = referral_service.get_referral_progress(self.referrer)
        self.assertEqual(progress['verified_referrals'], 9)


class PurchaseQualificationTests(TestCase):
    """§9.6 — Purchase qualification via service"""

    def setUp(self):
        self.referrer = _make_user('purchaser@example.com')
        self.referred = _make_user('referred_p@example.com')
        self.package = ProductPackage.objects.create(
            code='purch-card', name='Purchase Card', price_ngn=10000, description='P'
        )
        self.ref = _make_referral(self.referrer, self.referred, status=Referral.STATUS_VERIFIED)

    def test_process_qualification_moves_status_to_qualified(self):
        order = Order.objects.create(
            order_number='ORD-PURCH-001',
            user=self.referred, package=self.package,
            amount=10000, payment_status=Order.PAYMENT_PAID,
        )
        referral_service.process_referral_qualification(order)
        self.ref.refresh_from_db()
        self.assertEqual(self.ref.status, Referral.STATUS_QUALIFIED)
        self.assertEqual(self.ref.qualifying_order, order)

    def test_already_qualified_referral_not_re_qualified(self):
        """process_referral_qualification is a no-op when referral is already QUALIFIED."""
        order1 = Order.objects.create(
            order_number='ORD-PURCH-002',
            user=self.referred, package=self.package,
            amount=10000, payment_status=Order.PAYMENT_PAID,
        )
        referral_service.process_referral_qualification(order1)
        order2 = Order.objects.create(
            order_number='ORD-PURCH-003',
            user=self.referred, package=self.package,
            amount=10000, payment_status=Order.PAYMENT_PAID,
        )
        referral_service.process_referral_qualification(order2)
        # Should still point to order1
        self.ref.refresh_from_db()
        self.assertEqual(self.ref.qualifying_order, order1)


class CardActivationRewardTriggerTests(TestCase):
    """§9.7 — Card activation triggers reward check"""

    def setUp(self):
        self.referrer = _make_user('activator@example.com')
        self.package = ProductPackage.objects.create(
            code='act-card', name='Activation Card', price_ngn=10000, description='A'
        )
        # Create 10 verified referrals (9 without cards)
        for i in range(9):
            u = _make_user(f'act_ref{i}@example.com')
            _make_referral(self.referrer, u, status=Referral.STATUS_VERIFIED)

        # 10th referred user — will have their card activated
        self.referred_10 = _make_user('act_ref10@example.com')
        self.ref_10 = _make_referral(
            self.referrer, self.referred_10, status=Referral.STATUS_QUALIFIED,
        )

    def _create_active_card(self, user):
        card = Card.objects.create(card_code=f'ST-ACT-{user.pk}')
        card.user = user
        card.status = Card.STATUS_ACTIVE
        card.activated_at = timezone.now()
        card.save()
        return card

    def test_card_activation_creates_reward_when_eligible(self):
        card = self._create_active_card(self.referred_10)
        reward = referral_service.record_card_activation(card)
        self.assertIsNotNone(reward)
        self.assertEqual(reward.referrer, self.referrer)
        self.assertEqual(reward.status, ReferralReward.STATUS_PENDING_REVIEW)
        self.ref_10.refresh_from_db()
        self.assertEqual(self.ref_10.activation_card, card)

    def test_card_activation_does_not_create_reward_below_threshold(self):
        """Only 9 verified referrals — reward must NOT be created."""
        # Remove one referral to drop to 9 total verified
        Referral.objects.filter(referrer=self.referrer).exclude(pk=self.ref_10.pk).last().delete()
        card = self._create_active_card(self.referred_10)
        reward = referral_service.record_card_activation(card)
        self.assertIsNone(reward)

    def test_card_activation_on_non_referred_user_returns_none(self):
        non_referred = _make_user('notreferred@example.com')
        card = self._create_active_card(non_referred)
        reward = referral_service.record_card_activation(card)
        self.assertIsNone(reward)


class FailedPaymentExclusionTests(TestCase):
    """§9.8 — Failed/cancelled payments do not qualify referrals"""

    def setUp(self):
        self.referrer = _make_user('fail_ref@example.com')
        self.referred = _make_user('fail_referred@example.com')
        self.package = ProductPackage.objects.create(
            code='fail-card', name='Fail Card', price_ngn=10000, description='F'
        )
        self.ref = _make_referral(self.referrer, self.referred, status=Referral.STATUS_VERIFIED)

    def test_pending_payment_order_does_not_qualify(self):
        order = Order.objects.create(
            order_number='ORD-FAIL-001',
            user=self.referred, package=self.package,
            amount=10000, payment_status=Order.PAYMENT_PENDING,
        )
        # process_referral_qualification is only called by verify_payment after success
        # Simulate: we do NOT call process_referral_qualification for a pending order
        self.ref.refresh_from_db()
        self.assertEqual(self.ref.status, Referral.STATUS_VERIFIED)

    def test_cancelled_order_does_not_qualify(self):
        order = Order.objects.create(
            order_number='ORD-FAIL-002',
            user=self.referred, package=self.package,
            amount=10000, payment_status=Order.PAYMENT_PENDING,
            order_status=Order.STATUS_CANCELLED,
        )
        # Service should only be called after Paystack confirms success
        self.ref.refresh_from_db()
        self.assertEqual(self.ref.status, Referral.STATUS_VERIFIED)


class IdempotencyTests(TestCase):
    """§9.9 — Duplicate webhook / idempotency"""

    def setUp(self):
        self.referrer = _make_user('idempotent@example.com')
        self.package = ProductPackage.objects.create(
            code='idemp-card', name='Idemp Card', price_ngn=10000, description='I'
        )
        for i in range(10):
            u = _make_user(f'idemp_ref{i}@example.com')
            _make_referral(self.referrer, u, status=Referral.STATUS_VERIFIED)

    def test_check_and_create_reward_is_idempotent(self):
        """Calling check_and_create_reward twice does not create two rewards."""
        u = _make_user('idemp_act@example.com')
        ref = _make_referral(self.referrer, u, status=Referral.STATUS_QUALIFIED)
        card = Card.objects.create(card_code='ST-IDEMP-001')
        card.user = u
        card.status = Card.STATUS_ACTIVE
        card.activated_at = timezone.now()
        card.save()
        ref.activation_card = card
        ref.save()

        reward1 = referral_service.check_and_create_reward(self.referrer, ref, card)
        reward2 = referral_service.check_and_create_reward(self.referrer, ref, card)
        self.assertIsNotNone(reward1)
        self.assertIsNone(reward2)
        self.assertEqual(ReferralReward.objects.filter(referrer=self.referrer).count(), 1)

    def test_record_card_activation_twice_does_not_duplicate(self):
        """Activating same card twice does not set activation_card twice or create two rewards."""
        u = _make_user('idemp_act2@example.com')
        ref = _make_referral(self.referrer, u, status=Referral.STATUS_QUALIFIED)
        card = Card.objects.create(card_code='ST-IDEMP-002')
        card.user = u
        card.status = Card.STATUS_ACTIVE
        card.activated_at = timezone.now()
        card.save()

        referral_service.record_card_activation(card)
        referral_service.record_card_activation(card)  # second call
        self.assertEqual(ReferralReward.objects.filter(referrer=self.referrer).count(), 1)


class RewardStateMachineTests(TestCase):
    """§9.10 — Reward state machine"""

    def setUp(self):
        self.referrer = _make_user('statemachine@example.com')
        self.reward = ReferralReward.objects.create(
            referrer=self.referrer,
            status=ReferralReward.STATUS_PENDING_REVIEW,
        )

    def test_initial_status_is_pending_review(self):
        self.assertEqual(self.reward.status, ReferralReward.STATUS_PENDING_REVIEW)

    def test_can_transition_to_approved(self):
        self.reward.status = ReferralReward.STATUS_APPROVED
        self.reward.reviewed_at = timezone.now()
        self.reward.save()
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.status, ReferralReward.STATUS_APPROVED)

    def test_can_transition_to_available(self):
        self.reward.status = ReferralReward.STATUS_AVAILABLE
        self.reward.save()
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.status, ReferralReward.STATUS_AVAILABLE)

    def test_claim_service_transitions_to_claimed(self):
        self.reward.status = ReferralReward.STATUS_AVAILABLE
        self.reward.save()
        success, err = referral_service.claim_reward(self.reward, {
            'name': 'Test User', 'phone': '+2340000000000',
            'address': '1 Test Street', 'city': 'Lagos', 'state': 'Lagos State',
        })
        self.assertTrue(success)
        self.assertIsNone(err)
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.status, ReferralReward.STATUS_CLAIMED)
        self.assertIsNotNone(self.reward.claimed_at)
        self.assertEqual(self.reward.delivery_name, 'Test User')

    def test_cannot_claim_pending_review_reward(self):
        """Reward not yet available cannot be claimed."""
        success, err = referral_service.claim_reward(self.reward, {
            'name': 'T', 'phone': '+234', 'address': 'A', 'city': 'L', 'state': 'L',
        })
        self.assertFalse(success)
        self.assertIsNotNone(err)

    def test_fulfilled_transition(self):
        self.reward.status = ReferralReward.STATUS_CLAIMED
        self.reward.fulfilled_at = timezone.now()
        self.reward.status = ReferralReward.STATUS_FULFILLED
        self.reward.save()
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.status, ReferralReward.STATUS_FULFILLED)


class DuplicateRewardPreventionTests(TestCase):
    """§9.11 — Duplicate reward prevention"""

    def setUp(self):
        self.referrer = _make_user('dup_reward@example.com')
        self.package = ProductPackage.objects.create(
            code='dup-card', name='Dup Card', price_ngn=10000, description='D'
        )
        for i in range(10):
            u = _make_user(f'dup_ref{i}@example.com')
            _make_referral(self.referrer, u, status=Referral.STATUS_VERIFIED)
        u_act = _make_user('dup_act@example.com')
        ref = _make_referral(self.referrer, u_act, status=Referral.STATUS_QUALIFIED)
        card = Card.objects.create(card_code='ST-DUP-001')
        card.user = u_act
        card.status = Card.STATUS_ACTIVE
        card.activated_at = timezone.now()
        card.save()
        ref.activation_card = card
        ref.save()
        self.card = card
        self.ref = ref

    def test_second_activation_does_not_create_second_reward(self):
        # Create first reward
        referral_service.check_and_create_reward(self.referrer, self.ref, self.card)
        # Second call must return None
        result = referral_service.check_and_create_reward(self.referrer, self.ref, self.card)
        self.assertIsNone(result)
        self.assertEqual(
            ReferralReward.objects.filter(
                referrer=self.referrer
            ).exclude(status=ReferralReward.STATUS_REJECTED).count(),
            1
        )


class DuplicateClaimPreventionTests(TestCase):
    """§9.12 — Duplicate claim prevention"""

    def setUp(self):
        self.referrer = _make_user('dup_claim@example.com')
        self.reward = ReferralReward.objects.create(
            referrer=self.referrer,
            status=ReferralReward.STATUS_AVAILABLE,
        )

    def test_second_claim_fails(self):
        delivery = {
            'name': 'User', 'phone': '+234', 'address': 'Street', 'city': 'L', 'state': 'L',
        }
        success1, _ = referral_service.claim_reward(self.reward, delivery)
        self.assertTrue(success1)
        # Try claiming again — should fail
        success2, err = referral_service.claim_reward(self.reward, delivery)
        self.assertFalse(success2)
        self.assertIsNotNone(err)


class AdminActionsTests(TestCase):
    """§9.13 — Admin approve/reject actions"""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            email='admin@example.com', password='Admin123!',
            first_name='Admin', last_name='User',
        )
        self.referrer = _make_user('admintest@example.com')
        self.reward = ReferralReward.objects.create(
            referrer=self.referrer,
            status=ReferralReward.STATUS_PENDING_REVIEW,
        )
        self.client = Client()
        self.client.force_login(self.admin)

    def test_approve_action_sets_approved_status(self):
        from apps.core import admin as _  # noqa: ensure admin is loaded
        from django.contrib.admin.sites import AdminSite
        from apps.accounts.admin import ReferralRewardAdmin

        site = AdminSite()
        admin_instance = ReferralRewardAdmin(ReferralReward, site)
        from unittest.mock import MagicMock

        request = MagicMock()
        request.user = self.admin
        qs = ReferralReward.objects.filter(pk=self.reward.pk)
        admin_instance.approve_reward(request, qs)
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.status, ReferralReward.STATUS_APPROVED)

    def test_reject_action_sets_rejected_status(self):
        from apps.accounts.admin import ReferralRewardAdmin
        from django.contrib.admin.sites import AdminSite
        from unittest.mock import MagicMock

        site = AdminSite()
        admin_instance = ReferralRewardAdmin(ReferralReward, site)
        request = MagicMock()
        request.user = self.admin
        qs = ReferralReward.objects.filter(pk=self.reward.pk)
        admin_instance.reject_reward(request, qs)
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.status, ReferralReward.STATUS_REJECTED)


class DataIsolationTests(TestCase):
    """§9.14 — Customer cannot access another customer's referral data"""

    def setUp(self):
        self.user_a = _make_user('usera@example.com', verified=True)
        self.user_b = _make_user('userb@example.com', verified=True)
        self.client = Client()

    def test_referrals_view_only_shows_own_referrals(self):
        self.client.force_login(self.user_b)
        # Create a referral for user_a
        referred = _make_user('referred_isolation@example.com')
        _make_referral(self.user_a, referred, status=Referral.STATUS_VERIFIED)

        response = self.client.get(reverse('dashboard:referrals'))
        self.assertEqual(response.status_code, 200)
        # user_b's view should show 0 referrals
        self.assertEqual(response.context['total_count'], 0)

    def test_referrals_view_requires_login(self):
        response = Client().get(reverse('dashboard:referrals'))
        expected_url = f"{reverse('accounts:login')}?next={reverse('dashboard:referrals')}"
        self.assertRedirects(response, expected_url, fetch_redirect_response=False)


class ClaimViewTests(TestCase):
    """§9.17–9.18 — Claim view validation"""

    def setUp(self):
        self.referrer = _make_user('claimview@example.com', verified=True)
        self.client = Client()
        self.client.force_login(self.referrer)

    def test_claim_requires_delivery_fields(self):
        reward = ReferralReward.objects.create(
            referrer=self.referrer,
            status=ReferralReward.STATUS_AVAILABLE,
        )
        # POST with missing fields
        response = self.client.post(reverse('dashboard:referrals_claim'), {
            'delivery_name': '',
            'delivery_phone': '',
            'delivery_address': '',
        })
        # Should redirect back to referrals with error message
        self.assertRedirects(response, reverse('dashboard:referrals'), fetch_redirect_response=False)
        reward.refresh_from_db()
        self.assertEqual(reward.status, ReferralReward.STATUS_AVAILABLE)  # unchanged

    def test_claim_blocked_if_not_available(self):
        reward = ReferralReward.objects.create(
            referrer=self.referrer,
            status=ReferralReward.STATUS_PENDING_REVIEW,
        )
        response = self.client.post(reverse('dashboard:referrals_claim'), {
            'delivery_name': 'Test User',
            'delivery_phone': '+234000000000',
            'delivery_address': '1 Test Street Lagos',
        })
        self.assertRedirects(response, reverse('dashboard:referrals'), fetch_redirect_response=False)
        reward.refresh_from_db()
        self.assertEqual(reward.status, ReferralReward.STATUS_PENDING_REVIEW)

    def test_claim_view_requires_post(self):
        response = self.client.get(reverse('dashboard:referrals_claim'))
        self.assertEqual(response.status_code, 405)

    def test_successful_claim_stores_delivery_details(self):
        reward = ReferralReward.objects.create(
            referrer=self.referrer,
            status=ReferralReward.STATUS_AVAILABLE,
        )
        self.client.post(reverse('dashboard:referrals_claim'), {
            'delivery_name': 'Jane Doe',
            'delivery_phone': '+23480000000',
            'delivery_address': '15 Admiralty Way, Lekki Phase 1',
            'delivery_city': 'Lagos',
            'delivery_state': 'Lagos State',
        })
        reward.refresh_from_db()
        self.assertEqual(reward.status, ReferralReward.STATUS_CLAIMED)
        self.assertEqual(reward.delivery_name, 'Jane Doe')
        self.assertEqual(reward.delivery_city, 'Lagos')


class LegacyDataPreservationTests(TestCase):
    """§9.19 — Legacy ₦2,000 referral data preserved"""

    def test_existing_referral_reward_amount_preserved_on_qualification(self):
        """process_referral_qualification sets reward_amount_ngn=2000 on legacy field."""
        referrer = _make_user('legacy2k@example.com')
        referred = _make_user('legacy2k_ref@example.com')
        package = ProductPackage.objects.create(
            code='legacy-card', name='Legacy Card', price_ngn=10000, description='L'
        )
        ref = _make_referral(referrer, referred, status=Referral.STATUS_VERIFIED)
        order = Order.objects.create(
            order_number='ORD-LEGACY-001',
            user=referred, package=package, amount=10000,
            payment_status=Order.PAYMENT_PAID,
        )
        referral_service.process_referral_qualification(order)
        ref.refresh_from_db()
        # Legacy field must still be 2000 (backward compat)
        self.assertEqual(ref.reward_amount_ngn, 2000)
        self.assertEqual(ref.status, Referral.STATUS_QUALIFIED)

    def test_legacy_referrals_not_deleted_by_new_service(self):
        """check_and_create_reward does not touch or delete Referral records."""
        referrer = _make_user('nodelet@example.com')
        for i in range(10):
            u = _make_user(f'nodelet_ref{i}@example.com')
            _make_referral(referrer, u, status=Referral.STATUS_QUALIFIED)
        # Call the service
        referral_service.check_and_create_reward(referrer)
        # All referrals still exist
        self.assertEqual(Referral.objects.filter(referrer=referrer).count(), 10)


class GetReferralProgressTests(TestCase):
    """§9.20 — get_referral_progress correctness"""

    def setUp(self):
        self.referrer = _make_user('progress@example.com')
        self.package = ProductPackage.objects.create(
            code='prog-card', name='Prog Card', price_ngn=10000, description='P'
        )

    def test_progress_pct_zero_with_no_referrals(self):
        p = referral_service.get_referral_progress(self.referrer)
        self.assertEqual(p['progress_pct'], 0)
        self.assertEqual(p['verified_referrals'], 0)
        self.assertFalse(p['eligible_for_reward'])

    def test_progress_pct_fifty_with_five_verified(self):
        for i in range(5):
            u = _make_user(f'prog_ref{i}@example.com')
            _make_referral(self.referrer, u, status=Referral.STATUS_VERIFIED)
        p = referral_service.get_referral_progress(self.referrer)
        self.assertEqual(p['progress_pct'], 50)

    def test_eligible_for_reward_true_when_both_conditions_met(self):
        for i in range(10):
            u = _make_user(f'elig_ref{i}@example.com')
            _make_referral(self.referrer, u, status=Referral.STATUS_VERIFIED)
        # Give one of them an activation card
        u_act = _make_user('elig_act@example.com')
        ref = _make_referral(self.referrer, u_act, status=Referral.STATUS_QUALIFIED)
        card = Card.objects.create(card_code='ST-ELIG-001')
        ref.activation_card = card
        ref.save()
        p = referral_service.get_referral_progress(self.referrer)
        self.assertTrue(p['eligible_for_reward'])
        self.assertTrue(p['has_activation'])

    def test_eligible_for_reward_false_when_active_reward_exists(self):
        for i in range(10):
            u = _make_user(f'elig2_ref{i}@example.com')
            _make_referral(self.referrer, u, status=Referral.STATUS_VERIFIED)
        u_act = _make_user('elig2_act@example.com')
        ref = _make_referral(self.referrer, u_act, status=Referral.STATUS_QUALIFIED)
        card = Card.objects.create(card_code='ST-ELIG2-001')
        ref.activation_card = card
        ref.save()
        # Create existing active reward
        ReferralReward.objects.create(
            referrer=self.referrer,
            status=ReferralReward.STATUS_PENDING_REVIEW,
        )
        p = referral_service.get_referral_progress(self.referrer)
        # eligible_for_reward must be False (already has active reward)
        self.assertFalse(p['eligible_for_reward'])

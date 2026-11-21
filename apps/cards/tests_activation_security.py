"""
Batch 2 — NFC Card Activation Security Tests
=============================================
15 tests covering:
  - Card status lifecycle guards (RESERVED, ACTIVE, LOST, SUSPENDED, REPLACED)
  - Inventory protection (UNASSIGNED + user=None blocked; UNASSIGNED + user=self allowed)
  - Cross-user rejection
  - PIN normalization (hyphen-tolerant)
  - Incorrect PIN rejection
  - Layered rate limiting: per-account, per-card, per-IP
  - Redis unavailability (RateLimitServiceUnavailable → 503)
  - Batch 1 continuity: ?next= return-to-card after login (no auto-activation)
"""

from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.core.cache import cache
from django.contrib.auth import get_user_model

from apps.cards.models import Card
from apps.profiles.models import Profile
from apps.core.security import RateLimitServiceUnavailable

User = get_user_model()

_user_counter = 0

def _make_user(label):
    """Create a unique user. `label` is used only for readability."""
    global _user_counter
    _user_counter += 1
    email = f"b2test_{label}_{_user_counter}@stride-test.local"
    user = User.objects.create_user(
        email=email,
        password="TestPass123!",
        first_name=label.capitalize(),
        last_name="Test",
        is_email_verified=True,
    )
    Profile.objects.get_or_create(user=user)
    return user


def _make_card(card_code, status=Card.STATUS_RESERVED, user=None):
    """Create a card with a known plain-text PIN of '12345678'."""
    card = Card(card_code=card_code, status=status, user=user)
    # generate_activation_code sets activation_code_hash and returns plaintext
    # We bypass that and directly set a known hash for '12345678'
    card.set_activation_code('12345678')
    card.save()
    return card


VALID_PIN = '12345678'          # matches hash set above
VALID_PIN_HYPHEN = '1234-5678'  # same digits, hyphenated form
WRONG_PIN = 'XXXXXXXX'

ACTIVATE_URL = reverse('cards:card_activate')


class TestBatch2CardActivation(TestCase):
    """Core lifecycle and status guard tests."""

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = _make_user('activator')
        self.other_user = _make_user('other')
        self.client.force_login(self.user)

    # ------------------------------------------------------------------
    # Test 1: Reserved card activated by its authorized customer → SUCCESS
    # ------------------------------------------------------------------
    def test_01_reserved_card_activated_by_authorized_customer(self):
        card = _make_card('B2-TEST-001', status=Card.STATUS_RESERVED, user=self.user)
        resp = self.client.post(ACTIVATE_URL, {
            'card_code': 'B2-TEST-001',
            'activation_code': VALID_PIN,
        })
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_ACTIVE)
        self.assertEqual(card.user, self.user)
        self.assertRedirects(resp, reverse('dashboard:card_manage'), fetch_redirect_response=False)
        msgs = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any('activated' in m.lower() or 'success' in m.lower() for m in msgs),
                        f"Expected success message, got: {msgs}")

    # ------------------------------------------------------------------
    # Test 2: Reserved card rejected for different customer
    # ------------------------------------------------------------------
    def test_02_reserved_card_rejected_for_wrong_customer(self):
        card = _make_card('B2-TEST-002', status=Card.STATUS_RESERVED, user=self.other_user)
        resp = self.client.post(ACTIVATE_URL, {
            'card_code': 'B2-TEST-002',
            'activation_code': VALID_PIN,
        })
        card.refresh_from_db()
        self.assertNotEqual(card.status, Card.STATUS_ACTIVE)
        msgs = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any('assigned to another account' in m for m in msgs),
                        f"Expected ownership error, got: {msgs}")

    # ------------------------------------------------------------------
    # Test 3: Unassigned card (user=None) is ALLOWED — backward compat
    # Physical cards arrive before the staff RESERVED step in current flow.
    # ------------------------------------------------------------------
    def test_03_unassigned_card_no_user_allowed_for_backward_compat(self):
        """
        UNASSIGNED + user=None + is_warehouse_stock=False allowed for backward compatibility.
        Real customers who received legacy cards before staff reservation can activate.
        """
        card = _make_card('B2-TEST-003', status=Card.STATUS_UNASSIGNED, user=None)
        resp = self.client.post(ACTIVATE_URL, {
            'card_code': 'B2-TEST-003',
            'activation_code': VALID_PIN,
        })
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_ACTIVE,
                         "UNASSIGNED + user=None should still activate (backward compat)")

    # ------------------------------------------------------------------
    # Test 3b: Unassigned warehouse inventory card (is_warehouse_stock=True) is BLOCKED
    # ------------------------------------------------------------------
    def test_03b_unassigned_warehouse_stock_card_blocked(self):
        """
        New unallocated warehouse inventory (is_warehouse_stock=True) CANNOT be self-activated
        until assigned/dispatched by staff.
        """
        card = Card.objects.create(
            card_code='B2-TEST-WAREHOUSE-01',
            status=Card.STATUS_UNASSIGNED,
            is_warehouse_stock=True,
        )
        card.set_activation_code(VALID_PIN)
        card.save()

        resp = self.client.post(ACTIVATE_URL, {
            'card_code': 'B2-TEST-WAREHOUSE-01',
            'activation_code': VALID_PIN,
        })
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_UNASSIGNED)
        msgs = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any('warehouse inventory' in m.lower() for m in msgs),
                        f"Expected warehouse inventory error, got: {msgs}")

    # ------------------------------------------------------------------
    # Test 4: Unassigned card where user=self → also allowed (consistent)
    # ------------------------------------------------------------------
    def test_04_unassigned_card_assigned_to_self_allowed(self):
        card = _make_card('B2-TEST-004', status=Card.STATUS_UNASSIGNED, user=self.user)
        resp = self.client.post(ACTIVATE_URL, {
            'card_code': 'B2-TEST-004',
            'activation_code': VALID_PIN,
        })
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_ACTIVE,
                         "UNASSIGNED card provisioned to this user should activate")

    # ------------------------------------------------------------------
    # Test 5: Active card cannot be claimed again
    # ------------------------------------------------------------------
    def test_05_active_card_cannot_be_claimed(self):
        card = _make_card('B2-TEST-005', status=Card.STATUS_ACTIVE, user=self.user)
        resp = self.client.post(ACTIVATE_URL, {
            'card_code': 'B2-TEST-005',
            'activation_code': VALID_PIN,
        })
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_ACTIVE)
        msgs = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any('already active' in m for m in msgs),
                        f"Expected already-active error, got: {msgs}")

    # ------------------------------------------------------------------
    # Test 6: Lost card cannot be activated
    # ------------------------------------------------------------------
    def test_06_lost_card_cannot_be_activated(self):
        card = _make_card('B2-TEST-006', status=Card.STATUS_LOST, user=self.user)
        resp = self.client.post(ACTIVATE_URL, {
            'card_code': 'B2-TEST-006',
            'activation_code': VALID_PIN,
        })
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_LOST)
        msgs = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any('lost' in m.lower() for m in msgs),
                        f"Expected lost-card error, got: {msgs}")

    # ------------------------------------------------------------------
    # Test 7: Suspended card cannot be activated
    # ------------------------------------------------------------------
    def test_07_suspended_card_cannot_be_activated(self):
        card = _make_card('B2-TEST-007', status=Card.STATUS_SUSPENDED, user=self.user)
        resp = self.client.post(ACTIVATE_URL, {
            'card_code': 'B2-TEST-007',
            'activation_code': VALID_PIN,
        })
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_SUSPENDED)
        msgs = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any('suspended' in m.lower() for m in msgs),
                        f"Expected suspended error, got: {msgs}")

    # ------------------------------------------------------------------
    # Test 8: Replaced card cannot be activated
    # ------------------------------------------------------------------
    def test_08_replaced_card_cannot_be_activated(self):
        card = _make_card('B2-TEST-008', status=Card.STATUS_REPLACED, user=self.user)
        resp = self.client.post(ACTIVATE_URL, {
            'card_code': 'B2-TEST-008',
            'activation_code': VALID_PIN,
        })
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_REPLACED)
        msgs = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any('replaced' in m.lower() for m in msgs),
                        f"Expected replaced error, got: {msgs}")


class TestBatch2PINNormalization(TestCase):
    """Tests 9–11: PIN format normalization."""

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = _make_user('pin_tester')
        self.client.force_login(self.user)

    # ------------------------------------------------------------------
    # Test 9: Correct PIN WITH hyphen accepted
    # ------------------------------------------------------------------
    def test_09_correct_pin_with_hyphen_accepted(self):
        card = _make_card('B2-TEST-009', status=Card.STATUS_RESERVED, user=self.user)
        resp = self.client.post(ACTIVATE_URL, {
            'card_code': 'B2-TEST-009',
            'activation_code': VALID_PIN_HYPHEN,  # '1234-5678'
        })
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_ACTIVE,
                         "Hyphenated PIN should be accepted after normalization")

    # ------------------------------------------------------------------
    # Test 10: Correct PIN WITHOUT hyphen accepted
    # ------------------------------------------------------------------
    def test_10_correct_pin_without_hyphen_accepted(self):
        card = _make_card('B2-TEST-010', status=Card.STATUS_RESERVED, user=self.user)
        resp = self.client.post(ACTIVATE_URL, {
            'card_code': 'B2-TEST-010',
            'activation_code': VALID_PIN,  # '12345678'
        })
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_ACTIVE,
                         "Unhyphenated PIN should be accepted")

    # ------------------------------------------------------------------
    # Test 11: Incorrect PIN → error, card status unchanged
    # ------------------------------------------------------------------
    def test_11_incorrect_pin_rejected(self):
        card = _make_card('B2-TEST-011', status=Card.STATUS_RESERVED, user=self.user)
        resp = self.client.post(ACTIVATE_URL, {
            'card_code': 'B2-TEST-011',
            'activation_code': WRONG_PIN,
        })
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_RESERVED,
                         "Card should stay RESERVED after wrong PIN")
        msgs = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any('invalid activation code' in m.lower() for m in msgs),
                        f"Expected invalid PIN error, got: {msgs}")

    # ------------------------------------------------------------------
    # Test 11b: Historical PIN compatibility — card hashed WITH hyphen
    # Customer entering without hyphen ('HIST9999') succeeds
    # ------------------------------------------------------------------
    def test_11b_historical_hashed_pin_without_hyphen_succeeds(self):
        """
        Backward compatibility for legacy cards where activation_code_hash
        was computed directly on a hyphenated string ('HIST-9999').
        Entering 'HIST9999' without hyphen must succeed.
        """
        import hashlib
        legacy_card = Card.objects.create(
            card_code='B2-LEGACY-PIN-01',
            status=Card.STATUS_RESERVED,
            user=self.user,
        )
        legacy_card.activation_code_hash = hashlib.sha256('HIST-9999'.encode('utf-8')).hexdigest()
        legacy_card.save()

        resp = self.client.post(ACTIVATE_URL, {
            'card_code': 'B2-LEGACY-PIN-01',
            'activation_code': 'HIST9999',
        })
        legacy_card.refresh_from_db()
        self.assertEqual(legacy_card.status, Card.STATUS_ACTIVE,
                         "Entering unhyphenated PIN for card hashed with hyphen must succeed")

    # ------------------------------------------------------------------
    # Test 11c: Historical PIN compatibility — card hashed WITH hyphen
    # Customer entering WITH hyphen ('HIST-8888') succeeds
    # ------------------------------------------------------------------
    def test_11c_historical_hashed_pin_with_hyphen_succeeds(self):
        """
        Entering with hyphen ('HIST-8888') against a card hashed with hyphen must succeed.
        """
        import hashlib
        legacy_card = Card.objects.create(
            card_code='B2-LEGACY-PIN-02',
            status=Card.STATUS_RESERVED,
            user=self.user,
        )
        legacy_card.activation_code_hash = hashlib.sha256('HIST-8888'.encode('utf-8')).hexdigest()
        legacy_card.save()

        resp = self.client.post(ACTIVATE_URL, {
            'card_code': 'B2-LEGACY-PIN-02',
            'activation_code': 'HIST-8888',
        })
        legacy_card.refresh_from_db()
        self.assertEqual(legacy_card.status, Card.STATUS_ACTIVE)


class TestBatch2RateLimiting(TestCase):
    """Tests 12–15: Per-account, per-card, per-IP rate limits, and Redis failure."""

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = _make_user('rl_tester')
        self.client.force_login(self.user)

    def _make_reserved(self, code):
        return _make_card(code, status=Card.STATUS_RESERVED, user=self.user)

    # ------------------------------------------------------------------
    # Test 12: Per-account rate limiting — 5 wrong PINs → throttled
    # ------------------------------------------------------------------
    def test_12_per_account_rate_limit_triggers(self):
        """After 5 failed attempts on a user account, the 6th is throttled."""
        # Burn 5 attempts with wrong PINs on distinct cards to avoid per-card limit
        for i in range(5):
            self._make_reserved(f'B2-RL-ACC-{i:03d}')
            self.client.post(ACTIVATE_URL, {
                'card_code': f'B2-RL-ACC-{i:03d}',
                'activation_code': WRONG_PIN,
            })

        # 6th attempt — should be throttled at account level
        self._make_reserved('B2-RL-ACC-999')
        resp = self.client.post(ACTIVATE_URL, {
            'card_code': 'B2-RL-ACC-999',
            'activation_code': WRONG_PIN,
        })
        msgs = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(
            any('throttled' in m.lower() or 'too many' in m.lower() for m in msgs),
            f"Expected rate limit message after 5 failed attempts, got: {msgs}"
        )

    # ------------------------------------------------------------------
    # Test 13: Per-card rate limiting — 5 attempts on same card → throttled
    # ------------------------------------------------------------------
    def test_13_per_card_rate_limit_triggers(self):
        """5 attempts on the SAME card code (across different accounts) → throttled."""
        card = self._make_reserved('B2-RL-CARD-001')

        # Create 5 distinct users and burn the per-card limit
        for i in range(5):
            u = _make_user(f'card_rl_user_{i}')
            c = Client()
            c.force_login(u)
            # Clear per-account key so we don't hit that limit first
            cache.delete(f'rl:card_act:{u.id}')
            c.post(ACTIVATE_URL, {
                'card_code': 'B2-RL-CARD-001',
                'activation_code': WRONG_PIN,
            })

        # 6th attempt against same card — per-card limit now exceeded
        self.client.force_login(self.user)
        cache.delete(f'rl:card_act:{self.user.id}')
        resp = self.client.post(ACTIVATE_URL, {
            'card_code': 'B2-RL-CARD-001',
            'activation_code': WRONG_PIN,
        })
        msgs = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(
            any('too many activation attempts for this card' in m.lower() for m in msgs),
            f"Expected per-card rate limit message, got: {msgs}"
        )

    # ------------------------------------------------------------------
    # Test 14: Per-IP rate limiting — 10 attempts from same IP → throttled
    # ------------------------------------------------------------------
    def test_14_per_ip_rate_limit_triggers(self):
        """10 activation attempts from the same IP → throttled on the 11th."""
        # Create 10 distinct users to avoid hitting the per-account limit
        for i in range(10):
            u = _make_user(f'ip_rl_user_{i}')
            self._make_reserved(f'B2-RL-IP-{i:03d}')
            c = Client()
            c.force_login(u)
            # Send from the same IP (REMOTE_ADDR default is 127.0.0.1 in test client)
            c.post(ACTIVATE_URL, {
                'card_code': f'B2-RL-IP-{i:03d}',
                'activation_code': WRONG_PIN,
            }, REMOTE_ADDR='10.0.0.1')

        # 11th attempt from same IP
        u11 = _make_user('ip_rl_user_10')
        self._make_reserved('B2-RL-IP-010')
        c11 = Client()
        c11.force_login(u11)
        resp = c11.post(ACTIVATE_URL, {
            'card_code': 'B2-RL-IP-010',
            'activation_code': WRONG_PIN,
        }, REMOTE_ADDR='10.0.0.1')
        msgs = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(
            any('too many activation attempts from your connection' in m.lower() for m in msgs),
            f"Expected per-IP rate limit message, got: {msgs}"
        )

    # ------------------------------------------------------------------
    # Test 15: Redis unavailable → RateLimitServiceUnavailable → 503
    # ------------------------------------------------------------------
    def test_15_redis_unavailable_raises_503(self):
        """When Redis is down during a sensitive rate limit check, the view raises
        RateLimitServiceUnavailable which the middleware converts to HTTP 503."""
        self._make_reserved('B2-RL-REDIS-001')

        with patch('apps.cards.views.check_rate_limit', side_effect=RateLimitServiceUnavailable()):
            resp = self.client.post(ACTIVATE_URL, {
                'card_code': 'B2-RL-REDIS-001',
                'activation_code': VALID_PIN,
            })
        self.assertEqual(resp.status_code, 503)


class TestBatch2AuthContinuityIntegration(TestCase):
    """Test 16: Batch 1 continuity — after login with ?next=/c/<code>/, card is NOT auto-activated."""

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = _make_user('continuity_user')

    def test_16_login_with_next_returns_to_card_no_auto_activation(self):
        """
        After logging in with ?next=/c/B2-CONT-001/, user is redirected to the card
        landing page. The card must NOT be auto-activated — it still requires explicit
        PIN submission via the activation form.
        """
        card = _make_card('B2-CONT-001', status=Card.STATUS_RESERVED, user=self.user)

        resp = self.client.post(
            reverse('accounts:login') + '?next=/c/B2-CONT-001/',
            {
                'username': self.user.email,  # UserLoginForm uses 'username' field for email
                'password': 'TestPass123!',
                'next': '/c/B2-CONT-001/',
            },
            follow=False,
        )

        # Should redirect to the card page, not the dashboard
        self.assertIn(resp.status_code, [301, 302])
        location = resp.get('Location', '')
        self.assertIn('/c/B2-CONT-001/', location,
                      f"Expected redirect to card page, got Location: {location}")

        # Card must NOT have been activated
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_RESERVED,
                         "Card must NOT be auto-activated on login redirect")

    # ------------------------------------------------------------------
    # Test 17: P1 Regression - Malicious next parameter rejected in activation
    # ------------------------------------------------------------------
    def test_17_activation_redirect_rejects_malicious_next(self):
        """P1 Regression: Malicious, protocol-relative, or malformed next values in activation must be rejected."""
        self.client.force_login(self.user)
        card = _make_card('B2-REDIR-001', status=Card.STATUS_UNASSIGNED, user=None)
        malicious_targets = [
            '/c//evil.com',
            '/c/..//evil.com',
            '/c/%2F%2Fevil.com',
            '/c/\\evil.com',
            '//evil.com',
            'https://evil.com/c/B2-REDIR-001/',
            '/c/http://evil.com',
        ]
        for bad_next in malicious_targets:
            cache.clear()
            resp = self.client.post(ACTIVATE_URL, {
                'card_code': 'B2-REDIR-001',
                'activation_code': WRONG_PIN,
                'next': bad_next
            })
            self.assertNotEqual(resp.url, bad_next, f"Vulnerability reproduced: redirected to {bad_next}")
            self.assertEqual(resp.url, reverse('dashboard:card_manage'), f"Failed for next={bad_next}: got {resp.url}")

    def test_18_activation_redirect_preserves_valid_card_url(self):
        """Valid internal card activation destination is preserved on error."""
        self.client.force_login(self.user)
        card = _make_card('B2-REDIR-002', status=Card.STATUS_UNASSIGNED, user=None)
        valid_target = f"/c/{card.card_code}/"
        cache.clear()
        resp = self.client.post(ACTIVATE_URL, {
            'card_code': card.card_code,
            'activation_code': WRONG_PIN,
            'next': valid_target
        })
        self.assertRedirects(resp, valid_target, fetch_redirect_response=False)


class TestActivationSuccessView(TestCase):
    """Test dedicated activation success view."""

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = _make_user('success_user')
        self.other_user = _make_user('success_other')
        self.client.force_login(self.user)

    def test_success_view_accessible_by_owner(self):
        card = Card.objects.create(
            card_code='SUCC-001',
            status=Card.STATUS_ACTIVE,
            user=self.user,
            profile=self.user.profile,
        )
        resp = self.client.get(reverse('cards:activation_success', kwargs={'card_code': 'SUCC-001'}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'SUCC-001')
        self.assertContains(resp, 'Smart Card Is Live')

    def test_success_view_forbidden_for_non_owner(self):
        card = Card.objects.create(
            card_code='SUCC-002',
            status=Card.STATUS_ACTIVE,
            user=self.other_user,
            profile=self.other_user.profile,
        )
        resp = self.client.get(reverse('cards:activation_success', kwargs={'card_code': 'SUCC-002'}))
        self.assertEqual(resp.status_code, 404)

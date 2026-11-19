"""
STRIDE Referral Reward Service
===============================
Business logic for the new product-based referral reward programme.

New Programme Rules (v2):
- A referrer earns ONE free STRIDE Smart NFC Card when:
  1. They have >= 10 unique verified referrals (email-confirmed new users).
  2. At least 1 of those referred users has completed a successful paid order
     AND activated their physical NFC card.

- Reward: one free Smart NFC Card + free nationwide delivery.
- Non-transferable, non-cash, non-combinable.
- One active reward per referrer at a time (a new cycle can begin after fulfilment
  or rejection if they reach the next 10-verified milestone).

Legacy data: Existing Referral records with reward_amount_ngn=2000 are historical
(₦2,000 cash programme). They are preserved as-is and must not be altered.
The new programme tracks rewards exclusively via ReferralReward model.

This service is the ONLY place that creates ReferralReward records.
All callers (card activation hook, payment webhook) must go through this service.
"""

import logging
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger('stride.referrals')

REQUIRED_VERIFIED_REFERRALS = 10


def _get_referral_counts(referrer):
    """
    Returns a dict with referral statistics for a referrer.
    All DB reads — no writes.
    """
    from apps.accounts.models import Referral

    all_referrals = Referral.objects.filter(referrer=referrer)
    total = all_referrals.count()

    # Verified = status in (verified, qualified, rewarded)  — email confirmed
    verified = all_referrals.filter(
        status__in=[
            Referral.STATUS_VERIFIED,
            Referral.STATUS_QUALIFIED,
            Referral.STATUS_REWARDED,
        ]
    ).count()

    # Purchase-qualified: has a paid qualifying_order
    purchase_qualified = all_referrals.filter(
        qualifying_order__isnull=False,
        status__in=[Referral.STATUS_QUALIFIED, Referral.STATUS_REWARDED],
    ).count()

    # Activation-qualified: has an activation_card set
    activation_qualified = all_referrals.filter(
        activation_card__isnull=False
    ).count()

    return {
        'total': total,
        'verified': verified,
        'purchase_qualified': purchase_qualified,
        'activation_qualified': activation_qualified,
    }


def get_referral_progress(referrer):
    """
    Returns the referrer's current progress toward the reward.
    Safe to call from views and templates.

    Returns dict:
        total_referrals:       int — all referrals regardless of status
        verified_referrals:    int — email-verified referrals
        required_verified:     int — always REQUIRED_VERIFIED_REFERRALS (10)
        purchase_qualified:    int — referrals with paid orders
        activation_qualified:  int — referrals with activated cards
        has_activation:        bool — True if any referred user activated a card
        progress_pct:          int (0-100) — % toward 10-verified goal
        reward:                ReferralReward | None — most recent non-rejected reward
        eligible_for_reward:   bool — True if conditions met and no active reward pending
    """
    from apps.accounts.models import ReferralReward

    counts = _get_referral_counts(referrer)

    # Find most recent active reward (non-rejected)
    reward = (
        referrer.referral_rewards
        .exclude(status=ReferralReward.STATUS_REJECTED)
        .order_by('-created_at')
        .first()
    )

    # Determine eligibility: 10+ verified AND 1+ activation AND no current active reward
    has_activation = counts['activation_qualified'] >= 1
    meets_threshold = counts['verified'] >= REQUIRED_VERIFIED_REFERRALS
    no_active_reward = reward is None or reward.status == ReferralReward.STATUS_REJECTED

    eligible_for_reward = meets_threshold and has_activation and no_active_reward

    return {
        'total_referrals': counts['total'],
        'verified_referrals': counts['verified'],
        'required_verified': REQUIRED_VERIFIED_REFERRALS,
        'purchase_qualified': counts['purchase_qualified'],
        'activation_qualified': counts['activation_qualified'],
        'has_activation': has_activation,
        'progress_pct': min(100, int(counts['verified'] / REQUIRED_VERIFIED_REFERRALS * 100)),
        'reward': reward,
        'eligible_for_reward': eligible_for_reward,
    }


@transaction.atomic
def check_and_create_reward(referrer, triggering_referral=None, triggering_card=None):
    """
    Idempotently checks whether the referrer qualifies for a reward and creates
    a ReferralReward record if they do.

    Must be called inside a transaction with select_for_update on the referrer
    or the caller must ensure serialisation. This function acquires its own lock.

    Args:
        referrer:             User — the person who made the referrals
        triggering_referral:  Referral | None — the referral whose activation triggered this check
        triggering_card:      Card | None — the card whose activation triggered this check

    Returns:
        ReferralReward | None — the newly created reward, or None if conditions not met
                                or a non-rejected reward already exists
    """
    from apps.accounts.models import Referral, ReferralReward
    from django.contrib.auth import get_user_model
    User = get_user_model()

    # Lock referrer row to prevent race conditions
    referrer = User.objects.select_for_update().get(pk=referrer.pk)

    # --- Idempotency check: do NOT create a second active reward ---
    existing_active = (
        referrer.referral_rewards
        .exclude(status=ReferralReward.STATUS_REJECTED)
        .exists()
    )
    if existing_active:
        logger.info(
            "check_and_create_reward: referrer %s already has an active reward. Skipping.",
            referrer.email,
        )
        return None

    # --- Qualification check ---
    verified_count = Referral.objects.filter(
        referrer=referrer,
        status__in=[
            Referral.STATUS_VERIFIED,
            Referral.STATUS_QUALIFIED,
            Referral.STATUS_REWARDED,
        ],
    ).count()

    has_activation = Referral.objects.filter(
        referrer=referrer,
        activation_card__isnull=False,
    ).exists()

    if verified_count < REQUIRED_VERIFIED_REFERRALS or not has_activation:
        logger.info(
            "check_and_create_reward: referrer %s not yet eligible "
            "(verified=%d/%d, has_activation=%s).",
            referrer.email, verified_count, REQUIRED_VERIFIED_REFERRALS, has_activation,
        )
        return None

    # --- Create reward ---
    reward = ReferralReward.objects.create(
        referrer=referrer,
        status=ReferralReward.STATUS_PENDING_REVIEW,
        triggering_referral=triggering_referral,
        triggering_card=triggering_card,
    )
    logger.info(
        "check_and_create_reward: ReferralReward #%d created for referrer %s "
        "(verified=%d, triggering_card=%s).",
        reward.pk, referrer.email, verified_count,
        triggering_card.card_code if triggering_card else "N/A",
    )
    return reward


@transaction.atomic
def record_card_activation(card):
    """
    Called when a physical card is successfully activated.
    Checks whether the activated card's user was referred;
    if so, records the activation on the Referral record and checks reward eligibility.

    Args:
        card: Card — the newly activated card

    Returns:
        ReferralReward | None — a newly created reward if conditions are met, else None
    """
    if not card.user:
        return None

    try:
        referral = card.user.referred_by  # OneToOneField reverse accessor
    except Exception:
        # User was not referred — normal case
        return None

    # Record activation on the referral (idempotent — only update if not already set)
    if referral.activation_card_id is None:
        referral.activation_card = card
        referral.save(update_fields=['activation_card'])
        logger.info(
            "record_card_activation: activation_card set on Referral #%d "
            "(referred_user=%s, card=%s).",
            referral.pk, card.user.email, card.card_code,
        )
    else:
        logger.info(
            "record_card_activation: Referral #%d already has an activation_card. Skipping update.",
            referral.pk,
        )

    # Check if referrer now qualifies for a reward
    return check_and_create_reward(
        referrer=referral.referrer,
        triggering_referral=referral,
        triggering_card=card,
    )


@transaction.atomic
def process_referral_qualification(order):
    """
    Called after a successful payment to mark the referral as purchase-qualified.
    Preserves legacy ₦2,000 reward_amount_ngn field for historical records.
    Also checks reward eligibility (edge case: referred user already activated card
    before this payment completed).

    Args:
        order: Order — the successfully paid order

    Returns:
        ReferralReward | None
    """
    from apps.accounts.models import Referral

    if not order.user:
        return None

    referral = Referral.objects.filter(
        referred_user=order.user,
        status__in=[Referral.STATUS_PENDING, Referral.STATUS_VERIFIED],
    ).first()

    if not referral:
        # Already qualified, or no referral record — nothing to do
        return None

    referral.status = Referral.STATUS_QUALIFIED
    referral.qualifying_order = order
    referral.qualified_at = timezone.now()
    # Preserve legacy field (historical cash value — not used in new programme logic)
    referral.reward_amount_ngn = 2000
    referral.save()

    logger.info(
        "process_referral_qualification: Referral #%d qualified (referrer=%s, order=%s).",
        referral.pk, referral.referrer.email, order.order_number,
    )

    # Edge case: if the referred user already activated a card, check for reward now
    if referral.activation_card_id is not None:
        return check_and_create_reward(
            referrer=referral.referrer,
            triggering_referral=referral,
            triggering_card=referral.activation_card,
        )

    return None


@transaction.atomic
def claim_reward(reward, delivery_data):
    """
    Records a customer's claim of an available reward.

    Args:
        reward:        ReferralReward — must be in STATUS_AVAILABLE
        delivery_data: dict with keys: name, phone, address, city, state

    Returns:
        (success: bool, error_message: str | None)
    """
    from apps.accounts.models import ReferralReward

    if reward.status != ReferralReward.STATUS_AVAILABLE:
        return False, "This reward is not currently available to claim."

    # Re-fetch with lock
    reward = ReferralReward.objects.select_for_update().get(pk=reward.pk)
    if reward.status != ReferralReward.STATUS_AVAILABLE:
        return False, "This reward is not currently available to claim."

    reward.status = ReferralReward.STATUS_CLAIMED
    reward.claimed_at = timezone.now()
    reward.delivery_name = delivery_data.get('name', '')[:150]
    reward.delivery_phone = delivery_data.get('phone', '')[:50]
    reward.delivery_address = delivery_data.get('address', '')
    reward.delivery_city = delivery_data.get('city', '')[:100]
    reward.delivery_state = delivery_data.get('state', '')[:100]
    reward.save()

    logger.info(
        "claim_reward: ReferralReward #%d claimed by %s.",
        reward.pk, reward.referrer.email,
    )
    return True, None

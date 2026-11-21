# STRIDE Console & Hardware Provisioning — Staging Deployment Report

**Project:** STRIDE NFC Platform  
**Branch:** `staging`  
**Target Environment:** Railway Staging (`https://nfc-staging.up.railway.app`)  
**Deployment Date:** November 21, 2026  
**Latest Deployment Commits:**
- `669a9ba`: feat(console): deploy STRIDE Console and NFC Hardware Provisioning engine to staging
- `cdfcdcc`: style(profile): raise avatar position onto cover banner (-70px margin-top)
**Status:** **DEPLOYED & VERIFIED ON STAGING**  
**Production Isolation:** **CONFIRMED — NO PRODUCTION ENVIRONMENT MODIFIED**

---

## 1. Deployment Execution Summary

The STRIDE Console, NFC Card Provisioning Engine, database migrations, and public profile visual refinements have been deployed to the Railway staging environment.

### Deployment Parameters & Pipeline
* **Repository:** `https://github.com/S-A-UMAR/nfc.git`
* **Branch:** `staging`
* **Trigger:** Push to `origin/staging`
* **Builder:** Nixpacks
* **Pre-Deploy Command:** `python manage.py migrate --noinput`
* **Runtime Command:** `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
* **Healthcheck Route:** `/health/` (HTTP 200)

---

## 2. Database Migrations Status on Staging

During the Railway deployment pre-deploy lifecycle hook, the database migrations were executed against the isolated staging PostgreSQL database (Neon Serverless):

```
cards
 [X] 0001_initial
 [X] 0002_card_activation_code_hash
 [X] 0003_add_referral_reward_model
 [X] 0004_add_card_warehouse_stock_flag
 [X] 0005_card_batch_reference_card_provisioning_stage
core
 [X] 0001_initial
 [X] 0002_adminauditlog
 [X] 0003_business_inquiry
 [X] 0004_add_business_type
 [X] 0005_mediacleanuptask
 [X] 0006_alter_adminauditlog_action
orders
 [X] 0001_initial
 [X] 0002_alter_order_order_status_alter_order_payment_status
 [X] 0003_alter_order_order_status_alter_order_payment_status
 [X] 0004_alter_order_user
 [X] 0005_order_shipping_carrier_and_more
```

All 3 new migrations (`cards.0005`, `core.0006`, `orders.0005`) applied cleanly with zero errors.

---

## 3. Live Staging Smoke Tests

Direct HTTP verification against live Railway staging endpoints (`https://nfc-staging.up.railway.app`):

| Endpoint / Route | Method | Expected Result | Live Staging Response | Verdict |
|---|---|---|---|---|
| `/health/` | `GET` | `HTTP 200` | `HTTP/2 200` | **PASS** |
| `/console/` | `GET` | `302 -> /auth/login/?next=/console/` | `HTTP/2 302 (location: /auth/login/?next=/console/)` | **PASS** |
| `/console/cards/` | `GET` | `302 -> /auth/login/?next=/console/cards/` | `HTTP/2 302 (location: /auth/login/?next=/console/cards/)` | **PASS** |
| `/console/cards/packaging/<token>/` | `GET` | `302 -> /auth/login/?next=...` | `HTTP/2 302 (location: /auth/login/?next=...)` | **PASS** |
| `/console/cards/packaging/<token>/csv/` | `GET` | `302 -> /auth/login/?next=...` | `HTTP/2 302 (location: /auth/login/?next=...)` | **PASS** |
| `/console/cards/packaging/<token>/print/` | `GET` | `302 -> /auth/login/?next=...` | `HTTP/2 302 (location: /auth/login/?next=...)` | **PASS** |
| `/` (Home) | `GET` | `HTTP 200` | `HTTP/2 200` | **PASS** |
| `/auth/login/` | `GET` | `HTTP 200` + CSRF cookie | `HTTP/2 200 (set-cookie: csrftoken=...)` | **PASS** |
| `/auth/register/` | `GET` | `HTTP 200` + CSRF cookie | `HTTP/2 200 (set-cookie: csrftoken=...)` | **PASS** |
| `/activate/` | `GET` | `302 -> /auth/login/?next=/activate/` | `HTTP/2 302 (location: /auth/login/?next=/activate/)` | **PASS** |
| `/c/NONEXISTENT1/` (NFC) | `GET` | `HTTP 404` (branded error page) | `HTTP/2 404` | **PASS** |

---

## 4. Profile Visual & Form Refinements

1. **Cover Banner Upload Fix:**
   * Resolved the `(unknown format — no extension detected)` error by bypassing validation on existing stored Cloudinary files (`isinstance(image, UploadedFile)`) and checking real image magic bytes via Pillow.
2. **Banner Ambient Bottom Fade:**
   * Implemented CSS `mask-image: linear-gradient(to bottom, rgba(0,0,0,1) 0%, rgba(0,0,0,1) 50%, rgba(0,0,0,0) 100%)` and multi-stop gradient darkening overlay to dissolve the banner smoothly into the card body.
3. **Avatar Sizing & Raised Position:**
   * Resized avatar ring to **82px** with refined padding and font-size.
   * Raised the avatar position onto the banner via `margin-top: -70px;` (elevated `z-index: 12`) so that 85% of the circle sits directly on the textured banner, floating gracefully above the ambient bottom fade.

---

## 5. Security & Isolation Verification

* **Credential Isolation:** Plaintext activation PINs are never stored in PostgreSQL. They exist only in ephemeral cache for 15 minutes, accessible exclusively by the creator or managers, with explicit acknowledge-to-purge functionality.
* **Manufacturing Archive Security:** Factory ZIP exports strictly exclude PINs or PIN columns in the `nfc_encoding_manifest.csv`.
* **Formula Injection Defenses:** All CSV exports escape formula prefixes (`=`, `+`, `-`, `@`) with a leading apostrophe.
* **Staging Environment Guardrails:**
  * `ENVIRONMENT=staging`
  * Paystack restricted to Sandbox test keys (`pk_test_...` / `sk_test_...`; live keys fail-closed)
  * Brevo email recipient allowlist blocks outbound transactional emails to non-staff recipients
  * Database hosted on dedicated Neon staging serverless cluster
* **Production Status:** **CONFIRMED UNTOUCHED**. No production databases, credentials, domains, or code branches were modified.

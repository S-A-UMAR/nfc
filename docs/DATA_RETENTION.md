# UZYRA PLATFORM — DATA RETENTION & MINIMIZATION MAP
**Internal Technical & Compliance Specification**  
**Governing Statute:** Nigeria Data Protection Act 2023 (NDPA)  
**Classification:** Confidential — Internal Operations & Compliance

---

## 1. Overview & Data Minimization Principles
UZYRA operates under strict data minimization principles pursuant to Section 24 of the NDPA 2023:
1. Only collect personal data strictly required to deliver the digital identity, NFC hardware, and web platform services.
2. Store personal records in encrypted storage (TLS 1.3 in transit, AES/PBKDF2 for sensitive tokens).
3. Do not employ third-party advertising surveillance, tracking pixels, or cross-site tracking.
4. Establish clear retention lifecycles and permanent erasure flows upon verified user account deletion.

---

## 2. Comprehensive Data Inventory & Retention Map

### A. Customer User Accounts (`apps.accounts.User`)
- **What is stored:** First name, last name, email address (unique username), phone number (optional), hashed password (PBKDF2 SHA-256), email verification status (`is_email_verified`), `date_joined`, `last_login`.
- **Purpose:** User authentication, account ownership, and communications.
- **Necessity:** Essential for service operation.
- **Access:** Account owner (self), Platform Staff with verified admin credentials.
- **User Control:** Editable anytime via `Settings > Account Details`.
- **Retention Lifecycle:** Retained while account is active. Permanently purged from the primary database upon customer-initiated account deletion via `dashboard:delete_account`.

---

### B. Digital Profiles (`apps.profiles.Profile`, `SocialLink`, `CustomLink`)
- **What is stored:** Display name, job title, bio, location, business name, business category, direct phone, WhatsApp number, public email, website URL, custom button links, social media URLs, avatar/cover photo references.
- **Purpose:** Public digital business card rendered at `/u/<slug>/`.
- **Necessity:** Core platform value proposition. Information is published solely by explicit user choice.
- **Access:** Public (anyone visiting `/u/<slug>/` or tapping the paired physical card), Account owner (edit rights).
- **User Control:** 100% editable, unpublishable, or erasable via dashboard.
- **Retention Lifecycle:** Retained while account exists. Deleted immediately via CASCADE when the account is deleted.

---

### C. Physical NFC Smart Cards (`apps.cards.Card`, `CardEvent`)
- **What is stored:** Card code (e.g. `BR-000001`), chip material, activation status (`unassigned`, `active`, `suspended`, `lost`, `replaced`), activation security PIN hash (PBKDF2), activation timestamp, CardEvent logs (event type: NFC tap or QR scan, user agent, timestamp).
- **Purpose:** Physical smart card inventory control, supply chain integrity, dynamic redirection routing via `/c/<card_code>/`.
- **Necessity:** Essential for NFC hardware routing.
- **Access:** Card owner, authorized fulfillment staff, operations portal.
- **User Control:** User can toggle status to "Suspended" or "Report Lost" instantly.
- **Account Deletion Behavior:** The physical card is decoupled: `card.user = None`, `card.profile = None`, `card.status = 'unassigned'`. Taps immediately cease resolving to the former owner's profile and display the unassigned card screen. Card code remains in inventory for reuse or recycling.

---

### D. Orders & Shipping Data (`apps.orders.Order`, `OrderRequirement`)
- **What is stored:** Order number, package selected, final price (NGN), payment status, order status, courier recipient name, delivery street address, city, state, courier contact phone number, packaging notes.
- **Purpose:** Physical card manufacturing, laser engraving, and nationwide courier delivery.
- **Necessity:** Required for physical contract fulfillment and courier dispatch.
- **Access:** Ordering customer, operations logistics staff.
- **Retention Lifecycle:** Under Nigerian tax, financial reporting, and Federal Competition and Consumer Protection Act (FCCPA) standards, commercial sales invoices and delivery records are retained for a minimum of **6 years** for statutory audit and tax reconciliation.
- **Account Deletion Behavior:** User login credentials are deleted; historical sales invoice records remain archived in order records without active web login access.

---

### E. Financial & Payment Records (`apps.payments.Payment`)
- **What is stored:** Paystack transaction reference, payment amount (NGN), currency, payment status (`pending`, `success`, `failed`, `refunded`), channel, paid timestamp, Paystack gateway reference token.
- **What is NEVER stored:** Full 16-digit debit/credit card numbers, CVV security codes, card expiration dates, bank PINs.
- **Purpose:** Reconciliation, fraud prevention, Paystack webhook confirmation, and customer refund verification.
- **Necessity:** Mandatory for financial and tax auditing.
- **Retention Lifecycle:** Retained for statutory 6-year financial audit period.

---

### F. Interaction Analytics (`apps.analytics.AnalyticsEvent`)
- **What is stored:** Event type (`profile_view`, `card_tap`, `qr_scan`, `whatsapp_click`, `call_click`, `email_click`, `vcard_download`, `social_click`), timestamp, target label, truncated User-Agent (max 255 chars), truncated Referer (max 255 chars), SHA-256 hashed IP (optional).
- **What is NOT stored:** Raw IP addresses, visitor names, visitor phone numbers, cross-site tracking cookies.
- **Purpose:** Real-time engagement analytics displayed on customer dashboard.
- **Necessity:** Core customer feature.
- **Retention Lifecycle:** Events aggregate continuously. Upon user profile deletion, related analytics events are purged via database CASCADE. Rolling retention policy of 12 months for historical aggregate queries.

---

### G. Security Verification Codes (`apps.accounts.OTPCode`)
- **What is stored:** 6-digit numeric OTP code (stored in plain or hashed), user link, expiration timestamp, usage status.
- **Purpose:** Two-factor email ownership verification and password reset validation.
- **Necessity:** Essential authentication security.
- **Retention Lifecycle:** Single-use with strict **10-minute expiration window**. Expired and used codes are periodically purged from the database.

---

### H. Contact Inquiries & Privacy Requests (`apps.core.ContactMessage`)
- **What is stored:** Full name, email address, phone number (optional), subject (including `[Data Privacy Request]`, `[IP / Copyright Notice]`, etc.), message body, resolution status (`is_resolved`), timestamp.
- **Purpose:** Customer support, warranty claims, and formal NDPA Data Subject Request tracking.
- **Necessity:** Required for legal communication and regulatory audit trails.
- **Retention Lifecycle:** Active inquiries retained until resolution. Resolved privacy requests and statutory legal notices archived for **3 years** to demonstrate regulatory compliance with NDPC mandates.

---

### I. Uploaded Media & Photographs (Cloudinary CDN)
- **What is stored:** Profile avatars, cover banners, and business logos stored on Cloudinary persistent cloud storage.
- **Purpose:** Visual customization of digital profiles.
- **Necessity:** Profile branding.
- **User Control:** User can replace or clear images anytime via profile edit dashboard.
- **Account Deletion Behavior:** The database references are permanently removed upon profile deletion; corresponding Cloudinary assets are unreferenced and scheduled for permanent bucket garbage collection.

---

## 3. Summary of Data Lifecycles

| Category | Primary Retention Location | Retention Period | Deletion Mechanism |
|---|---|---|---|
| User Credentials | TiDB MySQL (`User`) | Active account duration | Permanent user delete (`dashboard:delete_account`) |
| Profile & Links | TiDB MySQL (`Profile`) | Active account duration | Instant CASCADE delete upon account deletion |
| Physical Cards | TiDB MySQL (`Card`) | Permanent hardware lifecycle | Reset to `unassigned`, unlinked from user |
| Orders & Invoices | TiDB MySQL (`Order`) | 6 Years (Statutory Tax Law) | Retained for tax records; user credentials deleted |
| Payment References | TiDB MySQL (`Payment`) | 6 Years (Financial Audit) | Retained for audit; no raw payment cards stored |
| Analytics Telemetry | TiDB MySQL (`AnalyticsEvent`) | 12 Months rolling / Account lifetime | CASCADE delete upon profile deletion |
| Security OTP Codes | TiDB MySQL (`OTPCode`) | 10 Minutes (Ephemeral) | Automated expiration & database cleanup |
| Privacy Complaints | TiDB MySQL (`ContactMessage`) | 3 Years (Compliance Audit) | Resolved & archived in administrative audit trail |
| Media Files | Cloudinary Storage | Account lifetime | Dereferenced upon profile deletion |

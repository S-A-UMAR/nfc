# UZYRA PLATFORM — DATA PRIVACY REQUEST PROCEDURE
**Standard Operating Procedure (SOP) for Data Subject Access & Privacy Requests**  
**Governing Statute:** Nigeria Data Protection Act 2023 (NDPA)  
**Classification:** Confidential — Operations & Compliance Manual  
**Effective Date:** October 2026  
**Review Cycle:** Annual  

---

## 1. Purpose & Scope
This Standard Operating Procedure (SOP) defines the operational workflow for receiving, verifying, investigating, fulfilling, and logging data protection requests submitted by individuals under the **Nigeria Data Protection Act 2023 (NDPA)** and global privacy benchmarks.

This procedure applies to all requests concerning:
1. **Right of Access** (NDPA Section 34(1)(a)): Confirmation of whether personal data is processed, and access to that data.
2. **Right to Rectification** (NDPA Section 34(1)(b)): Correction of inaccurate or incomplete personal records.
3. **Right to Erasure / Deletion** (NDPA Section 34(1)(c)): Permanent deletion or anonymization of personal data ("Right to be Forgotten").
4. **Right to Restriction / Objection** (NDPA Section 34(1)(d)): Ceasing specific processing activities (e.g., promotional communications, analytics).
5. **Right to Data Portability** (NDPA Section 38): Provision of personal data in a structured, commonly used, machine-readable format (.vcf, JSON, CSV).

---

## 2. Ingestion & Intake Channels
Data privacy requests enter the UZYRA administrative pipeline through the following verified channels:

1. **Formal Web Ingestion (Primary):**
   - URL: `https://uzyra.com/legal/complaints/?category=privacy`
   - Automatically prefixes message subject with `[Data Privacy Request]`
   - Ingests into Django backend as an authenticated or unauthenticated `ContactMessage` record.
2. **Dedicated Email Ingestion:**
   - Dedicated Mailbox: `privacy@uzyra.com` (cc: `legal@uzyra.com`, `support@uzyra.com`)
   - Monitored by the Data Protection Officer (DPO) and operations lead.
3. **In-App Dashboard Self-Service:**
   - Users can self-manage data access and correction directly via `Dashboard > Settings`.
   - Contact card data portability is available on-demand via the **Export Contact Card (.vcf)** utility.
   - Irreversible account erasure is available on-demand via **Danger Zone > Delete Account** (`dashboard:delete_account`).

---

## 3. Statutory Timelines
- **Standard Acknowledgment:** Within **48 hours** of receipt.
- **Statutory Resolution Deadline:** Within **30 calendar days** from verified identity receipt pursuant to NDPA standards.
- **Complex Request Extension:** Where requests are unusually complex or numerous, the period may be extended by up to an additional 30 days. The data subject must be formally notified of the extension and rationale within the initial 30-day window.

---

## 4. End-to-End Operational Workflow (8-Step SOP)

### Step 1: Ingestion, Triage & Category Tagging
1. Open the UZYRA Django Admin portal at `/admin/core/contactmessage/`.
2. Apply the **Inquiry Category Filter** located on the right sidebar and select `Data Privacy Request (NDPA)`.
3. Open the incoming message to review the request details, contact email, user link, and submission timestamp.
4. Verify that the request has not already been resolved (`is_resolved == False`).

### Step 2: Requester Identity Verification
Before releasing or deleting any personal records, staff **MUST** authenticate the identity of the requester to prevent unlawful data disclosure or unauthorized account deletion:
- **Authenticated Submissions:** If the user submitted while logged in (`message.user` is populated), identity is verified.
- **Unauthenticated Submissions:** If submitted via general email or while logged out:
  1. Check if the provided email exists in `apps.accounts.models.User`.
  2. Send a verification email to the registered account email containing a single-use verification link or requiring reply from that registered address.
  3. Require confirmation of the last 4 digits of the phone number or the last order number on record.
  *Never disclose personal records to an unverified email or third party without documented legal power of attorney.*

### Step 3: Scope Determination & Legal Assessment
Review the nature of the request against UZYRA's data models (`User`, `Profile`, `Card`, `Order`, `Payment`, `AnalyticsEvent`):
- **Access / Portability:** Assess whether the user is requesting basic profile data (obtainable via dashboard) or comprehensive database records.
- **Rectification:** Assess whether the requested correction can be performed directly by the user in `Dashboard > Edit Profile` / `Settings`.
- **Erasure / Deletion:**
  - Standard user profile, social links, custom websites, avatars: Eligible for immediate deletion.
  - Physical NFC cards: Must be decoupled and returned to `STATUS_UNASSIGNED` inventory.
  - Financial Orders & Tax Invoices (`Order`, `Payment`): **Statutory Retention Exception.** Nigerian tax laws, accounting standards, and FCCPA guidelines mandate retaining commercial sales transactions for a minimum of 6 years. Personal profile and login credentials can be deleted, but sales receipts are archived securely.

### Step 4: Access & Portability Fulfillment
1. If the user desires standard contact data, direct them to `Dashboard > Settings > Export Contact Card (.vcf)`.
2. For comprehensive subject access requests:
   - Export account details: First/last name, registered email, registration date, login timestamps.
   - Export digital profile details: Bio, title, business name, public links, paired card serial numbers.
   - Export transaction history: Order numbers, items purchased, payment timestamps (excluding payment card tokens which UZYRA never holds).
   - Package the data in a password-protected zip file containing clean JSON/CSV format.
   - Transmit securely to the verified email address.

### Step 5: Rectification Fulfillment
1. If the user is active, guide them to `Dashboard > Settings` or `Dashboard > Edit Profile` where name, email, phone, bio, and links can be corrected instantly.
2. If the user requires administrative correction (e.g. email change where verification is required, or historical order address correction before fulfillment), administrative staff updates the record in Django admin with an audit comment.

### Step 6: Erasure Fulfillment (Account Deletion & Data Purge)
1. **Self-Service Erasure (Preferred):**
   - Direct user to `https://uzyra.com/dashboard/settings/delete-account/`.
   - The user enters their password to confirm informed, voluntary consent.
   - The system automatically:
     a. Decouples all linked physical NFC cards (`Card.objects.filter(user=user).update(user=None, profile=None, status='unassigned')`).
     b. Flushes active sessions (`auth_logout(request)`).
     c. Permanently cascades user, profile, social links, and website records (`user.delete()`).
2. **Admin-Assisted Erasure:**
   - Where a user cannot log in and requests manual erasure in writing:
     a. DPO validates identity proof.
     b. DPO unassigns cards via `apps.cards.models.Card`.
     c. DPO purges the `User` record via Django Admin or management command.
     d. Confirms physical NFC hardware URL `/c/<card_code>/` redirects to unassigned card notice.

### Step 7: Documentation & Audit Logging
1. In Django Admin, open the corresponding `ContactMessage` record.
2. Check `is_resolved = True`.
3. In internal admin notes, record:
   - Date and time of fulfillment.
   - Identity verification method used.
   - Actions performed (e.g., "Exported JSON archive sent to user", "Account deleted and NFC card BR-000042 unassigned").
   - Name/ID of the handling staff member.

### Step 8: Written Notification & Closing
1. Dispatch formal resolution email to the data subject from `privacy@uzyra.com`:
   - State clearly what actions have been completed.
   - Reiterate that statutory financial transaction records (if any) are retained in archived tax ledgers under Nigerian law.
   - Inform the user of their statutory right to lodge a complaint with the **Nigeria Data Protection Commission (NDPC)** if dissatisfied.
2. Close the ticket.

---

## 5. Escalation & Regulatory Reporting
- **Data Protection Officer (DPO):** `dpo@uzyra.com` / `privacy@uzyra.com`
- **Regulatory Authority:**
  - Nigeria Data Protection Commission (NDPC)
  - Headquarters: Abuja, Federal Capital Territory, Nigeria
  - Official Portal: `https://ndpc.gov.ng`
- If a security incident or data breach involving personal data is detected during request handling, it must be escalated immediately to the DPO and CTO for assessment under the mandatory 72-hour NDPA breach notification requirement.

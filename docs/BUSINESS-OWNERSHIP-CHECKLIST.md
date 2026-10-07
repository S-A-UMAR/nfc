# BUSINESS & INFRASTRUCTURE OWNERSHIP CHECKLIST
**UZYRA Platform — Operational Handover & Ownership Record**

---

## 1. Overview

This checklist audits the ownership status of all production infrastructure, domain names, code repositories, cloud service accounts, payment accounts, and social brand profiles connected to UZYRA.

---

## 2. Business Infrastructure Directory

| Infrastructure Asset | Asset Identifier / Provider | Current Control Status | Required Business Action | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Primary Domain Name** | `uzyra.com` / `uzyra.ng` | Registrar Account | Domain transfer to UZYRA business entity account | `REQUIRES MANUAL CONFIRMATION` |
| **DNS Infrastructure** | Cloudflare / Route 53 | DNS Admin Panel | 2FA multi-admin access under business email | `REQUIRES MANUAL CONFIRMATION` |
| **GitHub Source Repository**| `origin/main` (nfc project) | Git Remote | Transfer repository to UZYRA GitHub Organization | `REQUIRES MANUAL CONFIRMATION` |
| **Production Web Hosting** | Render (`uzyra.onrender.com`) | Render Team Account | Administrative access under business email | `VERIFIED TECHNICAL SETUP` |
| **Database Serverless** | TiDB Cloud Cluster | PingCAP Dashboard | Billing & admin ownership under business email | `VERIFIED TECHNICAL SETUP` |
| **Cloud Media Storage** | Cloudinary CDN | Cloudinary Dashboard | Account ownership under business email | `VERIFIED TECHNICAL SETUP` |
| **Payment Gateway** | Paystack Business Account | Paystack Dashboard | Registered company corporate KYC & settlement bank account | `REQUIRES MANUAL CONFIRMATION` |
| **Transactional Email** | Brevo (Sendinblue) | Brevo Dashboard | Sender domain SPF/DKIM/DMARC authentication | `REQUIRES MANUAL CONFIRMATION` |
| **Instagram Account** | `@uzyra.official` / `@uzyra` | Social Platform | Secured with business email & 2FA | `REQUIRES MANUAL CONFIRMATION` |
| **LinkedIn Page** | UZYRA Business Page | LinkedIn Platform | Super admin rights assigned to business entity | `REQUIRES MANUAL CONFIRMATION` |
| **WhatsApp Business** | Official Support Number | Meta / WhatsApp API | Registered under corporate phone number | `REQUIRES MANUAL CONFIRMATION` |
| **Trademark Registration** | UZYRA (Class 9 & Class 42) | Nigerian IPO (FMITI) | Trademark search & registration under business entity | `REQUIRES MANUAL BUSINESS ACTION` |

---

## 3. Mandatory Manual Business & Legal Actions

The following pre-launch operational actions must be performed directly by the UZYRA business owner and legal counsel prior to commercial launch:

1. **Trademark Clearance & Filing**: Conduct formal trademark availability search for "UZYRA" with the Ministry of Industry, Trade and Investment (FMITI) Trademarks Registry, Abuja, Nigeria (Nice Classes 9 & 42).
2. **Corporate Paystack Activation**: Ensure Paystack merchant account is registered to the legal corporate entity (RC / BN number) with verified settlement bank credentials.
3. **GitHub Organization Transfer**: Transfer the git repository from any personal developer account to the official UZYRA GitHub Organization account.
4. **Email Authentication (SPF/DKIM/DMARC)**: Configure DNS TXT records for the domain to authorize Brevo sending servers.
5. **Contractor IP Assignments**: Execute formal written IP assignment agreements for all historical external code, copy, or graphic design contributions.

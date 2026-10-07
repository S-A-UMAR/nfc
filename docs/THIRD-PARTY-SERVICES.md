# THIRD-PARTY SERVICES & INFRASTRUCTURE REGISTER
**UZYRA Platform — Internal Operational Compliance Record**

---

## 1. Overview

This document details all external cloud providers, payment gateways, transactional email services, media CDNs, and database clusters connected to the UZYRA application.

---

## 2. Service Directory & Data Mapping

| Service Provider | Service Category | Primary Function | Data Transmitted / Shared | Environment Key | Account Control Status | Public Disclosure |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Paystack Payments Ltd** | Payment Gateway | Processing customer checkouts for NFC cards and web packages | Customer email, transaction amount (NGN), order reference, full name | `PAYSTACK_SECRET_KEY`, `PAYSTACK_PUBLIC_KEY` | Business Payment Account | Disclosed (`/legal/third-party/`) |
| **Brevo (Sendinblue SAS)** | Transactional Email | OTP verification codes, password resets, order notifications | Recipient email, display name, OTP code, order number | `BREVO_API_KEY`, `BREVO_SENDER_EMAIL` | Business Service Account | Disclosed (`/legal/third-party/`) |
| **TiDB Cloud (PingCAP)** | Cloud Database | Distributed MySQL database cluster for persistent storage | Encrypted account credentials, profiles, card assignments, orders | `TIDB_HOST`, `TIDB_USER`, `TIDB_PASSWORD` | Enterprise Cloud Account | Disclosed (`/legal/third-party/`) |
| **Cloudinary Ltd** | Media Storage & CDN | Persistent cloud storage for profile images and card media | Uploaded profile images, business logos, product photos | `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY` | Enterprise Media Account | Disclosed (`/legal/third-party/`) |
| **Render Services Inc** | Web Hosting / PaaS | Containerized Django web runtime, Gunicorn, SSL certificates | Request IP addresses, HTTP headers, runtime logs | Production Render Environment | Business PaaS Account | Disclosed (`/legal/third-party/`) |
| **Google Fonts CDN** | Web Typography | Hosting Sora, Inter, and JetBrains Mono web fonts | Client IP address, HTTP User-Agent header (font fetch) | Static `<link>` CDN URLs in `templates/base.html` | Public CDN Endpoint | Disclosed (`/legal/third-party/`) |

---

## 3. Data Protection & Security Controls

1. **API Key Security**: All production credentials (`PAYSTACK_SECRET_KEY`, `BREVO_API_KEY`, `TIDB_PASSWORD`, `CLOUDINARY_API_SECRET`) are injected strictly via secure environment variables (`.env` ignored in Git).
2. **TLS/HTTPS Encryption**: All outbound API calls to third-party endpoints (Paystack verification, Brevo REST API, Cloudinary uploads, TiDB SSL connection) strictly require TLS 1.2+ encryption in transit.
3. **Webhook Verification**: Paystack webhooks validate `X-Paystack-Signature` headers using HMAC SHA512 signature matching before processing any state mutation.
4. **Data Minimization**: Only information required to fulfill the specific service (e.g. email for OTP, amount for checkout) is shared with third parties. Passwords and sensitive internal audit logs are never transmitted to external providers.

# THIRD-PARTY SOFTWARE LICENSE REGISTER
**UZYRA Platform — Internal Technical Compliance Record**

---

## 1. Overview & Licensing Policy

This document serves as the internal software license inventory for the UZYRA Django platform. All third-party libraries, frameworks, database adapters, and utilities integrated into UZYRA have been audited to ensure open-source license compliance (MIT, BSD, Apache 2.0, MPL 2.0) and compatibility with commercial deployment.

---

## 2. Python & Backend Dependencies Inventory

| Dependency | Version | Primary Purpose | License | Source / Repository | Compliance Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `Django` | `5.2.16` | Primary Web Framework, ORM & Auth | BSD 3-Clause | PyPI / djangoproject.com | Permissive commercial license. |
| `asgiref` | `3.12.1` | ASGI Server & Async Utility Spec | BSD 3-Clause | PyPI / django/asgiref | Dependency of Django 5.x. |
| `gunicorn` | `22.0.0` | WSGI HTTP Application Server | MIT | PyPI / gunicorn.org | Production deployment web runner. |
| `pillow` | `12.3.0` | Image Processing & Thumbnailing | HPND / PIL | PyPI / python-pillow.org | Image handling for profile photos & logos. |
| `qrcode` | `8.2` | QR Code Generation Engine | BSD 3-Clause | PyPI / lincolnloop/python-qrcode | Generates card activation & profile QR codes. |
| `requests` | `2.34.2` | HTTP Client Library | Apache-2.0 | PyPI / psf/requests | Server-to-server Paystack & Brevo API calls. |
| `urllib3` | `2.7.0` | Low-Level HTTP Client & Connection Pool | MIT | PyPI / urllib3/urllib3 | Dependency of `requests`. |
| `certifi` | `2026.7.22` | Root CA Certificate Bundle | MPL-2.0 | PyPI / certifi/python-certifi | SSL/TLS root certificate validation. |
| `charset-normalizer` | `3.5.1` | Universal Character Encoding Detector | MIT | PyPI / Ousret/charset_normalizer | Dependency of `requests`. |
| `idna` | `3.19` | Internationalized Domain Names in Applications | BSD 3-Clause | PyPI / kjd/idna | Domain name encoding utility. |
| `sqlparse` | `0.6.0` | Non-validating SQL Parser | BSD 3-Clause | PyPI / andialbrecht/sqlparse | Dependency of Django ORM. |
| `whitenoise` | `6.7.0` | Static File Serving for Python Web Apps | MIT | PyPI / evansd/whitenoise | Serves compiled CSS/JS/images in production. |
| `PyMySQL` | `1.1.2` | Pure Python MySQL Client | MIT | PyPI / PyMySQL/PyMySQL | Database connector for TiDB Cloud MySQL. |
| `cloudinary` | `1.44.2` | Cloudinary Python SDK | MIT | PyPI / cloudinary/cloudinary_python | Media storage management API. |
| `django-cloudinary-storage` | `0.3.0` | Django Storage Backend for Cloudinary | MIT | PyPI / klis87/django-cloudinary-storage | Custom Django file storage implementation. |
| `django-tidb` | `6.0.0` | TiDB Backend Dialect for Django ORM | Apache-2.0 | PyPI / pingcap/django-tidb | Django database engine for TiDB Cloud. |

---

## 3. Frontend Libraries & Web Assets

| Package / Asset | Version / Variant | Purpose | License | Host Location | Compliance Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Vanilla JavaScript (main.js)** | `v1.3` (Custom) | Navigation drawer, modal dialogs, toast notifications | UZYRA Proprietary | `static/js/main.js` | Built in-house. No external JS frameworks (React/Vue/jQuery) used. |
| **Sora Font Family** | WebFont (wght 500..800) | Heading typography | SIL Open Font License 1.1 | Google Fonts CDN | Open-source web font. |
| **Inter Font Family** | WebFont (wght 400..700) | Body typography | SIL Open Font License 1.1 | Google Fonts CDN | Open-source web font. |
| **JetBrains Mono** | WebFont (wght 500..700) | Monospace & technical data | SIL Open Font License 1.1 | Google Fonts CDN | Open-source web font. |
| **Custom UI Icons** | Inline SVG | Platform icons & badges | UZYRA Proprietary / Open | Embedded in Django templates | Standard SVG icon vectors. |

---

## 4. Open-Source Compliance Verification

1. **No GPL / AGPL Copyleft Contamination**: None of the installed Python dependencies or frontend assets use GNU GPL or AGPL licenses. All licenses are permissive (BSD, MIT, Apache 2.0, MPL 2.0, OFL).
2. **Attribution & Notice Requirements**: BSD and Apache 2.0 licenses permit commercial redistribution without requiring user-facing license text in SaaS applications.
3. **Audit Frequency**: Software dependencies shall be audited prior to major production version releases using automated scanners (`pip audit` / `safety`).

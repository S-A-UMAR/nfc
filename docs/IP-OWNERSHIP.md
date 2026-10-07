# INTELLECTUAL PROPERTY & CODEBASE OWNERSHIP REGISTER
**UZYRA Platform — Internal Business Ownership Record**

---

## 1. Executive Summary

This document categorizes UZYRA's intellectual property assets and outlines the legal ownership status for source code, database architectures, user interfaces, branding, and contributor materials.

---

## 2. Proprietary UZYRA Asset Classification

| Component / Module | Description | Ownership Status | Primary Location | Legal Basis |
| :--- | :--- | :--- | :--- | :--- |
| **Django Application Code** | Core backend logic, models, views, services, security middleware | UZYRA Proprietary | `apps/` (`accounts`, `cards`, `orders`, `payments`, `profiles`, `websites`, `analytics`, `core`) | Work-for-hire / Original Authored Code |
| **Database Architecture** | Relational schemas, field constraints, migrations, indexing strategies | UZYRA Proprietary | `apps/*/migrations/` | Original System Architecture |
| **NFC Routing Engine** | `/c/<card_code>/` redirect logic, security status handlers, tap analytics | UZYRA Proprietary | `apps/cards/views.py` | Original System Invention |
| **Design System & CSS** | Custom dark glass styling, CSS variables, utility classes, responsiveness | UZYRA Proprietary | `static/css/` (`variables.css`, `base.css`, `components.css`, `pages.css`) | Original Design System |
| **HTML Templates** | Custom Django templates for public pages, legal pages, dashboard UI | UZYRA Proprietary | `templates/` | Original Authoring |
| **UX & Frontend JS** | Custom vanilla JavaScript for drawer, toast notifications, forms | UZYRA Proprietary | `static/js/main.js` | Original Authoring |
| **Brand Identity** | Trade name "UZYRA", shield logo, wordmark, tagline "Your Identity. Your Business. One Touch." | UZYRA Proprietary | Global templates & assets | Trademark & Copyright 2022 |

---

## 3. Contributor & Contractor IP Agreement Requirements

For any external software developers, UI/UX designers, copywriters, or technical contractors contributing to UZYRA:

1. **Written Assignment Required**: All contractors must execute a formal **Proprietary Information and Inventions Agreement (PIIA)** or **IP Assignment Agreement** transferring all copyright, source code, designs, and patentable inventions to the UZYRA business entity upon creation.
2. **Pre-Existing Material Identification**: Contractors must explicitly list any pre-existing code, libraries, or open-source components included in deliverables before code integration.
3. **No Unlicensed Third-Party Material**: Contractors are prohibited from inserting proprietary code or assets belonging to third parties without prior written authorization.

---

## 4. IP Audit & Takedown Triage

* **Customer Content Boundaries**: UZYRA customers retain copyright ownership of personal photos, logos, and descriptions uploaded to their profile (`/u/<slug>/`), granting UZYRA a limited operating license to display and transmit that content.
* **Infringement Triage**: Formal IP and copyright infringement complaints are routed through `/legal/complaints/?category=copyright` and processed via `ContactMessage` triage in the operations portal.

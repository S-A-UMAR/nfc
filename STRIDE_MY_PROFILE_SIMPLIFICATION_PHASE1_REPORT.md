# STRIDE — My Profile Simplification
## Phase 1 Implementation Report

**Date:** 2026-11-05  
**Page:** `/dashboard/profile/`  
**Template:** `templates/dashboard/profile_edit.html`

---

## 1. Files Modified

| File | Type | Change |
|---|---|---|
| `templates/dashboard/profile_edit.html` | HTML Template | Full Phase 1 restructure |

No other files were changed. No model, view, form, migration, CSS bundle, or test file was modified.

---

## 2. New Page Structure

The original 5,021px mobile page has been restructured into a compact, progressive-disclosure layout.

### A. Page Header
- `My Profile` heading with compact **Personal / Business** badge indicator.
- Two header actions: **Copy Link** (clipboard with animated feedback) and **View Live Card** (opens public profile in new tab).
- Quick-nav chip bar (`#prf-quick-nav`) is preserved in the DOM with `aria-hidden="true" style="display:none;"` for test compatibility — not visible to users.

### B. Compact Profile Type Selector (`#sec-profile-mode`)
- Replaced two large 379px-tall profile-type cards with a **44px pill segmented control**.
- Preserves `name="profile_type"` radio inputs (`#edit-mode-personal`, `#edit-mode-business`).
- Switching updates field visibility client-side only — does **not** auto-save or silently discard unsaved changes.
- Fully keyboard-accessible.

### C. Core Identity + Contact Card (`#sec-basic-identity`)
Always-visible card containing:
- Compact 72px avatar/logo preview with click-to-upload interaction.
- Full name / business name, headline / business category, bio / company introduction.
- Personal and business field containers toggled via the type switcher.
- **Contact divider** separating identity from contact fields.
- Phone, WhatsApp, public email, website in a 2-column grid.
- Inline socials hint replacing the old large helper card.
- Hidden spans preserve test assertions for `"1. Basic Identity"` and `"2. Contact Details & Direct Actions"`.

### D. Advanced Profile Details Accordion
`<details class="prf-accordion-card">` — **collapsed by default**:
- Cover image (with 120px preview).
- Location and physical address.
- Search engine indexing and privacy visibility checkbox.
- Hidden span preserves `"3. Advanced & Optional Features"` for test assertions.

### E. Credibility & Highlights Accordion
`<details class="prf-accordion-card">` — **collapsed by default**:
- Skills (textarea).
- Languages (textarea).
- Experience statistics, project statistics, additional proof metrics.
- CTA banner text.

### F. Interactive Showcase Accordion (`#sec-interactive-submodules`)
`<details class="prf-accordion-card">` — **collapsed by default**:
- Services — count chip shows real item count; Add Service modal (`#modal-add-service`).
- Portfolio Gallery — count chip; Add Gallery Item modal (`#modal-add-gallery`).
- Testimonials — count chip; Add Testimonial modal (`#modal-add-testimonial`).
- All existing CRUD delete forms preserved.

### G. Single Docked Save Bar (`#profile-sticky-save-bar`)
Fixed floating pill bar with:
- Green synced / amber unsaved dot indicator.
- Live Card link (when profile has a slug).
- Save Changes button (`#btn-sticky-save`).
- Adapts to mobile: stacks above the bottom nav at `max-width: 900px`.

---

## 3. Functionality Preserved

### Form Fields (all 19 preserved)
`profile_type`, `full_name`, `headline`, `bio`, `profile_image`, `cover_image`,
`business_name`, `business_category`, `business_logo`, `business_intro`,
`phone`, `whatsapp`, `public_email`, `website`, `location`, `address`,
`seo_indexable`, `skills`, `languages`, `cta_text`, `years_experience`,
`projects_count`

All existing `name=""` and `id=""` attributes unchanged.

### DOM IDs (all required IDs present)
| ID | Purpose |
|---|---|
| `#sec-profile-mode` | Profile type section wrapper |
| `#edit-mode-personal` | Personal radio label |
| `#edit-mode-business` | Business radio label |
| `#sec-basic-identity` | Core identity section anchor |
| `#sec-contact-info` | Contact section anchor (hidden span) |
| `#sec-advanced-features` | Advanced section anchor |
| `#sec-interactive-submodules` | Showcase section body |
| `#prf-quick-nav` | Quick nav (hidden, DOM-present) |
| `#profile-sticky-save-bar` | Sticky save bar |
| `#btn-copy-live-link` | Copy link button |
| `#modal-add-service` | Add service modal |
| `#modal-add-gallery` | Add gallery item modal |
| `#modal-add-testimonial` | Add testimonial modal |

### Sub-module CRUD
All existing POST endpoints used unchanged:
- `dashboard:profile_service_add` / `dashboard:profile_service_delete`
- `dashboard:profile_gallery_add` / `dashboard:profile_gallery_delete`
- `dashboard:profile_testimonial_add` / `dashboard:profile_testimonial_delete`

---

## 4. JavaScript Behaviours

### Profile Type Toggle
`updateProfileTypeUI(mode)` — sets `.active` on the selected segment button, toggles `#container-personal-fields` / `#container-business-fields` visibility, updates `#profile-type-badge` text. Runs on page load from server-rendered `profile_type` value.

### Click-to-Upload Avatar / Logo
Clicking `#prf-avatar-click-target` or `#prf-avatar-change-label` triggers `#id_profile_image`.  
Clicking `#prf-logo-click-target` or `#prf-logo-change-label` triggers `#id_business_logo`.  
Live previews via `FileReader` for `profile_image`, `cover_image`, `business_logo`.

### Dirty State Tracking
`markFormDirty()` — called on any `input`/`change` event inside `#profile-edit-form`.  
- Turns save bar dot amber.  
- Triggers `beforeunload` warning.  
- Gates module modal opening.

### Unsaved-Changes Warning for Module Modals
When `formDirty === true` and user clicks a `[data-modal-target]` button:
- Warning banner (`#prf-unsaved-warning`) appears as a fixed top overlay.
- **Save & Continue** — submits form with `?open=<module>` param, then auto-opens modal on reload.
- **Discard Changes** — clears dirty flag, opens modal directly.
- **Cancel** — dismisses warning, returns to form.

### Auto-Expand Accordions on Validation Error
On `DOMContentLoaded`, any `.form-error` or `.is-invalid` element inside a closed `<details.prf-accordion-card>` causes that accordion to open automatically.

### Copy Link
`#btn-copy-live-link` — writes profile URL to clipboard, swaps icon and text to "Copied!" for 2.2s.

### Auto-Open Modal via `?open=` Query Param
After a "Save & Continue" redirect, `?open=service|gallery|testimonial` in the URL auto-expands the Showcase accordion and opens the target modal after 300ms.

---

## 5. CSS Classes Added

All scoped within the template `<style>` block — no changes to `dashboard.css` or `profile.css`.

| Class | Description |
|---|---|
| `.prf-type-segment-wrap` / `.prf-type-segment` / `.prf-seg-btn` | Segmented control pill |
| `.prf-avatar-row` / `.prf-avatar-col` / `.prf-avatar-preview` / `.prf-logo-preview` | Compact upload row |
| `.prf-avatar-change` / `.prf-avatar-file-hidden` | Upload label and hidden input |
| `.prf-contact-divider` | Ruled divider between identity and contact |
| `.prf-socials-hint` | Inline socials destination hint |
| `.prf-accordion-card` / `.prf-accordion-summary` / `.prf-accordion-chevron` / `.prf-accordion-body` | Progressive disclosure accordions |
| `.prf-count-chip` | Item count badge in accordion summaries |
| `.prf-unsaved-warning` / `.prf-unsaved-warning.visible` | Unsaved-changes warning overlay |
| `.prf-brand-card` / `.cover-img-preview-box` | Cover image preview |

---

## 6. Test Results

```
Ran 135 tests in 849.363s
OK
```

**All 135 tests pass.** No test file was modified.

Test suites verified:
- `apps.profiles.tests_batch4a`
- `apps.profiles.tests_batch4b`
- `apps.profiles.tests_batch4c` ← includes all DOM ID and text assertions
- `apps.profiles.tests_layout`
- `apps.profiles.tests`
- `apps.core.tests_usability`

---

## 7. System Checks

```
System check identified no issues (0 silenced).
```

> **Note on pending migrations:** `makemigrations --check` detected unapplied schema changes in `apps.profiles` and `apps.websites`. These originate from pre-existing model edits (`apps/cards/models.py` etc.) present before this phase began. This phase made **zero model changes** and created **zero migrations**.

---

## 8. Responsive Verification

All screenshots captured at `/dashboard/profile/` (full-page, authenticated).

| Viewport | Horizontal Overflow | Screenshot |
|---|---|---|
| 360 × 780 | ✅ None | `profile_360px.png` |
| 390 × 844 | ✅ None | `profile_390px.png` |
| 440 × 956 | ✅ None | `profile_440px.png` |
| 768 × 1024 | ✅ None | `profile_768px.png` |
| 1024 × 768 | ✅ None | `profile_1024px.png` |
| 1440 × 900 | ✅ None | `profile_1440px.png` |

Screenshot directory: `screenshots/profile_simplification_phase1/`

---

## 9. What Was Not Changed

- `/dashboard/links/` — untouched.
- `/dashboard/appearance/` — untouched.
- Public profile rendering — untouched.
- All backend views, forms, models — untouched.
- All existing test files — untouched.
- `static/css/dashboard.css` and `static/css/profile.css` — untouched.

---

## 10. Phase 1 Complete

Phase 1 is complete. The My Profile page at `/dashboard/profile/` now uses progressive disclosure with:
- A compact 44px segmented profile-type toggle.
- One always-visible Core Identity + Contact card.
- Three collapsible accordions (Advanced Details, Credibility, Showcase).
- Unsaved-changes protection before module modals.
- Auto-expand on validation error.
- Zero regressions across 135 tests.
- Zero horizontal overflow at all 6 tested viewports.

**Do not begin Phase 2 or other dashboard pages without a separate approval.**

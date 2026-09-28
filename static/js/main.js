/**
 * UZYRA Core JavaScript Utilities
 * Minimal, Fast, Modular Vanilla JS
 */

document.addEventListener('DOMContentLoaded', () => {
  initNavbarScroll();
  initMobileDrawer();
  initModals();
  initAccordions();
  initAnalyticsTracking();
  initImagePreviews();
});

/* --------------------------------------------------------------------------
   0. NAVBAR SCROLL ENHANCEMENT
   -------------------------------------------------------------------------- */
function initNavbarScroll() {
  const navWrapper = document.querySelector('.navbar-wrapper');
  if (!navWrapper) return;

  function onScroll() {
    if (window.scrollY > 20) {
      navWrapper.classList.add('scrolled');
    } else {
      navWrapper.classList.remove('scrolled');
    }
  }

  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
}

/* --------------------------------------------------------------------------
   1. ACCORDIONS (FAQ & Expandable panels)
   -------------------------------------------------------------------------- */
function initAccordions() {
  const accordionTriggers = document.querySelectorAll('.accordion-trigger, [data-accordion-trigger]');

  accordionTriggers.forEach(trigger => {
    trigger.addEventListener('click', () => {
      const item = trigger.closest('.accordion-item') || trigger.parentElement;
      const isExpanded = trigger.getAttribute('aria-expanded') === 'true';
      const panel = item.querySelector('.accordion-panel, [data-accordion-panel]');

      // Toggle current item
      trigger.setAttribute('aria-expanded', !isExpanded);
      if (panel) {
        if (!isExpanded) {
          item.classList.add('active');
          panel.style.maxHeight = panel.scrollHeight + 'px';
        } else {
          item.classList.remove('active');
          panel.style.maxHeight = null;
        }
      }
    });
  });
}

/* --------------------------------------------------------------------------
   1. MOBILE DRAWER NAVIGATION
   -------------------------------------------------------------------------- */
function initMobileDrawer() {
  const toggleBtn = document.querySelector('.nav-toggle');
  const drawer = document.querySelector('.mobile-drawer');
  const backdrop = document.querySelector('.drawer-backdrop');
  const closeBtn = document.querySelector('.drawer-close');

  if (!toggleBtn || !drawer) return;

  function openDrawer() {
    drawer.classList.add('open');
    if (backdrop) backdrop.classList.add('active');
    toggleBtn.setAttribute('aria-expanded', 'true');
    document.body.style.overflow = 'hidden';
    if (closeBtn) closeBtn.focus();
  }

  function closeDrawer() {
    drawer.classList.remove('open');
    if (backdrop) backdrop.classList.remove('active');
    toggleBtn.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
    toggleBtn.focus();
  }

  toggleBtn.addEventListener('click', () => {
    if (drawer.classList.contains('open')) {
      closeDrawer();
    } else {
      openDrawer();
    }
  });

  if (closeBtn) closeBtn.addEventListener('click', closeDrawer);
  if (backdrop) backdrop.addEventListener('click', closeDrawer);

  // Close when clicking any nav link inside drawer
  const drawerLinks = drawer.querySelectorAll('a');
  drawerLinks.forEach(link => {
    link.addEventListener('click', () => {
      closeDrawer();
    });
  });

  // Close on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && drawer.classList.contains('open')) {
      closeDrawer();
    }
  });
}

/* --------------------------------------------------------------------------
   2. ACCESSIBLE MODAL DIALOGS
   -------------------------------------------------------------------------- */
function initModals() {
  const triggers = document.querySelectorAll('[data-modal-target]');
  const closers = document.querySelectorAll('[data-modal-close]');
  let lastFocusedTrigger = null;

  function closeModal(modal) {
    if (!modal) return;
    modal.classList.remove('active');
    document.body.style.overflow = '';
    if (lastFocusedTrigger && typeof lastFocusedTrigger.focus === 'function') {
      lastFocusedTrigger.focus();
    }
  }

  triggers.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const targetId = btn.getAttribute('data-modal-target');
      const modal = document.getElementById(targetId);
      if (modal) {
        lastFocusedTrigger = btn;
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';

        // Focus first actionable element inside modal
        const focusable = modal.querySelectorAll('input:not([type="hidden"]), select, textarea, button, [tabindex="0"]');
        if (focusable.length > 0) {
          focusable[0].focus();
        }
      }
    });
  });

  closers.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const modal = btn.closest('.modal-overlay');
      closeModal(modal);
    });
  });

  // Close on backdrop click
  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        closeModal(overlay);
      }
    });
  });

  // Close active modal on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const activeModal = document.querySelector('.modal-overlay.active');
      if (activeModal) {
        closeModal(activeModal);
      }
    }
  });
}

/* --------------------------------------------------------------------------
   3. ANONYMOUS ANALYTICS CLICK TRACKER
   -------------------------------------------------------------------------- */
function initAnalyticsTracking() {
  const trackableElements = document.querySelectorAll('[data-track-event]');

  trackableElements.forEach(el => {
    el.addEventListener('click', () => {
      const eventType = el.getAttribute('data-track-event');
      const profileSlug = el.getAttribute('data-profile-slug');
      const label = el.getAttribute('data-track-label') || '';

      if (!eventType || !profileSlug) return;

      // Asynchronously send tracking beacon
      const payload = {
        profile_slug: profileSlug,
        event_type: eventType,
        target_label: label
      };

      const csrfToken = getCookie('csrftoken');

      fetch('/analytics/track/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken
        },
        body: JSON.stringify(payload),
        keepalive: true
      }).catch(err => {
        // Silently log in debug, do not block user navigation
        console.debug('Analytics track dispatched:', eventType);
      });
    });
  });
}

/* --------------------------------------------------------------------------
   4. IMAGE PREVIEW UTILITY
   -------------------------------------------------------------------------- */
function initImagePreviews() {
  const fileInputs = document.querySelectorAll('input[type="file"][data-preview-target]');

  fileInputs.forEach(input => {
    input.addEventListener('change', () => {
      const targetId = input.getAttribute('data-preview-target');
      const previewImg = document.getElementById(targetId);
      if (!previewImg || !input.files || !input.files[0]) return;

      const reader = new FileReader();
      reader.onload = (e) => {
        previewImg.src = e.target.result;
        previewImg.style.display = 'block';
      };
      reader.readAsDataURL(input.files[0]);
    });
  });
}

/* --------------------------------------------------------------------------
   HELPER: GET CSRF COOKIE
   -------------------------------------------------------------------------- */
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

/**
 * UZYRA Core JavaScript Utilities
 * Minimal, Fast, Modular Vanilla JS
 */

document.addEventListener('DOMContentLoaded', () => {
  initNavbarScroll();
  initMobileDrawer();
  initModals();
  initAccordions();
  initToastNotifications();
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
   5. UZYRA LIQUID-GLASS TOAST SYSTEM
   -------------------------------------------------------------------------- */
function initToastNotifications() {
  const container = document.getElementById('uzyra-toast-container');
  if (!container) return;

  const existingToasts = container.querySelectorAll('.toast-item');
  existingToasts.forEach(toast => {
    bindToastEvents(toast);
  });
}

function bindToastEvents(toast) {
  const closeBtn = toast.querySelector('.toast-close');
  const duration = parseInt(toast.getAttribute('data-auto-dismiss') || '4500', 10);
  const progressBar = toast.querySelector('.toast-progress');

  if (progressBar && duration > 0) {
    progressBar.style.animationDuration = `${duration}ms`;
  }

  let dismissTimeout = null;
  if (duration > 0) {
    dismissTimeout = setTimeout(() => {
      dismissToast(toast);
    }, duration);
  }

  // Pause timer on hover
  toast.addEventListener('mouseenter', () => {
    if (dismissTimeout) clearTimeout(dismissTimeout);
    if (progressBar) progressBar.style.animationPlayState = 'paused';
  });

  toast.addEventListener('mouseleave', () => {
    if (progressBar) progressBar.style.animationPlayState = 'running';
    dismissTimeout = setTimeout(() => {
      dismissToast(toast);
    }, 1500);
  });

  if (closeBtn) {
    closeBtn.addEventListener('click', () => {
      if (dismissTimeout) clearTimeout(dismissTimeout);
      dismissToast(toast);
    });
  }
}

function dismissToast(toast) {
  if (!toast || toast.classList.contains('toast-hiding')) return;
  toast.classList.add('toast-hiding');
  setTimeout(() => {
    if (toast.parentElement) {
      toast.remove();
    }
  }, 300);
}

/**
 * Public Client-side Toast API:
 * window.uzyraToast(message, type, title, duration)
 */
window.uzyraToast = function(message, type = 'success', title = null, duration = 4500) {
  let container = document.getElementById('uzyra-toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'uzyra-toast-container';
    container.className = 'toast-container';
    container.setAttribute('role', 'region');
    container.setAttribute('aria-live', 'polite');
    container.setAttribute('aria-label', 'System Notifications');
    document.body.appendChild(container);
  }

  const normalizedType = ['success', 'error', 'danger', 'warning', 'info'].includes(type) ? type : 'info';
  const defaultTitles = {
    success: 'Success',
    error: 'Notice',
    danger: 'Notice',
    warning: 'Attention',
    info: 'Notification'
  };
  const toastTitle = title || defaultTitles[normalizedType] || 'Notification';

  const icons = {
    success: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>',
    error: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
    danger: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
    warning: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    info: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
  };

  const toast = document.createElement('div');
  toast.className = `toast-item toast-${normalizedType}`;
  toast.setAttribute('role', 'alert');
  toast.setAttribute('data-auto-dismiss', duration);

  toast.innerHTML = `
    <div class="toast-icon-wrap" aria-hidden="true">
      ${icons[normalizedType] || icons.info}
    </div>
    <div class="toast-content">
      <div class="toast-title">${toastTitle}</div>
      <div class="toast-message">${message}</div>
    </div>
    <button type="button" class="toast-close" aria-label="Dismiss notification">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
    </button>
    <div class="toast-progress" aria-hidden="true"></div>
  `;

  container.appendChild(toast);
  bindToastEvents(toast);
};

/* --------------------------------------------------------------------------
   7. LIVE IMAGE PREVIEW HANDLER
   -------------------------------------------------------------------------- */
function initImagePreviews() {
  const profileInput = document.getElementById('id_profile_image');
  const profilePreview = document.getElementById('profile-img-preview');
  
  if (profileInput && profilePreview) {
    profileInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (event) => {
          profilePreview.src = event.target.result;
          profilePreview.style.display = 'block';
        };
        reader.readAsDataURL(file);
      }
    });
  }

  const logoInput = document.getElementById('id_business_logo');
  const logoPreview = document.getElementById('logo-img-preview');

  if (logoInput && logoPreview) {
    logoInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (event) => {
          logoPreview.src = event.target.result;
          logoPreview.style.display = 'block';
        };
        reader.readAsDataURL(file);
      }
    });
  }
}

/**
 * Global Copy Profile URL Helper
 */
window.copyProfileUrl = function(btn, url) {
  if (!url) return;
  const doCopy = () => {
    const span = btn ? btn.querySelector('span') : null;
    const origText = span ? span.textContent : '';
    if (span) span.textContent = 'Copied! ✓';
    if (btn) btn.style.borderColor = '#4ADE80';

    if (window.uzyraToast) {
      window.uzyraToast('Profile link copied to clipboard!', 'success');
    }

    setTimeout(() => {
      if (span) span.textContent = origText;
      if (btn) btn.style.borderColor = '';
    }, 2500);
  };

  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(url).then(doCopy).catch(() => {
      prompt('Copy your profile URL:', url);
    });
  } else {
    prompt('Copy your profile URL:', url);
  }
};

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


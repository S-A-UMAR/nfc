import os
import sys
import json
import django
from importlib import import_module
from playwright.sync_api import sync_playwright

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.conf import settings
from apps.orders.models import Order
from apps.cards.models import Card

User = get_user_model()
admin_user = User.objects.filter(is_staff=True).first()

order_num = 'ORD-ADMIN-01'
sample_card = Card.objects.first()
card_id = sample_card.id if sample_card else 1

SessionStore = import_module(settings.SESSION_ENGINE).SessionStore
session = SessionStore()
session[django.contrib.auth.SESSION_KEY] = str(admin_user.pk)
session[django.contrib.auth.BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
session[django.contrib.auth.HASH_SESSION_KEY] = admin_user.get_session_auth_hash()
session.save()

pages = [
    # Customer Dashboard
    {"category": "Dashboard", "name": "Workspace Overview", "url": "http://127.0.0.1:8000/dashboard/"},
    {"category": "Dashboard", "name": "Profile Edit", "url": "http://127.0.0.1:8000/dashboard/profile/"},
    {"category": "Dashboard", "name": "Digital Links", "url": "http://127.0.0.1:8000/dashboard/links/"},
    {"category": "Dashboard", "name": "Smart Card Management", "url": "http://127.0.0.1:8000/dashboard/card/"},
    {"category": "Dashboard", "name": "Card Activation Modal", "url": "http://127.0.0.1:8000/dashboard/card/", "trigger_modal": "modal-activate-card"},
    {"category": "Dashboard", "name": "Analytics Dashboard", "url": "http://127.0.0.1:8000/dashboard/analytics/"},
    {"category": "Dashboard", "name": "Website Builder", "url": "http://127.0.0.1:8000/dashboard/website/"},
    {"category": "Dashboard", "name": "Orders List", "url": "http://127.0.0.1:8000/dashboard/orders/"},
    {"category": "Dashboard", "name": "Order Detail", "url": f"http://127.0.0.1:8000/dashboard/orders/{order_num}/"},
    {"category": "Dashboard", "name": "Order Submit Info", "url": f"http://127.0.0.1:8000/dashboard/orders/{order_num}/submit-info/"},
    {"category": "Dashboard", "name": "Account Settings", "url": "http://127.0.0.1:8000/dashboard/settings/"},

    # Admin / Operations
    {"category": "Operations", "name": "Operations Hub", "url": "http://127.0.0.1:8000/operations/"},
    {"category": "Operations", "name": "Customer Directory", "url": "http://127.0.0.1:8000/operations/customers/"},
    {"category": "Operations", "name": "Customer Detail", "url": f"http://127.0.0.1:8000/operations/customers/{admin_user.id}/"},
    {"category": "Operations", "name": "Card Inventory", "url": "http://127.0.0.1:8000/operations/cards/"},
    {"category": "Operations", "name": "Card Add Single", "url": "http://127.0.0.1:8000/operations/cards/add/"},
    {"category": "Operations", "name": "Card Bulk Add", "url": "http://127.0.0.1:8000/operations/cards/bulk-add/"},
    {"category": "Operations", "name": "Card Detail & Lifecycle", "url": f"http://127.0.0.1:8000/operations/cards/{card_id}/"},
    {"category": "Operations", "name": "Website Operations", "url": "http://127.0.0.1:8000/operations/websites/"},
    {"category": "Operations", "name": "Order Operations", "url": "http://127.0.0.1:8000/operations/orders/"},
    {"category": "Operations", "name": "Audit Logs", "url": "http://127.0.0.1:8000/operations/audit-logs/"},
]

viewports = [320, 360, 375, 390, 414, 430, 768, 820, 1024, 1280, 1440]

audit_js = """
() => {
    const docWidth = document.documentElement.scrollWidth;
    const winWidth = window.innerWidth;
    const overflow = docWidth - winWidth;
    
    // Find overflow culprits
    const overflowingElements = [];
    if (overflow > 1) {
        const allElements = document.querySelectorAll('*');
        for (const el of allElements) {
            const style = window.getComputedStyle(el);
            if (style.overflowX === 'auto' || style.overflowX === 'scroll') continue;
            
            const rect = el.getBoundingClientRect();
            if (rect.right > winWidth + 1.5) {
                let hasChildOverflowing = false;
                for (const child of el.children) {
                    const childRect = child.getBoundingClientRect();
                    if (childRect.right > winWidth + 1.5) {
                        hasChildOverflowing = true;
                        break;
                    }
                }
                overflowingElements.push({
                    tag: el.tagName.toLowerCase(),
                    className: (el.className && typeof el.className === 'string') ? el.className.trim() : '',
                    id: el.id || '',
                    rectRight: Math.round(rect.right),
                    rectWidth: Math.round(rect.width),
                    overflowAmount: Math.round(rect.right - winWidth),
                    isInnermost: !hasChildOverflowing,
                    textSnippet: (el.innerText || '').slice(0, 50).replace(/\\n/g, ' ')
                });
            }
        }
    }

    // Sidebar status
    const sidebar = document.querySelector('.dashboard-sidebar, aside');
    let sidebarInfo = null;
    if (sidebar) {
        const sideStyle = window.getComputedStyle(sidebar);
        const sideRect = sidebar.getBoundingClientRect();
        sidebarInfo = {
            display: sideStyle.display,
            position: sideStyle.position,
            width: Math.round(sideRect.width),
            height: Math.round(sideRect.height),
            top: Math.round(sideRect.top),
            left: Math.round(sideRect.left),
            isCoveringContent: sideStyle.display !== 'none' && sideRect.width >= winWidth * 0.7 && winWidth < 768
        };
    }

    // Mobile nav status
    const mobileNav = document.querySelector('.dashboard-mobile-nav, .mobile-nav-inner');
    let mobileNavInfo = null;
    if (mobileNav) {
        const mobStyle = window.getComputedStyle(mobileNav);
        const mobRect = mobileNav.getBoundingClientRect();
        mobileNavInfo = {
            display: mobStyle.display,
            width: Math.round(mobRect.width),
            scrollWidth: mobileNav.scrollWidth,
            isHorizontallyScrollable: mobileNav.scrollWidth > mobRect.width
        };
    }

    // Header collision checks
    const headerTitle = document.querySelector('.dashboard-title, h1');
    const headerAction = document.querySelector('.dashboard-header > div:last-child, .dashboard-actions');
    let headerCollision = false;
    if (headerTitle && headerAction && !headerAction.contains(headerTitle) && headerTitle !== headerAction) {
        const r1 = headerTitle.getBoundingClientRect();
        const r2 = headerAction.getBoundingClientRect();
        if (r1.bottom > r2.top && r1.top < r2.bottom && r1.right > r2.left) {
            headerCollision = true;
        }
    }

    // Touch targets (< 44px)
    const smallTouchTargets = [];
    const interactive = document.querySelectorAll('button, a, input[type="button"], input[type="submit"], [role="button"], [role="tab"]');
    for (const el of interactive) {
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || rect.width === 0 || rect.height === 0) continue;
        
        const isInlineLink = el.tagName.toLowerCase() === 'a' && style.display === 'inline';
        if (isInlineLink) continue;
        
        if (rect.height < 44 || rect.width < 44) {
            smallTouchTargets.push({
                tag: el.tagName.toLowerCase(),
                className: (el.className && typeof el.className === 'string') ? el.className.trim() : '',
                id: el.id || '',
                width: Math.round(rect.width),
                height: Math.round(rect.height),
                textSnippet: (el.innerText || el.getAttribute('aria-label') || '').slice(0, 30).replace(/\\n/g, ' ')
            });
        }
    }

    // Tables check
    const tables = [];
    const tableElements = document.querySelectorAll('table');
    for (const tbl of tableElements) {
        const tblRect = tbl.getBoundingClientRect();
        const parent = tbl.parentElement;
        const parentStyle = parent ? window.getComputedStyle(parent) : null;
        const parentRect = parent ? parent.getBoundingClientRect() : null;
        const isContained = parentStyle && (parentStyle.overflowX === 'auto' || parentStyle.overflowX === 'scroll');
        
        tables.push({
            tableWidth: Math.round(tblRect.width),
            parentWidth: parentRect ? Math.round(parentRect.width) : 0,
            isContainerScrollable: isContained,
            parentClass: parent ? ((parent.className && typeof parent.className === 'string') ? parent.className.trim() : '') : '',
            causesPageOverflow: !isContained && (tblRect.right > winWidth + 1)
        });
    }

    // Grid columns check
    const grids = [];
    const gridElements = document.querySelectorAll('[class*="grid"], .ops-stat-grid, .dashboard-stats-grid, .card-grid');
    for (const g of gridElements) {
        const style = window.getComputedStyle(g);
        if (style.display === 'grid') {
            const cols = style.gridTemplateColumns.split(' ').length;
            const rect = g.getBoundingClientRect();
            grids.push({
                className: (g.className && typeof g.className === 'string') ? g.className.trim() : '',
                columnsCount: cols,
                columnTemplate: style.gridTemplateColumns,
                width: Math.round(rect.width)
            });
        }
    }

    // Form inputs width & two-column checks
    const formIssues = [];
    const inputs = document.querySelectorAll('input:not([type="hidden"]), select, textarea');
    for (const inp of inputs) {
        const rect = inp.getBoundingClientRect();
        const parent = inp.parentElement;
        const parentRect = parent ? parent.getBoundingClientRect() : null;
        if (parentRect && rect.width > parentRect.width + 2) {
            formIssues.push({
                tag: inp.tagName.toLowerCase(),
                name: inp.name || inp.id || '',
                inputWidth: Math.round(rect.width),
                parentWidth: Math.round(parentRect.width)
            });
        }
    }

    // Modal check
    let modalInfo = null;
    const openModal = document.querySelector('.modal-overlay.active, .modal-overlay.open, .modal-overlay[style*="display: block"], .modal-overlay[style*="display: flex"]');
    if (openModal) {
        const modalBox = openModal.querySelector('.modal-box');
        if (modalBox) {
            const mRect = modalBox.getBoundingClientRect();
            modalInfo = {
                width: Math.round(mRect.width),
                height: Math.round(mRect.height),
                fitsInViewport: mRect.width <= winWidth && mRect.height <= window.innerHeight,
                overflowX: Math.max(0, Math.round(mRect.right - winWidth))
            };
        }
    }

    return {
        docWidth: Math.round(docWidth),
        winWidth: winWidth,
        overflow: Math.max(0, Math.round(overflow)),
        overflowingElements: overflowingElements.filter(e => e.isInnermost),
        sidebarInfo: sidebarInfo,
        mobileNavInfo: mobileNavInfo,
        headerCollision: headerCollision,
        smallTouchTargetsCount: smallTouchTargets.length,
        smallTouchTargetsSample: smallTouchTargets.slice(0, 10),
        tables: tables,
        grids: grids,
        formIssues: formIssues,
        modalInfo: modalInfo
    };
}
"""

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless=True)
    context = browser.new_context()
    context.add_cookies([{
        'name': settings.SESSION_COOKIE_NAME,
        'value': session.session_key,
        'domain': '127.0.0.1',
        'path': '/',
    }])
    page = context.new_page()

    total_tests = len(pages) * len(viewports)
    current = 0

    for p_info in pages:
        page_results = {
            "name": p_info["name"],
            "category": p_info["category"],
            "url": p_info["url"],
            "viewport_audits": {}
        }
        print(f"\nAuditing {p_info['category']} > {p_info['name']} ...")

        for vp_w in viewports:
            current += 1
            page.set_viewport_size({"width": vp_w, "height": 800})
            try:
                page.goto(p_info["url"], wait_until="domcontentloaded", timeout=10000)
                page.wait_for_timeout(200)

                # If testing a modal on this page, open it
                if p_info.get("trigger_modal"):
                    page.evaluate(f"""
                        () => {{
                            const m = document.getElementById('{p_info["trigger_modal"]}');
                            if (m) {{
                                m.classList.add('active');
                                m.style.display = 'flex';
                            }}
                        }}
                    """)
                    page.wait_for_timeout(100)

                data = page.evaluate(audit_js)
                page_results["viewport_audits"][str(vp_w)] = data
                overflow_str = f"OVERFLOW {data['overflow']}px" if data['overflow'] > 0 else "OK (0px)"
                print(f"  [{current}/{total_tests}] {vp_w}px: {overflow_str}")
            except Exception as e:
                print(f"  [{current}/{total_tests}] {vp_w}px: ERROR: {e}")
                page_results["viewport_audits"][str(vp_w)] = {"error": str(e)}

        results.append(page_results)

    browser.close()

with open("audit_results.json", "w") as f:
    json.dump(results, f, indent=2)

print("\nAudit completed successfully! Saved all 231 test points to audit_results.json")

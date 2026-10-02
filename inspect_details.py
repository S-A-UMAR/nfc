import os, django
from importlib import import_module
from playwright.sync_api import sync_playwright

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()
admin_user = User.objects.filter(is_staff=True).first()
SessionStore = import_module(settings.SESSION_ENGINE).SessionStore
session = SessionStore()
session[django.contrib.auth.SESSION_KEY] = str(admin_user.pk)
session[django.contrib.auth.BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
session[django.contrib.auth.HASH_SESSION_KEY] = admin_user.get_session_auth_hash()
session.save()

pages = [
    ("Overview", "http://127.0.0.1:8000/dashboard/"),
    ("Profile", "http://127.0.0.1:8000/dashboard/profile/"),
    ("Links", "http://127.0.0.1:8000/dashboard/links/"),
    ("Cards", "http://127.0.0.1:8000/dashboard/card/"),
    ("Analytics", "http://127.0.0.1:8000/dashboard/analytics/"),
    ("Websites", "http://127.0.0.1:8000/dashboard/website/"),
    ("Orders", "http://127.0.0.1:8000/dashboard/orders/"),
    ("Order Detail", "http://127.0.0.1:8000/dashboard/orders/ORD-ADMIN-01/"),
    ("Order Submit", "http://127.0.0.1:8000/dashboard/orders/ORD-ADMIN-01/submit-info/"),
    ("Settings", "http://127.0.0.1:8000/dashboard/settings/"),
    ("Ops Hub", "http://127.0.0.1:8000/operations/"),
    ("Ops Customers", "http://127.0.0.1:8000/operations/customers/"),
    ("Ops Cards", "http://127.0.0.1:8000/operations/cards/"),
    ("Ops Add Card", "http://127.0.0.1:8000/operations/cards/add/"),
    ("Ops Bulk Add", "http://127.0.0.1:8000/operations/cards/bulk-add/"),
    ("Ops Card Detail", "http://127.0.0.1:8000/operations/cards/1/"),
    ("Ops Websites", "http://127.0.0.1:8000/operations/websites/"),
    ("Ops Orders", "http://127.0.0.1:8000/operations/orders/"),
    ("Ops Audit Logs", "http://127.0.0.1:8000/operations/audit-logs/"),
]

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless=True)
    context = browser.new_context()
    context.add_cookies([{"name": settings.SESSION_COOKIE_NAME, "value": session.session_key, "domain": "127.0.0.1", "path": "/"}])
    page = context.new_page()

    for vp in [320, 768]:
        page.set_viewport_size({"width": vp, "height": 800})
        print(f"\n=================== VIEWPORT {vp}px ===================")
        for name, url in pages:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(100)
            res = page.evaluate("""() => {
                const grid2 = Array.from(document.querySelectorAll('.grid-2, form [style*="grid-template-columns"]'));
                const uncollapsedGrids = [];
                for (const g of grid2) {
                    const style = window.getComputedStyle(g);
                    if (style.display === "grid") {
                        const cols = style.gridTemplateColumns.split(" ");
                        if (cols.length > 1) {
                            uncollapsedGrids.push({
                                cols: cols.length,
                                colWidths: cols.map(c => Math.round(parseFloat(c))),
                                text: (g.innerText || "").slice(0, 35).replace(/\\s+/g, " ")
                            });
                        }
                    }
                }

                const tables = Array.from(document.querySelectorAll("table"));
                const tableInfo = tables.map(t => {
                    const p = t.parentElement;
                    const pStyle = window.getComputedStyle(p);
                    return {
                        w: Math.round(t.getBoundingClientRect().width),
                        parentW: Math.round(p.getBoundingClientRect().width),
                        scrollable: pStyle.overflowX === "auto" || pStyle.overflowX === "scroll"
                    };
                });

                return { uncollapsedGrids, tableInfo };
            }""")
            if res["uncollapsedGrids"]:
                for ug in res["uncollapsedGrids"]:
                    print(f"[{name}] Multi-col Grid: cols={ug['cols']} widths={ug['colWidths']} text='{ug['text']}'")
            for t in res["tableInfo"]:
                if t["w"] > t["parentW"]:
                    print(f"[{name}] Table wider than parent: table={t['w']}px, parent={t['parentW']}px, scrollable={t['scrollable']}")

    browser.close()

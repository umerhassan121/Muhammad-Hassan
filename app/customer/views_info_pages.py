"""
Shop ke Support & Trust pages (sidebar SUPPORT section se link hote hain):
FAQ, Help Center, About Us, Terms, Privacy, Return Policy.

Koi model nahi: company ki details (naam, phone, email, address) context processor se aati hain.
Return/refund ke din neeche constants se badalte hain.
"""
import os
from django.conf import settings
from django.contrib import messages
from django.http import FileResponse
from django.shortcuts import render, redirect

RETURN_WINDOW_DAYS = 7      # kitne din mein return request ho sakti hai
REFUND_DAYS = "3-5"         # refund process hone ke working days


def _page(request, template):
    return render(request, template, {
        'return_window_days': RETURN_WINDOW_DAYS,
        'refund_days': REFUND_DAYS,
    })


def faq(request):
    return _page(request, 'customer_portal/info/faq.html')


def help_center(request):
    return _page(request, 'customer_portal/info/help.html')


def about_us(request):
    return _page(request, 'customer_portal/info/about.html')


def terms(request):
    return _page(request, 'customer_portal/info/terms.html')


def privacy(request):
    return _page(request, 'customer_portal/info/privacy.html')


def return_policy(request):
    return _page(request, 'customer_portal/info/returns.html')


# ---------------------------------------------------------------------------
# Shop APK download (home tab ka "Install app" button)
# APK file yahan rakhein:  media/apk/shop.apk   (ya static/apk/shop.apk)
# File na ho to button nazar nahi aata (context: SHOP_APK_URL).
# ---------------------------------------------------------------------------
def shop_apk_path():
    for base in (settings.MEDIA_ROOT, os.path.join(settings.BASE_DIR, 'static')):
        p = os.path.join(str(base), 'apk', 'shop.apk')
        if os.path.isfile(p):
            return p
    return None


def shop_app_download(request):
    path = shop_apk_path()
    if not path:
        messages.info(request, 'The app is not available for download yet.')
        return redirect('shop_home')
    return FileResponse(open(path, 'rb'), as_attachment=True, filename='shop.apk',
                        content_type='application/vnd.android.package-archive')

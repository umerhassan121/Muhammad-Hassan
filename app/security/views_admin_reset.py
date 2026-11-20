"""Admin / staff forgot-password pages (logic: app/security/admin_reset.py)."""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from app.security import admin_reset as ar
from app.security import totp
from app.customer.views_customer_auth import get_client_ip
from app.i18n.i18n_lang import get_language
from app.i18n.server_t import translate

SESSION_KEY = 'arp_username'
TOO_MANY = 'Too many attempts. Please try again later.'
GENERIC = ('If this account exists and has an email set, a 6-digit code has been sent '
           '(valid for 10 minutes). Please check your spam folder too.')


def _translate_flash(request):
    """render() returns a plain HttpResponse, so the message middleware does not run: translate here."""
    try:
        code = get_language(request)['code']
        if code != 'en':
            for m in messages.get_messages(request):
                if not getattr(m, '_i18n_done', False):
                    m.message = translate(str(m.message), code)
                    m._i18n_done = True
    except Exception:
        pass


def _ctx(extra=None):
    from app.models import CompanyInfo
    c = CompanyInfo.objects.first()
    d = {'company_name': c.name if c else 'SmartERP'}
    d.update(extra or {})
    return d


@require_http_methods(['GET', 'POST'])
def admin_forgot_password(request):
    if request.method == 'POST':
        ip = get_client_ip(request) or ''
        if ar.too_many(f'arp_req_ip:{ip}', ar.REQ_PER_IP):
            messages.error(request, TOO_MANY)
            return redirect('admin_forgot_password')
        ar.bump(f'arp_req_ip:{ip}')

        username = (request.POST.get('username') or '').strip()[:150]
        user = ar.find_staff(username)
        if user:
            ar.send_code(user, ip)
        request.session[SESSION_KEY] = username
        request.session.modified = True
        messages.info(request, GENERIC)
        return redirect('admin_reset_password')
    _translate_flash(request)
    return render(request, 'auth/forgot_password.html', _ctx())


@require_http_methods(['GET', 'POST'])
def admin_reset_password(request):
    username = request.session.get(SESSION_KEY)
    if not username:
        messages.info(request, 'Please enter your username first.')
        return redirect('admin_forgot_password')

    if request.method == 'POST':
        ip = get_client_ip(request) or ''
        if ar.too_many(f'arp_ver_ip:{ip}', ar.VERIFY_PER_IP):
            messages.error(request, TOO_MANY)
            return redirect('admin_reset_password')
        ar.bump(f'arp_ver_ip:{ip}')

        user = ar.find_staff(username)
        if not user:
            messages.error(request, 'The code is wrong or has expired.')
            return redirect('admin_reset_password')
        ok, msg = ar.complete_reset(
            user, (request.POST.get('code') or '').strip()[:6], request.POST.get('totp_code', ''),
            request.POST.get('password', ''), request.POST.get('confirm_password', ''), ip)
        if ok:
            request.session.pop(SESSION_KEY, None)
            messages.success(request, msg)
            return redirect('login')
        messages.error(request, msg)
        return redirect('admin_reset_password')

    _translate_flash(request)
    return render(request, 'auth/reset_password.html', _ctx({'username': username}))

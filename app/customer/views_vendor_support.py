"""Vendor portal: Help center (FAQ) aur Support tickets.

- vendor_help            : /shop/vendor/help/            FAQ
- vendor_support         : /shop/vendor/support/         meri tickets + naya ticket
- vendor_support_detail  : /shop/vendor/support/<pk>/    baat-cheet, jawab, band / dobara kholna
Tickets store (VendorProfile) ke hisaab se hain: branch ke tickets us branch ke, aur owner/manager dono dekh sakte hain.
"""
import logging

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from ..decorators import vendor_login_required
from ..shop_flags import flag_required
from . import vendor_support as logic
from .vendor_access import get_vendor_profile
from .vendor_support import SupportError

logger = logging.getLogger(__name__)

FLAG = 'vendor_support_enabled'
TABS = {'open': 'Open', 'closed': 'Closed'}


def _company_name():
    from ..models import CompanyInfo
    company = CompanyInfo.objects.first()
    return company.name if company else 'Shop'


@vendor_login_required
def vendor_help(request):
    profile = get_vendor_profile(request.user)
    from ..shop_flags import shop_flag
    return render(request, 'customer_portal/vendor/help.html', {
        'page_title': 'Help center', 'faq': logic.FAQ, 'company_name': _company_name(),
        'support_on': shop_flag(FLAG), 'unread': logic.unread_count(profile),
    })


@vendor_login_required
@flag_required(FLAG, redirect_to='vendor_help')
def vendor_support(request):
    profile = get_vendor_profile(request.user)
    if request.method == 'POST':
        try:
            t = logic.create_ticket(profile, request.user, request.POST.get('subject'),
                                    request.POST.get('category'), request.POST.get('body'))
            messages.success(request, f'✅ Ticket {t.number} was sent. Support will reply soon.')
            return redirect('vendor_support_detail', pk=t.pk)
        except SupportError as exc:
            messages.error(request, f'❌ {exc}')
        except Exception:
            logger.exception('vendor support create failed (profile=%s)', profile.pk)
            messages.error(request, '❌ Something went wrong. Please try again.')
        return redirect('vendor_support')

    tab = request.GET.get('tab', 'open')
    if tab not in TABS:
        tab = 'open'
    qs = profile.support_tickets.all()
    qs = qs.exclude(status='closed') if tab == 'open' else qs.filter(status='closed')
    return render(request, 'customer_portal/vendor/support.html', {
        'page_title': 'Support tickets', 'tickets': qs[:50], 'tab': tab, 'tabs': TABS,
        'categories': logic.categories(), 'open_n': logic.open_count(profile),
        'max_open': logic.MAX_OPEN_TICKETS, 'company_name': _company_name(),
    })


@vendor_login_required
@flag_required(FLAG, redirect_to='vendor_help')
@require_http_methods(['GET', 'POST'])
def vendor_support_detail(request, pk):
    profile = get_vendor_profile(request.user)
    ticket = get_object_or_404(profile.support_tickets, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'reply':
                logic.vendor_reply(ticket, request.user, request.POST.get('body'))
                messages.success(request, '✅ Your reply was sent.')
            elif action == 'close':
                logic.close_ticket(ticket)
                messages.success(request, '✅ The ticket was closed.')
            elif action == 'reopen':
                logic.reopen_ticket(ticket)
                messages.success(request, '✅ The ticket was reopened.')
            else:
                raise SupportError('Galat action.')
        except SupportError as exc:
            messages.error(request, f'❌ {exc}')
        except Exception:
            logger.exception('vendor support POST failed (ticket=%s)', ticket.pk)
            messages.error(request, '❌ Something went wrong. Please try again.')
        return redirect('vendor_support_detail', pk=ticket.pk)

    logic.mark_seen(ticket)
    return render(request, 'customer_portal/vendor/support_detail.html', {
        'page_title': ticket.number, 'ticket': ticket,
        'thread': ticket.messages.select_related('author'), 'company_name': _company_name(),
    })

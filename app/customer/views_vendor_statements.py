"""Vendor portal: Financial statements (commission / VAT statement) - page aur PDF download.

- vendor_statements    : /shop/vendor/statements/       mahine ki list + custom dates
- vendor_statement_pdf : /shop/vendor/statements/pdf/   ?month=YYYY-MM  ya  ?from=..&to=..
Sirf owner dekh sakta hai (paise ka maamla), jaise Payouts page.
"""
import logging
from datetime import datetime, timedelta

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from ..decorators import vendor_login_required
from .vendor_access import get_vendor_profile
from . import vendor_statement as vs

logger = logging.getLogger(__name__)


def _parse_date(text):
    try:
        return datetime.strptime((text or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


def _range_from_request(request):
    """(start, end) ya None agar tareekhen galat hon."""
    today = timezone.localdate()
    month = (request.GET.get('month') or '').strip()
    if month:
        try:
            y, m = month.split('-')
            start, end = vs.month_range(int(y), int(m))
        except (ValueError, TypeError):
            return None
    else:
        start, end = _parse_date(request.GET.get('from')), _parse_date(request.GET.get('to'))
        if not start or not end:
            return None
    if start > end:
        start, end = end, start
    end = min(end, today)
    if start > end or (end - start).days + 1 > vs.MAX_RANGE_DAYS:
        return None
    return start, end


@vendor_login_required
def vendor_statements(request):
    profile = get_vendor_profile(request.user)
    months = vs.recent_months(12)
    for m in months:
        m['has_data'] = vs.build_statement(profile, m['start'], m['end'])['has_activity']
    return render(request, 'customer_portal/vendor/statements.html', {
        'page_title': 'Financial Statements', 'profile': profile, 'months': months,
        'today': timezone.localdate(), 'vat_pct': vs.vat_percent().normalize(),
    })


@vendor_login_required
def vendor_statement_pdf(request):
    profile = get_vendor_profile(request.user)
    rng = _range_from_request(request)
    if rng is None:
        messages.error(request, '❌ The dates are invalid (at most 1 year, up to today).')
        return redirect('vendor_statements')
    start, end = rng
    try:
        st = vs.build_statement(profile, start, end)
        pdf = vs.render_pdf(st)
    except Exception:
        logger.exception('vendor statement pdf failed (vendor=%s)', profile.pk)
        messages.error(request, '❌ The statement could not be created. Please try again.')
        return redirect('vendor_statements')
    resp = HttpResponse(pdf, content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="{st["number"]}.pdf"'
    return resp

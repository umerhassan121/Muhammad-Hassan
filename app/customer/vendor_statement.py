"""Vendor Financial Statement (commission invoice / VAT statement).

Ek period (mahina ya custom dates) ka hisaab:
    Sales  -  Commission  =  Vendor ka hissa (payable)
    payable  -  VAT (commission par)  =  Net payable
    Net payable + Opening balance  -  Is period me di gayi payments  =  Closing balance

Hisaab `vendor_commission.vendor_earnings` ke usool par hai (batch cost == vendor ka hissa),
bas date ke hisaab se. Is liye jab tak VAT 0 ho, closing balance Payouts page ke 'Total baqi'
se milta hai.

VAT: Settings > Shop > `vendor_statement_vat_percent` (default 0). Ye VAT shop ke commission
par lagta hai aur vendor ke payable se katta hai. Bahrain/Pakistan ka rate admin khud likhe.
"""
import io
import logging
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

CENT = Decimal('0.01')
ZERO = Decimal('0.00')
DONE_STATUSES = ('delivered', 'invoiced', 'partially_delivered')
MAX_RANGE_DAYS = 366
_MUL = DecimalField(max_digits=18, decimal_places=2)


def _q(v):
    return Decimal(v or 0).quantize(CENT, ROUND_HALF_UP)


def _day_start(d):
    return timezone.make_aware(datetime.combine(d, time.min))


def vat_percent():
    from .offers import setting_decimal
    pct = setting_decimal('vendor_statement_vat_percent', '0')
    return min(max(pct, Decimal('0')), Decimal('100'))


def _period_totals(vendor, start, end):
    """Sales / payable / deals. start None = shuru se; end None = ab tak (end din samet)."""
    from app.models import SaleItem, SaleItemBatchUsage, OrderDeal
    items = SaleItem.objects.filter(product__vendor=vendor)
    deals = OrderDeal.objects.filter(vendor=vendor, order__status__in=DONE_STATUSES)
    if start is not None:
        items = items.filter(sale__sale_date__gte=_day_start(start))
        deals = deals.filter(order__order_date__gte=_day_start(start))
    if end is not None:
        items = items.filter(sale__sale_date__lt=_day_start(end + timedelta(days=1)))
        deals = deals.filter(order__order_date__lt=_day_start(end + timedelta(days=1)))

    agg = items.aggregate(sales=Sum('total_amt'), units=Sum('qty'))
    cost = SaleItemBatchUsage.objects.filter(sale_item__in=items).aggregate(
        t=Sum(ExpressionWrapper(F('qty') * F('cost_price'), output_field=_MUL)))['t']
    extras = items.aggregate(
        t=Sum(ExpressionWrapper(F('qty') * F('options_extra_share'), output_field=_MUL)))['t']
    deal_total = _q(deals.aggregate(t=Sum('amount'))['t'])

    gross = _q(agg['sales'])
    payable = _q(Decimal(cost or 0) + Decimal(extras or 0))
    return {
        'units': agg['units'] or 0,
        'gross': gross,
        'deals': deal_total,
        'sales': gross - deal_total,
        'payable': payable - deal_total,
    }


def build_statement(profile, start, end):
    """Poora statement dict (template aur PDF dono isi se)."""
    from app.models import VendorPayout, SaleOrder
    vendor = profile.vendor
    vat_pct = vat_percent()

    cur = _period_totals(vendor, start, end)
    commission = _q(cur['sales'] - cur['payable'])
    vat = _q(commission * vat_pct / Decimal('100'))
    net = _q(cur['payable'] - vat)

    # Opening balance: period se pehle ka (payable - VAT - di gayi payments)
    before = _period_totals(vendor, None, start - timedelta(days=1))
    before_comm = _q(before['sales'] - before['payable'])
    before_vat = _q(before_comm * vat_pct / Decimal('100'))
    paid_before = _q(VendorPayout.objects.filter(
        vendor=vendor, paid_at__lt=_day_start(start)).aggregate(t=Sum('amount'))['t'])
    opening = _q(before['payable'] - before_vat - paid_before)

    payouts = list(VendorPayout.objects.filter(
        vendor=vendor, paid_at__gte=_day_start(start),
        paid_at__lt=_day_start(end + timedelta(days=1))).order_by('paid_at', 'id'))
    paid = _q(sum((p.amount for p in payouts), Decimal('0')))
    closing = _q(opening + net - paid)

    orders = SaleOrder.objects.filter(
        vendor=vendor, order_date__gte=_day_start(start),
        order_date__lt=_day_start(end + timedelta(days=1)))
    from .vendor_commission import commission_percent
    return {
        'profile': profile, 'vendor': vendor, 'start': start, 'end': end,
        'number': f'ST-{vendor.pk}-{start:%Y%m%d}-{end:%Y%m%d}',
        'orders_delivered': orders.filter(status__in=DONE_STATUSES).count(),
        'orders_cancelled': orders.filter(status='cancelled').count(),
        'units': cur['units'], 'gross': cur['gross'], 'deals': cur['deals'],
        'sales': cur['sales'], 'commission_pct': Decimal(commission_percent(profile)).normalize(),
        'commission': commission, 'vat_pct': vat_pct.normalize(), 'vat': vat,
        'payable': cur['payable'], 'net': net,
        'opening': opening, 'payouts': payouts, 'paid': paid, 'closing': closing,
        'has_activity': bool(cur['gross'] or payouts or cur['deals']),
    }


def month_range(year, month):
    """Mahine ki pehli aur aakhri tareekh (aaj se aage nahi)."""
    first = datetime(year, month, 1).date()
    nxt = datetime(year + (month == 12), (month % 12) + 1, 1).date()
    last = nxt - timedelta(days=1)
    return first, min(last, timezone.localdate())


def recent_months(count=12):
    today = timezone.localdate()
    y, m, out = today.year, today.month, []
    for _ in range(count):
        first, last = month_range(y, m)
        out.append({'key': f'{y}-{m:02d}', 'label': first.strftime('%B %Y'), 'start': first, 'end': last})
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


# ------------------------------------------------------------------ PDF
def _ascii(text):
    """Helvetica sirf Latin-1 dikha sakta hai (Urdu naam ke liye '?')."""
    return str(text or '').encode('latin-1', 'replace').decode('latin-1')


def render_pdf(st):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape

    from app.models import CompanyInfo
    company = CompanyInfo.objects.first()
    company_name = _ascii(company.name if company else 'Shop')
    profile, vendor = st['profile'], st['vendor']

    def money(v):
        return f"Rs. {Decimal(v):,.2f}"

    base = getSampleStyleSheet()
    normal = ParagraphStyle('n', parent=base['Normal'], fontSize=9, leading=12)
    small = ParagraphStyle('s', parent=normal, fontSize=8, textColor=colors.HexColor('#6b7280'))
    h1 = ParagraphStyle('h1', parent=base['Title'], fontSize=18, alignment=0, spaceAfter=2)
    h2 = ParagraphStyle('h2', parent=base['Heading3'], fontSize=11, spaceBefore=10, spaceAfter=4)

    def P(txt, style=normal):
        return Paragraph(escape(_ascii(txt)), style)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"Statement {st['number']}")
    el = []
    head = Table([[P(company_name, h1), P(f"Statement No: {st['number']}", normal)],
                  [P('Vendor Financial Statement', normal),
                   P(f"Period: {st['start']:%d %b %Y} to {st['end']:%d %b %Y}", normal)],
                  [P(f"Generated: {timezone.localtime():%d %b %Y, %I:%M %p}", small), '']],
                 colWidths=[100 * mm, 76 * mm])
    head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                              ('BOTTOMPADDING', (0, 0), (-1, -1), 1)]))
    el += [head, Spacer(1, 6)]

    store_lines = [f'<b>{escape(_ascii(profile.business_name))}</b>']
    for v in (profile.city, getattr(vendor, 'address', ''), getattr(vendor, 'contact_number', '')):
        if v:
            store_lines.append(escape(_ascii(v)))
    pay_line = ''
    if profile.payout_account_no:
        pay_line = (f"Payout: {profile.get_payout_method_display()} - {profile.payout_account_title} - "
                    f"{profile.payout_account_no}")
    el += [Paragraph('Store details', h2), Paragraph('<br/>'.join(store_lines), normal)]
    if pay_line:
        el.append(P(pay_line, small))

    grey, green = colors.HexColor('#f3f4f6'), colors.HexColor('#ecfdf5')
    right = ParagraphStyle('right', parent=normal, alignment=2)

    def cell(text, style, bold=False):
        text = escape(_ascii(text))
        return Paragraph(f'<b>{text}</b>' if bold else text, style)

    def two_col(rows, bold_rows=(), shade=None):
        t = Table([[cell(a, normal, i in bold_rows), cell(b, right, i in bold_rows)]
                   for i, (a, b) in enumerate(rows)], colWidths=[116 * mm, 60 * mm])
        style = [('LINEBELOW', (0, 0), (-1, -1), .3, colors.HexColor('#e5e7eb')),
                 ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                 ('BACKGROUND', (0, len(rows) - 1), (-1, len(rows) - 1), green)]
        if shade is not None:
            style.append(('BACKGROUND', (0, shade), (-1, shade), grey))
        t.setStyle(TableStyle(style))
        return t

    rows = [
        ['Orders delivered', str(st['orders_delivered'])],
        ['Orders cancelled', str(st['orders_cancelled'])],
        ['Units sold', f"{st['units']:g}"],
        ['Gross sales (items)', money(st['gross'])],
        ['Less: deals / offers funded by store', f"- {money(st['deals'])}"],
        ['Net sales', money(st['sales'])],
        [f"Platform commission ({st['commission_pct']}%)", f"- {money(st['commission'])}"],
    ]
    if st['vat_pct'] > 0:
        rows.append([f"VAT on commission ({st['vat_pct']}%)", f"- {money(st['vat'])}"])
    rows.append(['Net earnings for period', money(st['net'])])
    el += [Paragraph('Earnings summary', h2), two_col(rows, bold_rows=(5, len(rows) - 1), shade=5)]

    bal = [['Opening balance', money(st['opening'])],
           ['Add: net earnings for period', money(st['net'])],
           ['Less: payments made in period', f"- {money(st['paid'])}"],
           ['Closing balance (still payable to you)', money(st['closing'])]]
    el += [Paragraph('Balance', h2), two_col(bal, bold_rows=(3,))]

    el.append(Paragraph('Payments received', h2))
    if st['payouts']:
        data = [[P('Date'), P('Method'), P('Reference'), cell('Amount', right)]]
        for p in st['payouts']:
            data.append([P(f"{timezone.localtime(p.paid_at):%d %b %Y}"), P(p.get_method_display()),
                         P(p.reference_no or '-'),
                         cell(money(p.amount), right)])
        pt = Table(data, colWidths=[30 * mm, 38 * mm, 60 * mm, 48 * mm], repeatRows=1)
        pt.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), grey),
                                ('LINEBELOW', (0, 0), (-1, -1), .3, colors.HexColor('#e5e7eb'))]))
        el.append(pt)
    else:
        el.append(P('No payments in this period.', small))

    el += [Spacer(1, 10), P('Sales and commission are taken from delivered orders recorded in this period. '
                            'This is a system-generated statement and needs no signature.', small)]
    if company and company.footer_note:
        el.append(P(company.footer_note, small))
    doc.build(el)
    return buf.getvalue()

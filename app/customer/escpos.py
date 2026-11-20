"""ESC/POS receipt bytes (thermal printers: 58 mm = 32 columns, 80 mm = 48 columns).

Pure Python, Django ke baghair - isi liye aasani se test hota hai.
Printer ko bytes browser bhejta hai (Web Bluetooth / WebUSB / Web Serial), dekhein order_receipt.html.

Limit: plain-text mode mein printers sirf Latin (CP437) jaante hain. Accent wale harf sada ho jate hain (e.g. e-acute -> e);
Arabic / Urdu / aur koi non-Latin harf '?' ban jata hai. (Is ke liye image-raster printing chahiye - alag kaam.)
"""
import textwrap
import unicodedata

ESC, GS = b'\x1b', b'\x1d'

INIT = ESC + b'@'
CODEPAGE_CP437 = ESC + b't' + b'\x00'
ALIGN = {'left': ESC + b'a\x00', 'center': ESC + b'a\x01', 'right': ESC + b'a\x02'}
BOLD_ON, BOLD_OFF = ESC + b'E\x01', ESC + b'E\x00'
DOUBLE_ON, DOUBLE_OFF = GS + b'!\x11', GS + b'!\x00'      # double width + height
CUT = GS + b'V\x42\x00'                                    # feed + partial cut


def columns(width_mm):
    return 32 if int(width_mm) == 58 else 48


def clean(text):
    """Printer ke liye safe text: accents hata do, control chars hata do, baqi non-Latin -> '?'."""
    out = []
    for ch in str(text or ''):
        if ch in '\r\n\t':
            out.append(' ')
            continue
        if ord(ch) < 32 or ord(ch) == 127:
            continue
        base = unicodedata.normalize('NFKD', ch)
        base = ''.join(c for c in base if not unicodedata.combining(c))
        try:
            base.encode('cp437')
            out.append(base)
        except UnicodeEncodeError:
            out.append('?')
    return ''.join(out)


def _enc(text):
    return clean(text).encode('cp437', errors='replace')


def two_col(left, right, width):
    """left ek ya zyada line (wrap), right aakhri... pehli line ke saath. Bytes ke liye list[str]."""
    left, right = clean(left), clean(right)
    room = max(width - len(right) - 1, 8)
    lines = textwrap.wrap(left, room) or ['']
    first = lines[0].ljust(width - len(right)) + right
    return [first[:width]] + lines[1:]


def _money(value):
    try:
        return f'{float(value):.2f}'
    except (TypeError, ValueError):
        return str(value or '')


class _Buf:
    def __init__(self, width):
        self.w = width
        self.b = bytearray(INIT + CODEPAGE_CP437)

    def raw(self, data):
        self.b += data

    def line(self, text='', align='left', bold=False, big=False):
        self.b += ALIGN[align]
        if bold:
            self.b += BOLD_ON
        if big:
            self.b += DOUBLE_ON
        width = self.w // 2 if big else self.w
        for part in (textwrap.wrap(clean(text), width) or ['']):
            self.b += _enc(part) + b'\n'
        if big:
            self.b += DOUBLE_OFF
        if bold:
            self.b += BOLD_OFF
        self.b += ALIGN['left']

    def pair(self, left, right, bold=False):
        if bold:
            self.b += BOLD_ON
        for ln in two_col(left, right, self.w):
            self.b += _enc(ln) + b'\n'
        if bold:
            self.b += BOLD_OFF

    def rule(self):
        self.b += b'-' * self.w + b'\n'


def build_receipt(payload, shop_name, width_mm=80, printed_at='', created_text='', company_name=''):
    """payload = pos_api.order_payload(...) ka dict. Return: bytes (ESC/POS)."""
    w = columns(width_mm)
    b = _Buf(w)
    b.line(shop_name, 'center', bold=True)
    if company_name:
        b.line(company_name, 'center')
    b.rule()
    b.line('#' + str(payload['order_no']), 'center', bold=True, big=True)
    if created_text:
        b.line(created_text, 'center')
    if payload.get('scheduled_for'):
        b.line('SCHEDULED: ' + str(payload['scheduled_for'])[:16].replace('T', ' '), 'center', bold=True)
    if payload.get('prep_minutes'):
        b.line(f"Prep time: {payload['prep_minutes']} min", 'center')
    b.rule()
    cust = payload.get('customer') or {}
    b.line(cust.get('name', ''), bold=True)
    if cust.get('phone'):
        b.line('Tel: ' + cust['phone'])
    if cust.get('address'):
        b.line(cust['address'])
    b.rule()
    for it in payload.get('items', []):
        qty = float(it['qty'])
        qty_txt = str(int(qty)) if qty == int(qty) else f'{qty:g}'
        b.pair(f"{qty_txt} x {it['name']}", _money(it['unit_price']))
        if it.get('options'):
            b.line('  + ' + it['options'])
        if it.get('note'):
            b.line('  NOTE: ' + it['note'], bold=True)
    b.rule()
    b.pair('Items', _money(payload['subtotal']))
    b.pair('Delivery', _money(payload['delivery_fee']))
    b.pair('TOTAL', _money(payload['total']), bold=True)
    cod = payload.get('payment_method', 'cod') == 'cod'
    b.pair('Payment', 'Cash on delivery' if cod else str(payload.get('payment_method', '')).upper())
    if cod:
        b.pair('Cash to collect', _money(payload['cash_due']), bold=True)
    b.rule()
    if printed_at:
        b.line('Printed ' + printed_at, 'center')
    b.raw(b'\n\n\n' + CUT)
    return bytes(b.b)

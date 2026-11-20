"""Peak-hour bonus: admin waqt ki khidkiyan (windows) tay karta hai; us waqt jo order rider accept kare
us par har delivery ka extra milta hai. Extra order lete waqt DeliveryInfo.peak_bonus mein likha jata hai
(isliye baad mein window badalne se purane orders ki kamai nahi badalti) aur deliver par rider_fee mein jud jata hai.

Overlapping windows mein sab se bara extra lagta hai (jodte nahi)."""
from datetime import time
from decimal import Decimal

from ..shop_flags import shop_flag

ZERO = Decimal('0')
DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
MAX_EXTRA = Decimal('100000')


def parse_days(csv):
    """'0,2,6' -> {0, 2, 6}. Khali = har din (khali set). Ghalat tukde chhor diye jate hain."""
    out = set()
    for part in (csv or '').split(','):
        part = part.strip()
        if part.isdigit() and 0 <= int(part) <= 6:
            out.add(int(part))
    return out


def in_window(now_t, weekday, start, end, days):
    """Pure: kya (waqt, hafte ka din) window mein hai? days = set (khali = har din).
    Raat ke paar window (end <= start) ka din wo hai jis din wo shuru hui."""
    if start == end:
        return False
    if start < end:
        return start <= now_t < end and (not days or weekday in days)
    if now_t >= start:
        return not days or weekday in days
    if now_t < end:
        return not days or ((weekday - 1) % 7) in days
    return False


def current(now=None):
    """Abhi ka sab se bara peak: {'extra': Decimal, 'name': str, 'until': 'HH:MM'} ya None."""
    if not shop_flag('rider_peak_enabled'):
        return None
    from ..models import RiderPeakWindow
    if now is None:
        from .rider_gate import local_now
        now = local_now()
    best = None
    for w in RiderPeakWindow.objects.filter(is_active=True, extra_amount__gt=0):
        if in_window(now.time(), now.weekday(), w.start_time, w.end_time, parse_days(w.days)):
            if best is None or w.extra_amount > best['extra']:
                best = {'extra': Decimal(w.extra_amount), 'name': w.name, 'until': w.end_time.strftime('%H:%M')}
    return best


def bonus_now(now=None):
    c = current(now)
    return c['extra'] if c else ZERO


def parse_time(raw):
    """'HH:MM' -> time ya None."""
    try:
        h, m = (raw or '').strip().split(':')[:2]
        return time(int(h), int(m))
    except (ValueError, TypeError):
        return None

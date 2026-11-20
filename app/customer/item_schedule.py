"""Item schedule ka hisaab: kya item abhi (ya kisi waqt) available hai, aur customer ko dikhane ka text.

Qaida: schedule na ho ya khali ho -> hamesha available. Din (days) khali = har din; waqt khali = poora din.
Raat paar waqt (22:00 -> 02:00): 'din' wo hai jis din se shuru hota hai, is liye subah ke 00:00-02:00 hisse
ke liye pichhla din dekha jata hai (jaise store hours mein).
"""
from datetime import time

from django.utils import timezone

DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


def parse_days(raw):
    """'0156' -> {0,1,5,6}. Galat harf chhod diye jate hain."""
    return {int(c) for c in (raw or '') if c in '0123456'}


def clean_days(values):
    """Form ke din (list of str) -> '056' (sorted, unique). Sab 7 din == '' (har din)."""
    days = sorted(parse_days(''.join(str(v) for v in values)))
    return '' if len(days) in (0, 7) else ''.join(str(d) for d in days)


def _fmt_time(t):
    return t.strftime('%I:%M %p').lstrip('0')


def _fmt_days(days):
    if not days:
        return ''
    ds = sorted(days)
    if ds == [0, 1, 2, 3, 4]:
        return 'Mon-Fri'
    if ds == [5, 6]:
        return 'Sat-Sun'
    return ', '.join(DAY_NAMES[d] for d in ds)


def describe(sched):
    """'7:00 AM - 11:00 AM · Mon-Fri' (khali ho to '')."""
    if sched is None:
        return ''
    parts = []
    if sched.avail_from and sched.avail_to:
        parts.append(f'{_fmt_time(sched.avail_from)} - {_fmt_time(sched.avail_to)}')
    days = _fmt_days(parse_days(sched.days))
    if days:
        parts.append(days)
    return ' · '.join(parts)


def is_available_at(sched, local_dt):
    """local_dt (aware, local time) par item available hai?"""
    if sched is None:
        return True
    days = parse_days(sched.days)
    wd, t = local_dt.weekday(), local_dt.time()
    o, c = sched.avail_from, sched.avail_to
    if not (o and c):
        return not days or wd in days
    if o <= c:
        return (not days or wd in days) and o <= t <= c
    # raat paar: shuru wale din ki raat, ya agle din ka subah wala hissa
    if t >= o:
        return not days or wd in days
    if t <= c:
        return not days or ((wd - 1) % 7) in days
    return False


def _get(product):
    try:
        return product.schedule
    except Exception:           # RelatedObjectDoesNotExist
        return None


def unavailable_message(product, when=None):
    """Item abhi (ya `when` par) available na ho to message, warna None."""
    sched = _get(product)
    if sched is None:
        return None
    local = timezone.localtime(when) if when else timezone.localtime()
    if is_available_at(sched, local):
        return None
    when_text = describe(sched)
    return f'{product.name} abhi available nahi' + (f' (sirf {when_text})' if when_text else '') + '.'


def annotate(products):
    """Store page ke products par p.sched_off / p.sched_text lagao (ek hi query mein)."""
    from app.models import ProductSchedule
    products = list(products)
    ids = [p.pk for p in products]
    rows = {s.product_id: s for s in ProductSchedule.objects.filter(product_id__in=ids)}
    now = timezone.localtime()
    for p in products:
        s = rows.get(p.pk)
        p.sched_text = describe(s) if s else ''
        p.sched_off = bool(s) and not is_available_at(s, now)
    return products


def cart_error(cart, when=None):
    """Cart ke wo items jo abhi (ya `when` par) available nahi. Message ya None."""
    from app.models import ProductSchedule
    ids = set()
    for item in (cart or {}).values():
        try:
            ids.add(int(item.get('product_id')))
        except (TypeError, ValueError, AttributeError):
            continue
    if not ids:
        return None
    local = timezone.localtime(when) if when else timezone.localtime()
    bad = []
    for s in ProductSchedule.objects.filter(product_id__in=ids).select_related('product'):
        if not is_available_at(s, local):
            txt = describe(s)
            bad.append(s.product.name + (f' ({txt})' if txt else ''))
    if not bad:
        return None
    return ('Ye item is waqt available nahi, cart se hata dein: ' + ', '.join(sorted(bad)) + '.')


def save_schedule(product, avail_from, avail_to, days):
    """Schedule save/clear. Dono waqt ya koi nahi; din khali = har din. Sab khali ho to schedule hata do.
    Return: 'saved' / 'cleared'. Galat input par ValueError (saaf message ke sath)."""
    from app.models import ProductSchedule
    if bool(avail_from) != bool(avail_to):
        raise ValueError('Shuru aur khatam, dono waqt likhen (ya dono khali chhoden).')
    if avail_from and avail_to and avail_from == avail_to:
        raise ValueError('Shuru aur khatam ka waqt ek jaisa nahi ho sakta.')
    days = clean_days(days)
    if not avail_from and not days:
        ProductSchedule.objects.filter(product=product).delete()
        return 'cleared'
    ProductSchedule.objects.update_or_create(
        product=product, defaults={'avail_from': avail_from, 'avail_to': avail_to, 'days': days})
    return 'saved'


def parse_time(value):
    """'HH:MM' -> time, khali -> None, kharab -> ValueError."""
    value = (value or '').strip()
    if not value:
        return None
    try:
        h, m = value.split(':')[:2]
        return time(int(h), int(m))
    except (ValueError, TypeError):
        raise ValueError('Waqt galat hai (HH:MM chahiye).')

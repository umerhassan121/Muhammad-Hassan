"""
Sponsored / Featured store (vendor paise de kar upar aaye - shop ki extra income).

- Vendor "Promote my store" page se request bhejta hai (pending).
- Payment milne par admin Activate karta hai (Admin > Store Sponsorships); mudat Settings se.
- Active sponsorship wale stores store list (Recommended sort) aur homepage par pehle aate hain, 'Sponsored' tag ke saath.
- Band (closed) store kabhi khule store se upar nahi aata.

Budget + report (ads):
- Settings mein `sponsored_cpc` (per click rate) > 0 ho to vendor roz ka budget (`daily_budget`) tay karta hai.
  Us din ka kharch (clicks x rate) budget tak pahunchte hi store us din ke baqi hisse mein upar nahi aata.
  cpc = 0 ya budget = 0 ho to purane jaisa chalta hai (fixed price, koi hadd nahi).
- Impressions / clicks / orders `SponsoredDaily` mein roz ke hisaab se likhe jate hain. Koi bhi galti ho to
  sirf tracking chhoot-ti hai, customer ka page ya order kabhi nahi rukta.
- Billable click: ek session ek store par ek din mein sirf ek baar (refresh se kharch nahi badhta).
- Order attribution: sponsored click ke baad 24 ghante ke andar usi store ka order.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from ..shop_flags import shop_flag

logger = logging.getLogger(__name__)


def sponsored_settings():
    from .offers import setting_decimal
    return {
        'enabled': shop_flag('shop_sponsored_enabled'),
        'price': max(setting_decimal('sponsored_price', '0'), Decimal('0')),
        'days': max(int(setting_decimal('sponsored_days', '7')), 1),
        'max_slots': max(int(setting_decimal('sponsored_max_slots', '5')), 0),
        'cpc': max(setting_decimal('sponsored_cpc', '0'), Decimal('0')),
        'min_budget': max(setting_decimal('sponsored_min_daily_budget', '0'), Decimal('0')),
    }


def sponsored_profile_ids(today=None):
    """Abhi sponsored VendorProfile ids (flag off ho to khali). Slots se zyada hon to pehle shuru hone wale."""
    try:
        cfg = sponsored_settings()
        if not cfg['enabled']:
            return set()
        from ..models import StoreSponsorship
        today = today or timezone.localdate()
        rows = (StoreSponsorship.objects.filter(status='active', starts_on__lte=today, ends_on__gte=today)
                .order_by('starts_on', 'pk').values_list('profile_id', flat=True))
        exhausted = _budget_exhausted_profile_ids(today, cfg)
        ids = []
        for pid in rows:
            if pid not in ids and pid not in exhausted:
                ids.append(pid)
        if cfg['max_slots']:
            ids = ids[:cfg['max_slots']]
        return set(ids)
    except Exception:
        logger.exception('sponsored_profile_ids failed')
        return set()


def vendor_status(profile, today=None):
    """Vendor page ke liye: {'running': sponsorship ya None, 'pending': sponsorship ya None}."""
    from ..models import StoreSponsorship
    today = today or timezone.localdate()
    qs = StoreSponsorship.objects.filter(profile=profile)
    running = (qs.filter(status='active', ends_on__gte=today).order_by('-ends_on').first())
    pending = qs.filter(status='pending').order_by('-requested_at').first()
    return {'running': running, 'pending': pending}


# ------------------------------------------------------------
# BUDGET
# ------------------------------------------------------------
def _budget_exhausted_profile_ids(today, cfg):
    """Un profiles ke ids jin ka aaj ka kharch daily_budget tak pahunch gaya (cpc band ho to khali)."""
    if not cfg.get('cpc'):
        return set()
    try:
        from django.db.models import F
        from ..models import SponsoredDaily
        rows = (SponsoredDaily.objects
                .filter(day=today, sponsorship__status='active', sponsorship__daily_budget__gt=0,
                        spend__gte=F('sponsorship__daily_budget'))
                .values_list('sponsorship__profile_id', flat=True))
        return set(rows)
    except Exception:
        logger.exception('sponsored budget check failed')
        return set()


def clean_budget(raw, cfg=None):
    """Vendor ka likha budget -> Decimal. Galat/khali = 0 (koi hadd nahi). Kam se kam hadd se neeche ho to SupportError nahi,
    ValueError (message vendor ko dikhane ke liye)."""
    from decimal import InvalidOperation
    cfg = cfg or sponsored_settings()
    text = str(raw or '').strip().replace(',', '')
    if not text:
        return Decimal('0')
    try:
        val = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError('Enter the daily budget as a number.')
    if val < 0:
        raise ValueError('Daily budget cannot be negative.')
    if val == 0:
        return Decimal('0')
    if cfg['min_budget'] and val < cfg['min_budget']:
        raise ValueError(f'Daily budget must be at least Rs. {cfg["min_budget"]:,.0f} (or 0 for no limit).')
    return val.quantize(Decimal('0.01'))


# ------------------------------------------------------------
# TRACKING (impressions / clicks / orders)
# ------------------------------------------------------------
SESSION_SEEN = 'sp_seen'          # {profile_id: 'YYYY-MM-DD'}  aaj kin sponsored stores ko list mein dekha
SESSION_CLICK = 'sp_click'        # {profile_id: iso datetime}  sponsored click ka waqt (order attribution)
SESSION_BILLED = 'sp_billed'      # {profile_id: 'YYYY-MM-DD'}  aaj is session se kis ka click gina ja chuka
ATTRIBUTION_HOURS = 24


def _running_sponsorship(profile_id, today):
    from ..models import StoreSponsorship
    return (StoreSponsorship.objects.filter(profile_id=profile_id, status='active',
                                            starts_on__lte=today, ends_on__gte=today)
            .order_by('starts_on', 'pk').first())


def _bump(sponsorship, today, **inc):
    """SponsoredDaily ki row banao/badhao (race-safe: F() se)."""
    from django.db import IntegrityError, transaction
    from django.db.models import F
    from ..models import SponsoredDaily
    with transaction.atomic():
        try:
            SponsoredDaily.objects.get_or_create(sponsorship=sponsorship, day=today)
        except IntegrityError:
            pass
        SponsoredDaily.objects.filter(sponsorship=sponsorship, day=today).update(
            **{k: F(k) + v for k, v in inc.items()})


def record_impressions(request, shown_ids):
    """Store list / home par jo sponsored stores dikhe unhein gino. Ek session ek store ko ek din mein ek hi baar."""
    try:
        if not shown_ids or getattr(request, 'session', None) is None:
            return
        today = timezone.localdate()
        key = today.isoformat()
        seen = dict(request.session.get(SESSION_SEEN) or {})
        fresh = [pid for pid in shown_ids if seen.get(str(pid)) != key]
        # session mein sirf aaj ki entries rakho (barhne se bachao)
        seen = {k: v for k, v in seen.items() if v == key}
        for pid in shown_ids:
            seen[str(pid)] = key
        request.session[SESSION_SEEN] = seen
        for pid in fresh:
            sp = _running_sponsorship(pid, today)
            if sp:
                _bump(sp, today, impressions=1)
    except Exception:
        logger.exception('sponsored impression failed')


def record_click(request, profile_id):
    """Store page khula: agar customer sponsored list se aaya (session mein dekha tha) to ek billable click.
    Hadd (budget) poori ho chuki ho to click gina nahi jata (kharch budget se aage nahi barhta)."""
    try:
        session = getattr(request, 'session', None)
        if session is None:
            return False
        today = timezone.localdate()
        key = today.isoformat()
        if (session.get(SESSION_SEEN) or {}).get(str(profile_id)) != key:
            return False                      # list mein sponsored ho kar dekha hi nahi -> click nahi
        billed = {k: v for k, v in (session.get(SESSION_BILLED) or {}).items() if v == key}
        if str(profile_id) in billed:
            return False                      # aaj is session se pehle hi gina ja chuka
        sp = _running_sponsorship(profile_id, today)
        if not sp:
            return False
        cfg = sponsored_settings()
        if not cfg['enabled']:
            return False
        if profile_id in _budget_exhausted_profile_ids(today, cfg):
            return False
        _bump(sp, today, clicks=1, spend=cfg['cpc'])
        billed[str(profile_id)] = key
        session[SESSION_BILLED] = billed
        clicks = dict(session.get(SESSION_CLICK) or {})
        clicks[str(profile_id)] = timezone.now().isoformat()
        session[SESSION_CLICK] = clicks
        return True
    except Exception:
        logger.exception('sponsored click failed')
        return False


def record_order(request_or_session, order):
    """Order ban gaya: agar customer ne pichhle 24 ghante mein is store ka sponsored click kiya tha to order gino."""
    try:
        session = getattr(request_or_session, 'session', request_or_session)
        if session is None or not getattr(order, 'vendor_id', None):
            return False
        from ..models import VendorProfile
        profile_id = VendorProfile.objects.filter(vendor_id=order.vendor_id).values_list('pk', flat=True).first()
        if not profile_id:
            return False
        clicks = dict(session.get(SESSION_CLICK) or {})
        when = clicks.get(str(profile_id))
        if not when:
            return False
        from django.utils.dateparse import parse_datetime
        clicked = parse_datetime(when)
        if not clicked or timezone.now() - clicked > timedelta(hours=ATTRIBUTION_HOURS):
            clicks.pop(str(profile_id), None)
            session[SESSION_CLICK] = clicks
            return False
        today = timezone.localdate()
        sp = _running_sponsorship(profile_id, today)
        if not sp:
            return False
        from .store_orders import order_payable_total
        _bump(sp, today, orders=1, order_value=order_payable_total(order))
        clicks.pop(str(profile_id), None)         # ek click = ek order (dobara order par dobara nahi ginte)
        session[SESSION_CLICK] = clicks
        return True
    except Exception:
        logger.exception('sponsored order attribution failed')
        return False


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------
def report(profile, days=30, today=None):
    """Vendor ki report: pichhle `days` din ke totals + roz ki rows (naya din pehle)."""
    from django.db.models import Sum
    from ..models import SponsoredDaily
    today = today or timezone.localdate()
    start = today - timedelta(days=max(int(days), 1) - 1)
    qs = SponsoredDaily.objects.filter(sponsorship__profile=profile, day__gte=start, day__lte=today)
    rows = list(qs.values('day').annotate(
        impressions=Sum('impressions'), clicks=Sum('clicks'), orders=Sum('orders'),
        order_value=Sum('order_value'), spend=Sum('spend')).order_by('-day'))
    tot = {k: sum((r[k] or 0) for r in rows) for k in ('impressions', 'clicks', 'orders', 'order_value', 'spend')}
    for r in rows + [tot]:
        r['ctr'] = _pct(r['clicks'], r['impressions'])
        r['cost_per_order'] = (Decimal(r['spend']) / r['orders']).quantize(Decimal('0.01')) if r['orders'] else None
    return {'days': days, 'start': start, 'end': today, 'rows': rows, 'total': tot}


def _pct(part, whole):
    return round(part * 100.0 / whole, 1) if whole else 0.0


def today_spend(profile, today=None):
    """Aaj ka kharch aur budget (vendor ko 'aaj ka kharch / hadd' dikhane ke liye)."""
    from ..models import SponsoredDaily
    today = today or timezone.localdate()
    sp = _running_sponsorship(profile.pk, today)
    if not sp:
        return None
    row = SponsoredDaily.objects.filter(sponsorship=sp, day=today).first()
    spent = row.spend if row else Decimal('0')
    return {'spent': spent, 'budget': sp.daily_budget,
            'exhausted': bool(sp.daily_budget and spent >= sp.daily_budget)}

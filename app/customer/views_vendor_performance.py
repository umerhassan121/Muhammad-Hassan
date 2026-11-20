"""Vendor portal: Performance dashboard (store quality score).

Vendor ko ek nazar mein dikhata hai: order accept rate, miss/reject hue orders, prep time (bataya hua vs asal),
rating, cancel rate, disputes, aur 0-100 ka 'store quality score' - pichhli barabar muddat se muqabla karke.

Saare hisaab ke qaide app/utils/vendor_perf_rules.py mein hain (Django ke baghair test hote hain).
Nota: accepted_at / ready_at nayi cheezein hain (migration 0105), is liye purane orders ka prep-time data nahi hota;
unhe prep accuracy se bahar rakha jata hai (baqi sab metrics purane orders par bhi chalte hain).
"""
from collections import Counter
from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.shortcuts import render

from ..decorators import vendor_login_required
from ..models import OrderDispute, OrderReview, SaleOrder
from ..utils import vendor_perf_rules as rules
from .vendor_access import get_vendor_profile
from .views_vendor_tools import _day_start, _report_range

MAX_TIMED_ROWS = 5000       # prep-time ke liye ek muddat mein zyada se zyada itne orders parhe jate hain


def _reason_label(text):
    """'Item out of stock. note...' -> 'Item out of stock' (wajah ka pehla hissa)."""
    text = (text or '').strip()
    return (text.split('. ')[0].rstrip('.') or 'Other')[:60]


def perf_metrics(vendor, a, b):
    """[a, b) muddat mein is vendor ke orders ka performance (dict). a, b = aware datetimes."""
    orders = SaleOrder.objects.filter(vendor=vendor, order_date__gte=a, order_date__lt=b)

    has_reason = ~Q(reject_reason='')
    agg = orders.aggregate(
        total=Count('id'),
        cancelled=Count('id', filter=Q(status='cancelled')),
        accepted=Count('id', filter=~Q(status__in=['pending', 'cancelled'])),
        pending=Count('id', filter=Q(status='pending')),
        rejected=Count('id', filter=Q(status='cancelled', vendor_responded_at__isnull=False) & has_reason),
        missed=Count('id', filter=Q(status='cancelled', vendor_responded_at__isnull=True) & has_reason),
    )
    total = agg['total'] or 0

    # Prep time: bataya hua (accept par) vs asal (accept se ready tak)
    promised, actual, on_time, late = [], [], 0, 0
    timed = (orders.filter(accepted_at__isnull=False, ready_at__isnull=False, prep_minutes__isnull=False)
             .values_list('accepted_at', 'ready_at', 'prep_minutes')[:MAX_TIMED_ROWS])
    for accepted_at, ready_at, prep_minutes in timed:
        minutes = (ready_at - accepted_at).total_seconds() / 60.0
        if minutes < 0:
            continue
        promised.append(prep_minutes)
        actual.append(minutes)
        if rules.prep_on_time(prep_minutes, minutes):
            on_time += 1
        else:
            late += 1
    prep_n = len(actual)

    rating = OrderReview.objects.filter(vendor=vendor, vendor_rating__isnull=False,
                                        created_at__gte=a, created_at__lt=b
                                        ).aggregate(avg=Avg('vendor_rating'), n=Count('id'))
    disputes = OrderDispute.objects.filter(vendor=vendor, created_at__gte=a, created_at__lt=b).count()

    m = {
        'orders': total,
        'cancelled': agg['cancelled'] or 0,
        'accepted': agg['accepted'] or 0,
        'pending': agg['pending'] or 0,
        'rejected': agg['rejected'] or 0,
        'missed': agg['missed'] or 0,
        'cancel_rate': rules.percent(agg['cancelled'] or 0, total),
        'prep_n': prep_n,
        'prep_late': late,
        'prep_promised_min': round(sum(promised) / prep_n, 1) if prep_n else None,
        'prep_actual_min': round(sum(actual) / prep_n, 1) if prep_n else None,
        'prep_on_time_pct': rules.percent(on_time, prep_n),
        'rating': round(float(rating['avg']), 1) if rating['avg'] else None,
        'rating_n': rating['n'] or 0,
        'disputes': disputes,
    }
    m['accept_rate'] = rules.accept_rate(m['accepted'], m['rejected'], m['missed'])
    m['score'] = rules.quality_score(m)
    return m


@vendor_login_required
def vendor_my_performance(request):
    profile = get_vendor_profile(request.user)
    vendor = profile.vendor
    key, start, end = _report_range(request)
    a, b = _day_start(start), _day_start(end + timedelta(days=1))

    now_m = perf_metrics(vendor, a, b)

    # Pichhli barabar muddat (jaise aaj ke muqable kal; 7 din ke muqable pichhle 7 din)
    span = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span - 1)
    prev_m = perf_metrics(vendor, _day_start(prev_start), _day_start(prev_end + timedelta(days=1)))

    # Reject ki wajahen (top 3)
    reasons = Counter(_reason_label(r) for r in SaleOrder.objects.filter(
        vendor=vendor, order_date__gte=a, order_date__lt=b, status='cancelled',
        vendor_responded_at__isnull=False).exclude(reject_reason='').values_list('reject_reason', flat=True))
    top_reasons = [{'label': k, 'n': v} for k, v in reasons.most_common(3)]

    label, tone = rules.score_label(now_m['score'])
    return render(request, 'customer_portal/vendor/performance.html', {
        'profile': profile,
        'range_key': key, 'start': start, 'end': end,
        'm': now_m,
        'score_label': label, 'score_tone': tone,
        'score_delta': rules.delta(now_m['score'], prev_m['score']),
        'accept_delta': rules.delta(now_m['accept_rate'], prev_m['accept_rate']),
        'cancel_delta': rules.delta(now_m['cancel_rate'], prev_m['cancel_rate']),
        'prev_orders': prev_m['orders'],
        'prep_promised_txt': rules.fmt_minutes(now_m['prep_promised_min']),
        'prep_actual_txt': rules.fmt_minutes(now_m['prep_actual_min']),
        'top_reasons': top_reasons,
        'tips': rules.tips(now_m),
        'min_orders': rules.MIN_ORDERS,
        'grace_min': rules.PREP_GRACE_MIN,
    })

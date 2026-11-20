"""Rider kaam kar sakta hai ya nahi: approval, documents ki expiry aur (optional) booked shift.

DB wala hissa; hisaab ke qanoon rider_docs.py aur shifts.py (pure) mein hain.
"""
from datetime import timedelta

from django.utils import timezone

from ..shop_flags import shop_flag
from . import rider_docs, shifts

GRACE_MINUTES = 15


def setting_int(name, default):
    from .offers import setting_decimal
    return int(setting_decimal(name, str(default)))


def local_now():
    """Naive local waqt (shifts bhi naive local hain)."""
    return timezone.localtime().replace(tzinfo=None)


def doc_eval(rider):
    docs = [{'kind': d.kind, 'status': d.status, 'expiry': d.expiry} for d in rider.documents.all()]
    return rider_docs.evaluate(docs, timezone.localdate())


def doc_warnings(rider):
    """Rider ko dikhane ke liye: expire / jald expire hone wale documents."""
    if not rider.documents.exists():
        return []
    ev = doc_eval(rider)
    out = [f'⛔ {rider_docs.KIND_LABELS[k]} has expired — please upload a new one.' for k in ev['expired']]
    out += [f'⚠️ {rider_docs.KIND_LABELS[k]} expires soon.' for k in ev['expiring']]
    return out


def booked_windows(rider, around=None):
    """Rider ki booked shifts ke (shuru, khatam), kal se kal tak (aadhi raat wali shifts ke liye)."""
    from ..models import RiderShiftBooking
    today = (around or local_now()).date()
    qs = (RiderShiftBooking.objects.filter(rider=rider, status='booked',
                                           shift__date__gte=today - timedelta(days=1),
                                           shift__date__lte=today + timedelta(days=1))
          .select_related('shift'))
    return [shifts.bounds(b.shift.date, b.shift.start_time, b.shift.end_time) for b in qs]


def next_shift(rider):
    """Abhi chal rahi ya agli booked shift: {'start','end','live'} ya None."""
    if not shop_flag('rider_shift_booking_enabled'):
        return None
    from ..models import RiderShiftBooking
    now = local_now()
    b = (RiderShiftBooking.objects.filter(rider=rider, status='booked', shift__date__gte=now.date() - timedelta(days=1))
         .select_related('shift').order_by('shift__date', 'shift__start_time'))
    wins = [shifts.bounds(x.shift.date, x.shift.start_time, x.shift.end_time) for x in b[:20]]
    w = shifts.next_window(wins, now)
    return {'start': w[0], 'end': w[1], 'live': w[0] <= now <= w[1]} if w else None


def work_status(rider):
    """(ok, message). ok=False ho to rider Online nahi ja sakta, offers nahi dekhta, accept nahi kar sakta."""
    st = rider.approval_status
    if st == 'pending':
        return False, '⏳ Your account is under review. Upload your documents; you can go Online after approval.'
    if st == 'rejected':
        return False, '❌ Your application was rejected' + (f': {rider.approval_note}' if rider.approval_note else '.') + ' Please upload your documents again or contact the admin.'
    if st == 'suspended':
        return False, '⛔ Your account is suspended' + (f': {rider.approval_note}' if rider.approval_note else '.') + ' Please contact the admin.'
    if shop_flag('rider_documents_required'):
        ev = doc_eval(rider) if rider.documents.exists() else None
        if ev:
            bad = rider_docs.blocking(ev)
            if bad:
                names = ', '.join(rider_docs.KIND_LABELS[k] for k in bad)
                return False, f'⛔ These documents are expired or rejected: {names}. Please upload new ones on the Documents page.'
    if shop_flag('rider_shift_booking_enabled') and shop_flag('rider_shift_required_to_go_online'):
        if not shifts.in_shift(booked_windows(rider), local_now(), GRACE_MINUTES):
            return False, '🗓️ You have no booked shift right now. Book a shift on the Shifts page.'
    return True, ''

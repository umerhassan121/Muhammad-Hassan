"""Rider onboarding (documents + admin approval) aur shift booking - Talabat Bahrain jaisa.

Rider: /shop/rider/documents/  (upload)       /shop/rider/shifts/  (book / cancel)
Admin: /shop/rider/manage/<id>/review/ (approve/reject)   /shop/rider/manage/shifts/ (shifts banana)
Documents sirf is view ke zariye khulte hain (rider khud ya admin); URL kabhi seedha nahi diya jata.
"""
import mimetypes
import re
from datetime import datetime, timedelta

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.timezone import now
from django.views.decorators.http import require_POST

from ..models import RiderDocument, RiderShift, RiderShiftBooking, RiderProfile
from ..shop_flags import flag_required, shop_flag
from . import goals, rider_docs, rider_gate, shifts, store_orders
from .views_rider_portal import _admin_only, _rider_ctx, rider_login_required

MAX_DOC_BYTES = 8 * 1024 * 1024
NUMBER_RE = re.compile(r'^[A-Za-z0-9\-/ ]{3,40}$')
DAYS_AHEAD = 7
ADMIN_DAYS = 14


# ------------------------------------------------------------------ helpers
def _clean_doc_file(f):
    """JPG/PNG/WebP tasveer ya PDF, 8 MB tak. Galat ho to ValueError (rider ke liye saaf message)."""
    if not f:
        raise ValueError('Please choose a file.')
    if f.size > MAX_DOC_BYTES:
        raise ValueError('The file is too large (max 8 MB).')
    head = f.read(5)
    f.seek(0)
    if head == b'%PDF-':
        return f
    try:
        from PIL import Image
        img = Image.open(f)
        img.verify()
        fmt = (img.format or '').upper()
        f.seek(0)
    except Exception:
        raise ValueError('Only an image (JPG/PNG/WebP) or a PDF is allowed.')
    if fmt not in ('JPEG', 'PNG', 'WEBP', 'MPO'):
        raise ValueError('Only an image (JPG/PNG/WebP) or a PDF is allowed.')
    return f


def _parse_date(raw):
    try:
        return datetime.strptime((raw or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


def _notify(user, title, message, link=None, kind='info'):
    store_orders._notify(user, title, message, link, kind)


def _maybe_auto_approve(rider, admin_user):
    """Pending rider ke saare zaroori documents approved hon to rider approved."""
    if rider.approval_status != 'pending':
        return False
    if not rider_gate.doc_eval(rider)['complete']:
        return False
    rider.approval_status = 'approved'
    rider.approval_note = ''
    rider.approved_at = now()
    rider.is_active = True      # approve hone par login/Online ke liye account chalu bhi ho
    rider.save(update_fields=['approval_status', 'approval_note', 'approved_at', 'is_active'])
    _notify(rider.user, '✅ You are approved', 'All your documents are approved. You can now go Online.',
            '/shop/rider/', 'success')
    return True


# ------------------------------------------------------------------ rider: documents
@rider_login_required
def rider_documents(request):
    rider = request.user.rider_profile
    if request.method == 'POST':
        kind = request.POST.get('kind', '')
        label = rider_docs.KIND_LABELS.get(kind)
        error = None
        number = (request.POST.get('number') or '').strip()
        expiry = _parse_date(request.POST.get('expiry'))
        if not label:
            error = 'Invalid document type.'
        elif kind in rider_docs.NEEDS_NUMBER and not NUMBER_RE.match(number):
            error = f'{label}: enter a number (3-40 letters or digits).'
        elif kind in rider_docs.NEEDS_EXPIRY and not expiry:
            error = f'{label}: choose the expiry date.'
        elif kind in rider_docs.NEEDS_EXPIRY and expiry <= timezone.localdate():
            error = f'{label} has expired. Please upload a new document.'
        if not error:
            try:
                f = _clean_doc_file(request.FILES.get('file'))
            except ValueError as exc:
                error = str(exc)
        if error:
            messages.error(request, '❌ ' + error)
            return redirect('rider_documents')
        with transaction.atomic():
            doc = RiderDocument.objects.select_for_update().filter(rider=rider, kind=kind).first()
            if doc:
                old = doc.file
                doc.file = f
                doc.number = number if kind in rider_docs.NEEDS_NUMBER else ''
                doc.expiry = expiry if kind in rider_docs.NEEDS_EXPIRY else None
                doc.status, doc.reject_reason, doc.reviewed_by, doc.reviewed_at = 'pending', '', None, None
                doc.save()
                try:
                    old.storage.delete(old.name)     # purani file hata do (naya record save ho chuka)
                except Exception:
                    pass
            else:
                RiderDocument.objects.create(
                    rider=rider, kind=kind, file=f,
                    number=number if kind in rider_docs.NEEDS_NUMBER else '',
                    expiry=expiry if kind in rider_docs.NEEDS_EXPIRY else None)
        # rad hui application wali rider dobara upload kare to dobara review mein
        if rider.approval_status == 'rejected':
            RiderProfile.objects.filter(pk=rider.pk).update(approval_status='pending', approval_note='')
        messages.success(request, f'✅ {label} uploaded. The admin will review it.')
        return redirect('rider_documents')

    docs = {d.kind: d for d in rider.documents.all()}
    today = timezone.localdate()
    items = []
    for kind, label, needs_exp, needs_num in rider_docs.KINDS:
        d = docs.get(kind)
        items.append({'kind': kind, 'label': label, 'needs_exp': needs_exp, 'needs_num': needs_num, 'doc': d,
                      'expired': bool(d and d.expiry and d.expiry < today),
                      'expiring': bool(d and d.expiry and today <= d.expiry <= today + timedelta(days=rider_docs.SOON_DAYS))})
    ev = rider_gate.doc_eval(rider)
    return render(request, 'customer_portal/rider/documents.html', _rider_ctx(
        request, 'documents', items=items, ev=ev, approval=rider.approval_status,
        approval_note=rider.approval_note, min_date=(today + timedelta(days=1)).isoformat()))


def rider_document_file(request, pk):
    """Document dikhana: sirf uska apna rider ya admin. Baqi ko 404 (andaza lagane se bachao)."""
    doc = get_object_or_404(RiderDocument.objects.select_related('rider'), pk=pk)
    u = request.user
    if not u.is_authenticated or not (u.is_superuser or doc.rider.user_id == u.id):
        raise Http404
    try:
        fh = doc.file.open('rb')
    except Exception:
        raise Http404
    ctype = mimetypes.guess_type(doc.file.name)[0] or 'application/octet-stream'
    resp = FileResponse(fh, content_type=ctype)
    resp['Content-Disposition'] = 'inline'
    resp['Cache-Control'] = 'private, no-store'
    resp['X-Content-Type-Options'] = 'nosniff'
    return resp


# ------------------------------------------------------------------ admin: review
@_admin_only
def rider_review(request, pk):
    rider = get_object_or_404(RiderProfile.objects.select_related('user'), pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action in ('doc_approve', 'doc_reject'):
            doc = get_object_or_404(RiderDocument, pk=request.POST.get('doc_id') or 0, rider=rider)
            label = rider_docs.KIND_LABELS.get(doc.kind, doc.kind)
            if action == 'doc_approve':
                doc.status, doc.reject_reason = 'approved', ''
                _notify(rider.user, f'✅ {label} approved', 'Your document has been approved.', '/shop/rider/documents/', 'success')
            else:
                reason = (request.POST.get('reason') or '').strip()[:200]
                if not reason:
                    messages.error(request, '❌ Enter the reason for rejection.')
                    return redirect('rider_review', pk=rider.pk)
                doc.status, doc.reject_reason = 'rejected', reason
                _notify(rider.user, f'❌ {label} rejected', f'Reason: {reason}. Please upload a new one.', '/shop/rider/documents/', 'warning')
            doc.reviewed_by, doc.reviewed_at = request.user, now()
            doc.save(update_fields=['status', 'reject_reason', 'reviewed_by', 'reviewed_at'])
            promoted = _maybe_auto_approve(rider, request.user)
            messages.success(request, f'{label}: {doc.get_status_display()}' + (' — rider approved ✅' if promoted else ''))
        elif action in ('rider_approve', 'rider_reject', 'rider_suspend', 'rider_pending'):
            note = (request.POST.get('note') or '').strip()[:200]
            new = {'rider_approve': 'approved', 'rider_reject': 'rejected',
                   'rider_suspend': 'suspended', 'rider_pending': 'pending'}[action]
            if new in ('rejected', 'suspended') and not note:
                messages.error(request, '❌ Enter a reason.')
                return redirect('rider_review', pk=rider.pk)
            rider.approval_status = new
            rider.approval_note = note if new in ('rejected', 'suspended') else ''
            rider.approved_at = now() if new == 'approved' else rider.approved_at
            fields = ['approval_status', 'approval_note', 'approved_at']
            if new == 'approved' and not rider.is_active:
                rider.is_active = True      # warna approved rider login hi nahi kar sakta (list mein 'New — approval pending' rehta tha)
                fields.append('is_active')
            if new != 'approved' and rider.is_online:
                rider.is_online = False
                fields.append('is_online')
            rider.save(update_fields=fields)
            _notify(rider.user, {'approved': '✅ You are approved', 'rejected': '❌ Application rejected',
                                 'suspended': '⛔ Account suspended', 'pending': '📄 Documents needed again'}[new],
                    note or 'See the app for details.', '/shop/rider/documents/',
                    'success' if new == 'approved' else 'warning')
            messages.success(request, f'{rider.name}: {rider.get_approval_status_display()}')
        return redirect('rider_review', pk=rider.pk)

    today = timezone.localdate()
    docs = {d.kind: d for d in rider.documents.all()}
    items = [{'kind': k, 'label': label, 'doc': docs.get(k),
              'expired': bool(docs.get(k) and docs[k].expiry and docs[k].expiry < today),
              'required': k in rider_docs.REQUIRED}
             for k, label, _e, _n in rider_docs.KINDS]
    return render(request, 'customer_portal/rider/review.html', {
        'rider': rider, 'items': items, 'ev': rider_gate.doc_eval(rider)})


# ------------------------------------------------------------------ rider: shifts
def _week_booked_count(rider, d, exclude_shift_id=None):
    ws = goals.week_start(d)
    qs = RiderShiftBooking.objects.filter(rider=rider, status='booked',
                                          shift__date__gte=ws, shift__date__lt=ws + timedelta(days=7))
    if exclude_shift_id:
        qs = qs.exclude(shift_id=exclude_shift_id)
    return qs.count()


@rider_login_required
@flag_required('rider_shift_booking_enabled', redirect_to='rider_home')
def rider_shifts(request):
    rider = request.user.rider_profile
    n = rider_gate.local_now()
    today = n.date()
    shs = list(RiderShift.objects.filter(date__gte=today - timedelta(days=1), date__lte=today + timedelta(days=DAYS_AHEAD))
               .annotate(booked_n=Count('bookings', filter=Q(bookings__status='booked'))))
    mine = {b.shift_id for b in RiderShiftBooking.objects.filter(rider=rider, status='booked', shift__in=shs)}
    cancel_hours = rider_gate.setting_int('rider_shift_cancel_hours', 2)
    approved = rider.approval_status == 'approved'
    days = {}
    my_list = []
    for s in shs:
        start, end = shifts.bounds(s.date, s.start_time, s.end_time)
        if end < n:
            continue
        is_mine = s.id in mine
        if is_mine:
            state = 'mine'
        elif not s.is_open:
            state = 'closed'
        elif start <= n:
            state = 'started'
        elif s.booked_n >= s.capacity:
            state = 'full'
        else:
            state = 'open'
        card = {'shift': s, 'start': start, 'end': end, 'left': max(0, s.capacity - s.booked_n), 'state': state,
                'can_cancel': is_mine and shifts.can_cancel(start, n, cancel_hours)}
        days.setdefault(s.date, []).append(card)
        if is_mine:
            my_list.append(card)
    mx = rider_gate.setting_int('rider_shift_max_per_week', 0)
    return render(request, 'customer_portal/rider/shifts.html', _rider_ctx(
        request, 'shifts', days=sorted(days.items()), my_list=my_list, approved=approved,
        week_count=_week_booked_count(rider, today), week_max=mx, cancel_hours=cancel_hours,
        required=shop_flag('rider_shift_required_to_go_online')))


@rider_login_required
@flag_required('rider_shift_booking_enabled', redirect_to='rider_home')
@require_POST
def rider_shift_book(request, pk):
    rider = request.user.rider_profile
    try:
        if rider.approval_status != 'approved':
            raise ValueError('You must be approved before you can book a shift.')
        n = rider_gate.local_now()
        with transaction.atomic():
            shift = RiderShift.objects.select_for_update().filter(pk=pk).first()
            if not shift:
                raise ValueError('Shift not found.')
            start, end = shifts.bounds(shift.date, shift.start_time, shift.end_time)
            if not shift.is_open:
                raise ValueError('This shift is closed.')
            if start <= n:
                raise ValueError('This shift has already started.')
            booking = RiderShiftBooking.objects.filter(shift=shift, rider=rider).first()
            if booking and booking.status == 'booked':
                raise ValueError('You have already booked this shift.')
            for w in rider_gate.booked_windows(rider, around=datetime.combine(shift.date, shift.start_time)):
                if shifts.overlaps((start, end), w):
                    raise ValueError('You already have another shift at this time.')
            mx = rider_gate.setting_int('rider_shift_max_per_week', 0)
            if mx and _week_booked_count(rider, shift.date) >= mx:
                raise ValueError(f"You have reached this week's limit ({mx} shifts).")
            if shift.bookings.filter(status='booked').count() >= shift.capacity:
                raise ValueError('This shift is full.')
            if booking:
                booking.status, booking.cancelled_at = 'booked', None
                booking.save(update_fields=['status', 'cancelled_at'])
            else:
                RiderShiftBooking.objects.create(shift=shift, rider=rider)
        messages.success(request, f'✅ Shift booked: {shift.date:%d %b} {shift.start_time:%H:%M}–{shift.end_time:%H:%M}')
    except ValueError as exc:
        messages.error(request, f'❌ {exc}')
    return redirect('rider_shifts')


@rider_login_required
@flag_required('rider_shift_booking_enabled', redirect_to='rider_home')
@require_POST
def rider_shift_cancel(request, pk):
    rider = request.user.rider_profile
    booking = RiderShiftBooking.objects.select_related('shift').filter(shift_id=pk, rider=rider, status='booked').first()
    if not booking:
        messages.error(request, '❌ Booking not found.')
        return redirect('rider_shifts')
    s = booking.shift
    hours = rider_gate.setting_int('rider_shift_cancel_hours', 2)
    start, _end = shifts.bounds(s.date, s.start_time, s.end_time)
    if not shifts.can_cancel(start, rider_gate.local_now(), hours):
        messages.error(request, f'❌ A shift can only be cancelled up to {hours} hours before it starts.')
        return redirect('rider_shifts')
    booking.status, booking.cancelled_at = 'cancelled', now()
    booking.save(update_fields=['status', 'cancelled_at'])
    messages.success(request, '✅ Shift cancelled.')
    return redirect('rider_shifts')


# ------------------------------------------------------------------ admin: shifts
@_admin_only
def rider_shift_admin(request):
    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'generate':
            try:
                start = _parse_date(request.POST.get('start_date'))
                days = int(request.POST.get('days') or 0)
                cap = int(request.POST.get('capacity') or 0)
                if not start or not 1 <= days <= 14 or not 1 <= cap <= 500:
                    raise ValueError('Enter a valid date, number of days (1-14) and capacity (1-500).')
                slots = shifts.parse_slots(request.POST.get('slots'))
                zone = (request.POST.get('zone') or '').strip()[:60]
                made = 0
                for i in range(days):
                    for st, et in slots:
                        _o, created = RiderShift.objects.get_or_create(
                            date=start + timedelta(days=i), start_time=st, end_time=et, zone=zone,
                            defaults={'capacity': cap})
                        made += 1 if created else 0
                messages.success(request, f'✅ {made} new shifts created.')
            except ValueError as exc:
                messages.error(request, f'❌ {exc}')
        else:
            s = get_object_or_404(RiderShift, pk=request.POST.get('shift_id') or 0)
            if action == 'toggle':
                s.is_open = not s.is_open
                s.save(update_fields=['is_open'])
            elif action == 'capacity':
                try:
                    cap = int(request.POST.get('capacity') or 0)
                except ValueError:
                    cap = 0
                booked = s.bookings.filter(status='booked').count()
                if not 1 <= cap <= 500 or cap < booked:
                    messages.error(request, f'❌ Capacity cannot be lower than the {booked} already booked, and must be valid.')
                else:
                    s.capacity = cap
                    s.save(update_fields=['capacity'])
            elif action == 'delete':
                for b in s.bookings.filter(status='booked').select_related('rider__user'):
                    _notify(b.rider.user, '🗓️ Shift cancelled',
                            f'{s.date:%d %b} {s.start_time:%H:%M}–{s.end_time:%H:%M} shift was removed by the admin.',
                            '/shop/rider/shifts/', 'warning')
                s.delete()
                messages.success(request, '🗑️ Shift deleted (booked riders were notified).')
        return redirect('rider_shift_admin')

    today = timezone.localdate()
    shs = list(RiderShift.objects.filter(date__gte=today, date__lte=today + timedelta(days=ADMIN_DAYS))
               .prefetch_related('bookings__rider'))
    days = {}
    for s in shs:
        s.riders = [b.rider.name for b in s.bookings.all() if b.status == 'booked']
        s.booked_n = len(s.riders)
        days.setdefault(s.date, []).append(s)
    return render(request, 'customer_portal/rider/shift_admin.html', {
        'days': sorted(days.items()), 'today': today.isoformat()})

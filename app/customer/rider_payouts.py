"""Rider payout request: rider apni kamai nikalne ki darkhwast bhejta hai, admin Paid / Reject karta hai.

Hisaab: nikal sakne wali raqam = kamai ka baqi (due) - rider ke paas COD cash - pehle se pending request.
(COD cash rider ke paas company ka paisa hai, is liye kamai se pehle wohi barabar hota hai.)
Paid karne par ek RiderSettlement(kind='payout') banti hai, yani purana earnings/payout hisaab wahi rehta hai.
Ek rider ki ek waqt mein sirf ek pending request (database constraint bhi hai).
Settings: rider_payout_min (default 5).
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

CENT = Decimal('0.01')
ZERO = Decimal('0.00')
MAX_AMOUNT = Decimal('99999999.99')


class PayoutError(Exception):
    """Rider/admin ko seedha dikhai ja sakne wali ghalti."""


def min_amount():
    from .offers import setting_decimal
    return max(setting_decimal('rider_payout_min', '5'), Decimal('0.01'))


def available_amount(due, cash_in_hand, pending):
    """Pure hisaab: kabhi minus nahi."""
    v = Decimal(due or 0) - max(Decimal(cash_in_hand or 0), ZERO) - Decimal(pending or 0)
    return max(v, ZERO).quantize(CENT, ROUND_HALF_UP)


def parse_amount(raw):
    try:
        v = Decimal(str(raw).replace(',', '').strip())
        if not v.is_finite():
            raise InvalidOperation
        v = v.quantize(CENT, ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise PayoutError('Enter a valid amount.')
    if v <= 0 or v > MAX_AMOUNT:
        raise PayoutError('The amount must be more than zero.')
    return v


def pending_amount(rider):
    return Decimal(rider.payout_requests.filter(status='pending').aggregate(t=Sum('amount'))['t'] or 0)


def summary(rider):
    """Rider ke page ke liye: {'due','cash','pending','available','min'}."""
    from .views_rider_portal import rider_balances
    b = rider_balances(rider)
    pend = pending_amount(rider)
    return {'due': b['due'], 'cash': b['cash_in_hand'], 'pending': pend,
            'available': available_amount(b['due'], b['cash_in_hand'], pend), 'min': min_amount()}


def create_request(rider, raw_amount, method, account_title, account_no, note=''):
    from ..models import RiderPayoutRequest, RiderProfile
    methods = dict(RiderPayoutRequest.METHODS)
    if method not in methods:
        raise PayoutError('Choose how you want to be paid.')
    account_title = ' '.join((account_title or '').split())[:100]
    account_no = ''.join((account_no or '').split()).upper()[:50]
    if method != 'cash' and (len(account_title) < 3 or len(account_no) < 4):
        raise PayoutError('Enter the account holder name and account number / IBAN.')
    amount = parse_amount(raw_amount)
    with transaction.atomic():
        RiderProfile.objects.select_for_update().get(pk=rider.pk)     # do tabs se double request na ho
        if rider.approval_status != 'approved':
            raise PayoutError('Your account is not approved.')
        if rider.payout_requests.filter(status='pending').exists():
            raise PayoutError('You already have a pending request. Wait until it is handled.')
        s = summary(rider)
        if amount < s['min']:
            raise PayoutError(f"The minimum request is Rs. {s['min']:,.0f}.")
        if amount > s['available']:
            raise PayoutError(f"You can request up to Rs. {s['available']:,.2f} right now.")
        try:
            with transaction.atomic():
                return RiderPayoutRequest.objects.create(
                    rider=rider, amount=amount, method=method,
                    account_title='' if method == 'cash' else account_title,
                    account_no='' if method == 'cash' else account_no,
                    note=(note or '').strip()[:200])
        except IntegrityError:
            raise PayoutError('You already have a pending request.')


def cancel_request(rider, pk):
    from ..models import RiderPayoutRequest
    with transaction.atomic():
        req = RiderPayoutRequest.objects.select_for_update().filter(pk=pk, rider=rider).first()
        if req is None:
            raise PayoutError('Request not found.')
        if req.status != 'pending':
            raise PayoutError('This request can no longer be cancelled.')
        req.status = 'cancelled'
        req.reviewed_at = timezone.now()
        req.save(update_fields=['status', 'reviewed_at'])
        return req


def _tell_rider(req, title, message):
    try:
        from . import store_orders
        store_orders._notify(req.rider.user, title, message, '/shop/rider/earnings/',
                             'success' if req.status == 'paid' else 'warning')
    except Exception:
        import logging
        logging.getLogger(__name__).exception('rider payout notify failed')


def mark_paid(request_id, admin_user, reference_no):
    """Admin ne paise bhej diye: RiderSettlement(payout) banao aur request 'paid' karo (ek transaction mein)."""
    from ..models import RiderPayoutRequest, RiderSettlement
    from .views_rider_portal import rider_balances
    reference_no = (reference_no or '').strip()[:100]
    if not reference_no:
        raise PayoutError('Enter the transaction reference (or "cash").')
    with transaction.atomic():
        req = RiderPayoutRequest.objects.select_for_update().select_related('rider', 'rider__user').get(pk=request_id)
        if req.status != 'pending':
            raise PayoutError('This request is already handled.')
        due = rider_balances(req.rider)['due']
        if req.amount > due:
            raise PayoutError(f'The rider earnings balance (Rs. {due:,.2f}) is now less than the request. Reject it or ask for a new one.')
        st = RiderSettlement.objects.create(
            rider=req.rider, kind='payout', amount=req.amount, created_by=admin_user,
            note=f'Payout request #{req.pk} ({req.get_method_display()}) ref {reference_no}'[:200])
        req.status, req.settlement = 'paid', st
        req.reference_no = reference_no
        req.reviewed_by, req.reviewed_at = admin_user, timezone.now()
        req.save(update_fields=['status', 'settlement', 'reference_no', 'reviewed_by', 'reviewed_at'])
    _tell_rider(req, f'💰 Payout sent: Rs. {req.amount:,.0f}', f'Reference: {reference_no}')
    return req


def reject(request_id, admin_user, reason):
    from ..models import RiderPayoutRequest
    reason = (reason or '').strip()[:200]
    if not reason:
        raise PayoutError('Write the reason (the rider will see it).')
    with transaction.atomic():
        req = RiderPayoutRequest.objects.select_for_update().select_related('rider', 'rider__user').get(pk=request_id)
        if req.status != 'pending':
            raise PayoutError('This request is already handled.')
        req.status, req.reject_reason = 'rejected', reason
        req.reviewed_by, req.reviewed_at = admin_user, timezone.now()
        req.save(update_fields=['status', 'reject_reason', 'reviewed_by', 'reviewed_at'])
    _tell_rider(req, 'Payout request rejected', reason)
    return req

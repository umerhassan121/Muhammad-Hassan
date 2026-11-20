"""Rider ko tip: delivery ke baad customer apne wallet se tip deta hai (ek order par ek hi dafa).

Tip rider ki kamai (earnings / payout) mein jama hoti hai. Wallet se paisa kat'ta hai (WalletTransaction kind='tip'),
is liye alag payment gateway nahi chahiye. Sab raqam rider ko milti hai.
"""
from decimal import Decimal

from django.db import IntegrityError, transaction

from ..shop_flags import shop_flag
from .offers import CENT, setting_decimal, wallet_balance
from .wallet_funds import parse_amount

PRESETS = (20, 50, 100)
DEFAULT_MAX = Decimal('1000')


class TipError(Exception):
    pass


def enabled():
    return shop_flag('rider_tips_enabled') and shop_flag('shop_wallet_enabled')


def max_tip():
    m = setting_decimal('rider_tip_max', str(DEFAULT_MAX))
    return m if m > 0 else DEFAULT_MAX


def validate_amount(raw, maximum=None):
    """'50' -> Decimal('50.00'). Galat, 0, ya hadd se zyada ho to TipError."""
    amt = parse_amount(raw)
    if amt is None:
        raise TipError('Please enter a valid tip amount.')
    maximum = maximum or max_tip()
    if amt > maximum:
        raise TipError(f'The maximum tip is Rs. {maximum:,.0f}.')
    return amt.quantize(CENT)


def give_tip(order, customer, rider, raw_amount):
    """Wallet se tip kato aur RiderTip likho. Return RiderTip. Galat ho to TipError."""
    from ..models import Customer, RiderTip, WalletTransaction
    amt = validate_amount(raw_amount)
    try:
        with transaction.atomic():
            locked = Customer.objects.select_for_update().get(pk=customer.pk)   # do tabs se double-spend na ho
            if RiderTip.objects.filter(sale_order=order).exists():
                raise TipError('You have already tipped the rider for this order.')
            bal = wallet_balance(locked)
            if bal < amt:
                raise TipError(f'Your wallet balance (Rs. {bal:,.0f}) is less than the tip.')
            tip = RiderTip.objects.create(sale_order=order, rider=rider, customer=locked, amount=amt)
            WalletTransaction.objects.create(customer=locked, amount=-amt, kind='tip', order=order,
                                             note=f'Tip for rider {rider.name} - order #{order.order_no}')
            return tip
    except IntegrityError:
        raise TipError('You have already tipped the rider for this order.')

"""Marketplace alerts ke pure rules (Django ka koi import nahi - seedha test ho sakte hain).

Scheduled command (python manage.py marketplace_alerts) in functions se faisla leti hai:
kab manager/admin ko escalate karna hai, document expiry ka kaunsa milestone hai, shift reminder ka waqt.
"""
from datetime import date

MANAGER_AFTER_MIN = 5      # vendor ne itni der jawab nahi diya -> store manager ko
ADMIN_AFTER_MIN = 10       # itni der -> admin ko
DOC_MILESTONES = (30, 7, 0)  # document expiry se itne din pehle yaad dihani
SHIFT_LEAD_MIN = 30        # shift shuru hone se itne minute pehle reminder
CASH_REPEAT_HOURS = 6      # rider cash alert dobara itni der baad


def escalation_levels(expire_min=0, manager_min=MANAGER_AFTER_MIN, admin_min=ADMIN_AFTER_MIN):
    """(manager_at, admin_at) minute. Agar order khud cancel ho jata hai (expire_min > 0) to escalation
    uss se pehle honi chahiye warna kabhi nahi chalegi: manager = expire-2, admin = expire-1 (kam se kam 1/2)."""
    manager, admin = int(manager_min), int(admin_min)
    if expire_min and expire_min > 0:
        manager = min(manager, max(int(expire_min) - 2, 1))
        admin = min(admin, max(int(expire_min) - 1, manager + 1))
    if admin <= manager:
        admin = manager + 1
    return manager, admin


def escalation_stage(age_min, expire_min=0, manager_min=MANAGER_AFTER_MIN, admin_min=ADMIN_AFTER_MIN):
    """Pending order ki umar (minute) se: None | 'manager' | 'admin'."""
    if age_min is None:
        return None
    manager, admin = escalation_levels(expire_min, manager_min, admin_min)
    if age_min >= admin:
        return 'admin'
    if age_min >= manager:
        return 'manager'
    return None


def expiry_milestone(expiry, today, milestones=DOC_MILESTONES):
    """Document expiry (date) ke liye: None (abhi kuch nahi) | 'expired' | milestone (30 / 7 / 0).
    Sab se chhota lagoo milestone milta hai (5 din bache to 7)."""
    if expiry is None:
        return None
    left = (expiry - today).days
    if left < 0:
        return 'expired'
    for m in sorted(milestones):
        if left <= m:
            return m
    return None


def expiry_when(milestone):
    """Text: 'today' / 'in 7 days' / 'in 30 days'."""
    if milestone == 0:
        return 'today'
    return f'in {milestone} days'


def date_key(d):
    """Group key ke liye chhota date (YYMMDD) - naya document upload ho to alert phir se chal sake."""
    return d.strftime('%y%m%d') if isinstance(d, date) else ''


def shift_reminder_due(minutes_to_start, lead=SHIFT_LEAD_MIN):
    return minutes_to_start is not None and 0 < minutes_to_start <= lead

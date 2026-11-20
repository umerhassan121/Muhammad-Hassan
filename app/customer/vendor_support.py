"""Vendor support: FAQ aur ticket ka hisaab (views sirf form/POST ka kaam karte hain).

Ticket ka safar: vendor ticket kholta hai (open) -> admin jawab deta hai (answered) ->
vendor jawab de to dobara open -> koi bhi close kar sakta hai; vendor dobara khol sakta hai.
"""
import logging

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_OPEN_TICKETS = 5
MAX_SUBJECT = 120
MAX_BODY = 2000


class SupportError(Exception):
    """A clear reason shown to the vendor."""


FAQ = [
    ('Orders', [
        ('How do I accept a new order?',
         'On the Orders page, press Accept on the new order and enter the preparation time. Press Ready as soon as it is ready, '
         'so the customer and the rider know the right time.'),
        ('Can I reject an order?',
         'Yes. Press Reject and choose a reason (item finished, store closed, etc.). Rejecting often lowers your accept rate and '
         'store quality score.'),
        ('How do I assign a rider?',
         'After marking the order Ready, choose your own rider or the shop rider with "Assign rider" on the Orders page.'),
    ]),
    ('Payments', [
        ('When will I receive my money?',
         'The amount of new sales is held for a few days (for customer returns and disputes), and until the rider deposits the COD cash '
         'the amount of that order is also held. Check the "Available to withdraw" amount on the Payouts page and send a request.'),
        ('How do I save my account for payouts?',
         'On the Payouts page, enter the method, account holder name and number under "Payout account". For safety, your password '
         'is asked again.'),
        ('Where can I see the commission details?',
         'Download a PDF statement for any month or your own dates from the Statements page: sales, commission, VAT, '
         'payments made and the balance are all in it.'),
    ]),
    ('Menu and store', [
        ('How do I turn an item off temporarily?',
         'Use the on/off switch of the item on the Menu or Products page. A sold-out item is not shown to customers.'),
        ('How do I change my store timing?',
         'Day-wise timing, minimum order and delivery fee are set in Store settings. To stop right away, use Busy mode '
         'to pause new orders for a while.'),
        ('Why is my new product not showing?',
         'If admin approval is required, a new or edited product is not live until it is approved. '
         'If it takes long, open a support ticket.'),
    ]),
    ('Account', [
        ('How do I add staff or a branch?',
         'Create a manager or orders-only staff from the Staff page. Add a new branch and copy products from the Branches page.'),
        ('Where do I upload documents?',
         'Upload your CR, owner ID, bank proof etc. on the Documents page. The admin will tell you once they approve.'),
    ]),
]


def _clean(text, limit, label):
    text = (text or '').strip()
    if not text:
        raise SupportError(f'{label} is required.')
    if len(text) > limit:
        raise SupportError(f'{label} is too long (at most {limit} characters).')
    return text


def _admin_link(ticket):
    try:
        from django.urls import reverse
        return reverse('admin:app_supportticket_change', args=[ticket.pk])
    except Exception:
        return None


def _notify_staff(ticket, title, message):
    try:
        from app.models import Notification
        Notification.send_to_all(title, message, notification_type='info', link=_admin_link(ticket))
    except Exception:
        logger.exception('support: staff notification failed (ticket=%s)', ticket.pk)


def _notify_vendor(ticket, title, message):
    try:
        from app.models import Notification
        from .vendor_access import notify_users
        for u in notify_users(ticket.profile):
            Notification.send(user=u, title=title, message=message, notification_type='info',
                              link=f'/shop/vendor/support/{ticket.pk}/')
    except Exception:
        logger.exception('support: vendor notification failed (ticket=%s)', ticket.pk)


@transaction.atomic
def create_ticket(profile, user, subject, category, body):
    from app.models import SupportMessage, SupportTicket
    subject = _clean(subject, MAX_SUBJECT, 'Mauzu (subject)')
    body = _clean(body, MAX_BODY, 'Tafseel')
    if category not in dict(SupportTicket.CATEGORY_CHOICES):
        category = 'other'
    if open_count(profile) >= MAX_OPEN_TICKETS:
        raise SupportError(f'You already have {MAX_OPEN_TICKETS} tickets open. Please close or resolve old ones first.')
    ticket = SupportTicket.objects.create(profile=profile, created_by=user, subject=subject, category=category)
    SupportMessage.objects.create(ticket=ticket, author=user, is_admin=False, body=body)
    _notify_staff(ticket, f'New support ticket {ticket.number}',
                  f'{profile.business_name}: {subject}')
    return ticket


@transaction.atomic
def vendor_reply(ticket, user, body):
    from app.models import SupportMessage
    if ticket.is_closed:
        raise SupportError('This ticket is closed. Reopen it first to reply.')
    body = _clean(body, MAX_BODY, 'Paigham')
    SupportMessage.objects.create(ticket=ticket, author=user, is_admin=False, body=body)
    ticket.status = 'open'
    ticket.vendor_unread = False
    ticket.save(update_fields=['status', 'vendor_unread', 'updated_at'])
    _notify_staff(ticket, f'Vendor replied on {ticket.number}',
                  f'{ticket.profile.business_name}: {ticket.subject}')


@transaction.atomic
def close_ticket(ticket):
    if ticket.is_closed:
        return
    ticket.status = 'closed'
    ticket.closed_at = timezone.now()
    ticket.save(update_fields=['status', 'closed_at', 'updated_at'])


@transaction.atomic
def reopen_ticket(ticket):
    if not ticket.is_closed:
        return
    if open_count(ticket.profile) >= MAX_OPEN_TICKETS:
        raise SupportError(f'You already have {MAX_OPEN_TICKETS} tickets open.')
    ticket.status = 'open'
    ticket.closed_at = None
    ticket.save(update_fields=['status', 'closed_at', 'updated_at'])
    _notify_staff(ticket, f'Ticket {ticket.number} reopened',
                  f'{ticket.profile.business_name}: {ticket.subject}')


def mark_seen(ticket):
    if ticket.vendor_unread:
        ticket.vendor_unread = False
        ticket.save(update_fields=['vendor_unread'])      # updated_at nahi badalta


@transaction.atomic
def admin_reply(ticket, admin_user, body, close=False):
    """Admin ka jawab. close=True ho to jawab ke saath ticket band."""
    from app.models import SupportMessage
    body = _clean(body, MAX_BODY, 'Reply')
    SupportMessage.objects.create(ticket=ticket, author=admin_user, is_admin=True, body=body)
    ticket.vendor_unread = True
    if close:
        ticket.status = 'closed'
        ticket.closed_at = timezone.now()
    else:
        ticket.status = 'answered'
    ticket.save(update_fields=['status', 'vendor_unread', 'closed_at', 'updated_at'])
    _notify_vendor(ticket, f'Support replied: {ticket.number}', ticket.subject)

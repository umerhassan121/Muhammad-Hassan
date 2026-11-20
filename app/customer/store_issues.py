"""Store par masla: rider store pohancha lekin order tayyar nahi / store band / item kam.
Store aur admin ko foran notification jati hai. Rider intezar kar sakta hai ya order wapis de sakta hai."""
from django.utils import timezone

from . import store_orders


class IssueError(Exception):
    pass


def _labels():
    from ..models import StoreIssue
    return dict(StoreIssue.REASONS)


def reasons():
    from ..models import StoreIssue
    return StoreIssue.REASONS


def open_issue(di):
    return di.store_issues.filter(resolved_at__isnull=True).first()


def report(order, di, rider, reason, note, vendor_user, admins):
    from ..models import StoreIssue
    labels = _labels()
    if reason not in labels:
        raise IssueError('Choose what the problem is.')
    note = (note or '').strip()[:200]
    if reason == 'other' and not note:
        raise IssueError('Please write the problem.')
    if di.status != 'assigned':
        raise IssueError('You can report a store problem only before you pick up the order.')
    if open_issue(di):
        raise IssueError('A problem is already reported for this order.')
    issue = StoreIssue.objects.create(delivery=di, sale_order=order, rider=rider, reason=reason, note=note)
    text = f'Rider {rider.name} is at the store for #{order.order_no}: {labels[reason]}.' + (f' {note}' if note else '')
    store_orders._notify(vendor_user, f'⚠️ Order #{order.order_no}: rider reports a problem', text,
                         '/shop/vendor/orders/?tab=active', 'warning', category='orders', priority='high')
    for a in admins:
        store_orders._notify(a, f'⚠️ Store problem #{order.order_no}', text,
                             '/shop/rider/manage/', 'warning', category='riders')
    return issue


def resolve(di):
    """Pickup ya order wapis karne par khula masla band."""
    di.store_issues.filter(resolved_at__isnull=True).update(resolved_at=timezone.now())

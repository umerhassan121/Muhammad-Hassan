"""
Marketplace alerts: vendor escalation (5 min manager / 10 min admin), late order, rider needed,
document expiry (vendor + rider), rider shift reminder, rider cash limit.

Usage:
    python manage.py marketplace_alerts              # ek baar (cron har minute)
    python manage.py marketplace_alerts --loop 30    # har 30 second mein chalta rahe
Cron example:  * * * * * cd /path/to/project && python manage.py marketplace_alerts
"""
import time

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Marketplace notifications: escalation, late orders, document expiry, shift and cash alerts'

    def add_arguments(self, parser):
        parser.add_argument('--loop', type=int, default=0, help='Itne second baad dobara (0 = ek baar)')

    def handle(self, *args, **options):
        from app.customer import marketplace_alerts
        loop = max(options['loop'], 0)
        while True:
            res = marketplace_alerts.run_all()
            def _n(v):
                return sum(v.values()) if isinstance(v, dict) else (v if isinstance(v, int) else 1)
            if not loop or any(_n(v) for v in res.values()):
                self.stdout.write(f'marketplace_alerts: {res}')
            if not loop:
                break
            time.sleep(loop)

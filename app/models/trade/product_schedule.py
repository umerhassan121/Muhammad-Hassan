"""Models: trade/product_schedule - item ka schedule (kuch ghanton / dinon ke liye hi available).

Jaise breakfast item sirf subah 7-11, ya weekend special sirf Sat-Sun. Product ka on/off (is_active) alag hai:
schedule ke bahar item shop par nazar aata hai magar order nahi ho sakta ("Abhi available nahi").
"""
from django.db import models


class ProductSchedule(models.Model):
    product = models.OneToOneField('Product', on_delete=models.CASCADE, related_name='schedule')
    avail_from = models.TimeField(null=True, blank=True, help_text="Khali = poora din")
    avail_to = models.TimeField(null=True, blank=True, help_text="Khali = poora din. Raat paar (22:00 -> 02:00) bhi chalta hai")
    days = models.CharField(max_length=7, blank=True, default='',
                            help_text="Din ke number (0=Mon ... 6=Sun), jaise 56 = Sat+Sun. Khali = har din")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Item Schedule'
        verbose_name_plural = '3.7 Item Schedules'

    def __str__(self):
        return f"{self.product_id}: {self.avail_from}-{self.avail_to} {self.days}"

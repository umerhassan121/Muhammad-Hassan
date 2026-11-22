from django.conf import settings
from django.db import models


class IncomeSource(models.Model):
    """Aamdani ka ek zariya (jaise Salary, Dukaan, Kiraya). Har user ke apne zariye hote hain.
    Raqam, tareekh, hisaab wagaira baad ke features mein is par jude ge."""

    TYPE_CHOICES = [
        ('salary', 'Salary / Job'),
        ('business', 'Business / Shop'),
        ('rent', 'Rent'),
        ('freelance', 'Freelance / Services'),
        ('investment', 'Investment / Profit'),
        ('commission', 'Commission'),
        ('other', 'Other'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='income_sources')
    name = models.CharField(max_length=100)
    source_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='other')
    notes = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_active', 'name']
        verbose_name = 'Income source'
        verbose_name_plural = 'Income sources'
        constraints = [
            models.UniqueConstraint(fields=['owner', 'name'], name='income_unique_source_name_per_owner'),
        ]

    def __str__(self):
        return self.name

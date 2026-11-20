from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    """Hybrid delivery: store ki 'delivery_by' (vendor / platform) aur admin ki platform rider fee/time."""

    dependencies = [
        ('app', '0093_scrub_otp_notifications'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendorprofile',
            name='delivery_by',
            field=models.CharField(
                choices=[('vendor', 'Own delivery (my riders)'), ('platform', 'Platform riders')],
                default='vendor', max_length=10, verbose_name='Delivery by',
                help_text='Own delivery = fee aur time vendor khud set karta hai. '
                          'Platform riders = fee aur time admin ki settings se lagte hain.'),
        ),
        migrations.AddField(
            model_name='deliverysettings',
            name='platform_delivery_fee',
            field=models.DecimalField(decimal_places=2, default=Decimal('50.00'), max_digits=8,
                                      verbose_name='Platform rider delivery fee (Rs.)'),
        ),
        migrations.AddField(
            model_name='deliverysettings',
            name='platform_fee_per_km',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=8,
                                      verbose_name='Platform fee per km (Rs.)',
                                      help_text='Free radius ke baad har extra km par. 0 = sirf fixed fee.'),
        ),
        migrations.AddField(
            model_name='deliverysettings',
            name='platform_free_radius_km',
            field=models.DecimalField(decimal_places=1, default=Decimal('0.0'), max_digits=5,
                                      verbose_name='Platform free radius (km)'),
        ),
        migrations.AddField(
            model_name='deliverysettings',
            name='platform_time_min',
            field=models.PositiveSmallIntegerField(default=30, verbose_name='Platform delivery time - min (minutes)'),
        ),
        migrations.AddField(
            model_name='deliverysettings',
            name='platform_time_max',
            field=models.PositiveSmallIntegerField(default=45, verbose_name='Platform delivery time - max (minutes)'),
        ),
    ]

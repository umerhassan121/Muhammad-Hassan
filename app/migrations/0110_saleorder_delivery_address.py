from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0109_vendor_pos_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='saleorder',
            name='delivery_address',
            field=models.TextField(blank=True, default='', verbose_name='Delivery Address'),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0110_saleorder_delivery_address'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendorprofile',
            name='pickup_prep_minutes',
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, verbose_name='Pickup ready time (min)',
                help_text='Customer pickup par itne minute mein order tayyar. Khali = auto-accept prep time.'),
        ),
        migrations.AddField(
            model_name='deliverysettings',
            name='pickup_time',
            field=models.CharField(
                blank=True, default='2-4 hours', max_length=100,
                verbose_name='Pickup Ready Time (shop ka apna maal)',
                help_text="Customer ko 'Ready for pickup in ...' mein dikhta hai, jaise 2-4 hours ya 30 min"),
        ),
    ]

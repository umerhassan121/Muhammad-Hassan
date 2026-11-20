from django.db import migrations, models


class Migration(migrations.Migration):
    """Dark store (Mart): VendorProfile.is_dark_store."""

    dependencies = [
        ('app', '0114_bigvehicle_driver_state'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendorprofile', name='is_dark_store',
            field=models.BooleanField(
                db_index=True, default=False, verbose_name='Dark store (Mart)',
                help_text='ON = company ka apna tez-delivery store: sirf platform riders, order khud qubool, '
                          'delivery time is store ka apna (10-20 min), aur shop mein sab se upar \u26a1 Mart nishan ke saath. '
                          'Stock bhi baqi sab ki tarah default warehouse se chalta hai.')),
    ]

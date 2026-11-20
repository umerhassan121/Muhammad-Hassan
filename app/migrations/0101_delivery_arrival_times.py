from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0100_rider_support_chat'),
    ]

    operations = [
        migrations.AddField(
            model_name='deliveryinfo',
            name='arrived_store_at',
            field=models.DateTimeField(blank=True, null=True, help_text='Rider store par pohanch gaya'),
        ),
        migrations.AddField(
            model_name='deliveryinfo',
            name='arrived_customer_at',
            field=models.DateTimeField(blank=True, null=True, help_text='Rider customer ke darwaze par pohanch gaya'),
        ),
    ]

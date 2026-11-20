from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    """GST (tax-inclusive): Product.gst_rate, SaleOrderItem.gst_rate, SaleOrder.gst_amount."""

    dependencies = [
        ('app', '0115_vendorprofile_is_dark_store'),
    ]

    operations = [
        migrations.AddField(
            model_name='product', name='gst_rate',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True,
                                      help_text='Khali = shop ka GST rate. 0 = tax se mustasna. Warna is product ka apna rate.',
                                      verbose_name='GST % (this product)'),
        ),
        migrations.AddField(
            model_name='saleorderitem', name='gst_rate',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=5,
                                      help_text='Order ke waqt ka GST % (is qeemat mein shamil)'),
        ),
        migrations.AddField(
            model_name='saleorder', name='gst_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12,
                                      help_text='Total mein shamil GST (qeematein tax-inclusive hain)'),
        ),
    ]

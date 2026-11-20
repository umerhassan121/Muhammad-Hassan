import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0107_product_schedule'),
    ]

    operations = [
        migrations.AddField(
            model_name='storesponsorship',
            name='daily_budget',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10,
                                      help_text='Vendor ka roz ka kharch ka hadd (clicks x per-click rate). 0 = koi hadd nahi. Hadd poori ho to store us din ke baqi hisse mein upar nahi aata.'),
        ),
        migrations.CreateModel(
            name='SponsoredDaily',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('day', models.DateField(db_index=True)),
                ('impressions', models.PositiveIntegerField(default=0)),
                ('clicks', models.PositiveIntegerField(default=0)),
                ('orders', models.PositiveIntegerField(default=0)),
                ('order_value', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('spend', models.DecimalField(decimal_places=2, default=0, max_digits=10,
                                              help_text='clicks x per-click rate (us din ka rate)')),
                ('sponsorship', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                  related_name='daily_stats', to='app.storesponsorship')),
            ],
            options={
                'verbose_name': 'Sponsored Daily Stat',
                'verbose_name_plural': 'Sponsored Daily Stats',
                'ordering': ['-day'],
                'unique_together': {('sponsorship', 'day')},
            },
        ),
    ]

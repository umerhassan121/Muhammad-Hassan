import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='IncomeSource',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('source_type', models.CharField(choices=[('salary', 'Salary / Job'), ('business', 'Business / Shop'), ('rent', 'Rent'), ('freelance', 'Freelance / Services'), ('investment', 'Investment / Profit'), ('commission', 'Commission'), ('other', 'Other')], default='other', max_length=20)),
                ('notes', models.TextField(blank=True, default='')),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='income_sources', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Income source',
                'verbose_name_plural': 'Income sources',
                'ordering': ['-is_active', 'name'],
            },
        ),
        migrations.AddConstraint(
            model_name='incomesource',
            constraint=models.UniqueConstraint(fields=('owner', 'name'), name='income_unique_source_name_per_owner'),
        ),
    ]

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('food_menu_app', '0008_items_is_available_alter_items_item_price'),
    ]

    operations = [
        migrations.AddField(
            model_name='items',
            name='created_at',
            field=models.DateField(
                auto_now_add=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
    ]

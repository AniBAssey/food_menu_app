from rest_framework import serializers

from .models import Items


# Serialize menu item fields for future REST endpoints without exposing ownership or soft-delete controls.
class ItemsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Items
        fields = (
            'id',
            'item_name',
            'item_desc',
            'item_price',
            'item_image',
            'is_available',
            'created_at',
            'category',
        )
        read_only_fields = ('id', 'created_at')
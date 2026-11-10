from django.contrib import admin
from django.utils.html import format_html

from .models import Category, CustomerMessage

admin.site.register(Category)
from .models import Items


class ItemsAdmin(admin.ModelAdmin):
    list_display = ('item_name', 'item_desc', 'item_price', 'image_preview')
    readonly_fields = ('image_preview',)

    @admin.display(description='Image')
    def image_preview(self, obj):
        if not obj or not obj.item_image_src:
            return 'No image uploaded'

        return format_html(
            '<img src="{}" alt="{}" style="display: block; width: 240px; height: 180px; '
            'border-radius: 12px; object-fit: cover;">',
            obj.item_image_src,
            obj.item_name,
        )

admin.site.register(Items, ItemsAdmin)

@admin.register(CustomerMessage)
class CustomerMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'submitted_at', 'is_read')
    list_filter = ('is_read', 'submitted_at')
    search_fields = ('name', 'email', 'message')
    readonly_fields = ('name', 'email', 'message', 'submitted_at')
    fields = ('name', 'email', 'message', 'submitted_at', 'is_read')
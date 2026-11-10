from django.db import models


class ItemQuerySet(models.QuerySet):
    def available(self):
        return self.filter(is_available=True)

    def unavailable(self):
        return self.filter(is_available=False)

    def for_user(self, user):
        return self.filter(user_name=user)

    def in_category(self, category):
        return self.filter(category=category)

    def search(self, term):
        if not term:
            return self.none()
        lookup = term.strip()
        if not lookup:
            return self.none()
        return self.filter(
            models.Q(item_name__icontains=lookup)
            | models.Q(item_desc__icontains=lookup)
        )

    def by_name(self):
        return self.order_by('item_name', 'pk')

    def by_price(self):
        return self.order_by('item_price', 'pk')

    def with_category(self):
        return self.select_related('category', 'user_name')

    def expensive_than(self, amount):
        return self.filter(item_price__gt=amount)

    def cheap_than(self, amount):
        return self.filter(item_price__lt=amount)


class ItemsManager(models.Manager.from_queryset(ItemQuerySet)):
    def get_queryset(self):
        return super().get_queryset().select_related('category', 'user_name')

    def available(self):
        return self.get_queryset().available()

    def unavailable(self):
        return self.get_queryset().unavailable()

    def for_user(self, user):
        return self.get_queryset().for_user(user)

    def search(self, term):
        return self.get_queryset().search(term)

    def by_name(self):
        return self.get_queryset().by_name()

    def by_price(self):
        return self.get_queryset().by_price()

    def in_category(self, category):
        return self.get_queryset().in_category(category)

    def get_available_items(self):
        return self.available()

    def get_items_by_category(self, category):
        return self.in_category(category)

    def get_user_items(self, user):
        return self.for_user(user)


ItemManager = ItemsManager


class CategoryQuerySet(models.QuerySet):
    def with_item_count(self):
        return self.annotate(item_count=models.Count('items'))

    def ordered_by_name(self):
        return self.order_by('name')

    def named(self, name):
        return self.filter(name__iexact=name)


class CategoryManager(models.Manager.from_queryset(CategoryQuerySet)):
    def with_item_count(self):
        return self.get_queryset().with_item_count()

    def ordered_by_name(self):
        return self.get_queryset().ordered_by_name()

    def named(self, name):
        return self.get_queryset().named(name)


class CategoryQueryManager(CategoryManager):
    pass


def get_available_items(queryset):
    return queryset.filter(is_available=True)


def get_items_by_category(queryset, category):
    return queryset.filter(category=category)


def search_items(queryset, term):
    if not term:
        return queryset.none()
    lookup = term.strip()
    if not lookup:
        return queryset.none()
    return queryset.filter(
        models.Q(item_name__icontains=lookup)
        | models.Q(item_desc__icontains=lookup)
    )
 
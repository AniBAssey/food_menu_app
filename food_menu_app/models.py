import secrets

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from .managers import CategoryManager, ItemsManager


class Category(models.Model):
    objects = CategoryManager()

    name = models.CharField(max_length=100)
    added_on = models.DateField(auto_now_add=True)

    def __str__(self):
        return self.name
    
    def get_absolute_url(self, using=None, keep_parents=False):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()

class Items(models.Model):
    objects = ItemsManager()

    user_name = models.ForeignKey(User, on_delete=models.CASCADE, default=1)
    item_name = models.CharField(max_length=200, db_index=True)
    item_desc = models.TextField()
    item_price = models.DecimalField(max_digits=10, decimal_places=2, db_index=True)
    item_image = models.ImageField(upload_to='items/', blank=True)
    is_available = models.BooleanField(default=True)
    # Store the creation date and time shown on menu cards in templates/food_menu_app/index.html.
    created_at = models.DateTimeField(auto_now_add=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='items',
    )

    is_deleted = models.BooleanField(default=False)  #soft delete flag
    deleted_at = models.DateTimeField(null=True, blank=True) #saves timestamp

    class Meta:
        verbose_name = "Item"
        verbose_name_plural = "Items"
        indexes = [  # noqa: RUF012
            models.Index(fields=['user_name', 'item_price'])
        ]

    def __str__(self):
        return self.item_name

    # @property
    # def item_image_src(self):
    #     image_name = self.item_image.name
    #     if not image_name:
    #         return ''
    #     if image_name.startswith(('http://', 'https://', 'data:image/')):
    #         return image_name
    #     return self.item_image.url

    @property
    def item_image_src(self):
        if not self.item_image:
            return ''

        image_name = str(self.item_image)
        if image_name.startswith(('http://', 'https://', 'data:image/')):
            return image_name

        return self.item_image.url.replace('/media/media/', '/media/')


class ItemRating(models.Model):
    item = models.ForeignKey(
        Items,
        on_delete=models.CASCADE,
        related_name='ratings',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='item_ratings',
    )
    score = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('item', 'user'),
                name='unique_item_rating_per_user',
            ),
            models.CheckConstraint(
                condition=models.Q(score__gte=1, score__lte=5),
                name='item_rating_score_1_to_5',
            ),
        ]

    def __str__(self):
        return f'{self.item} rated {self.score}/5 by {self.user}'


class ItemComment(models.Model):
    item = models.ForeignKey(
        Items,
        on_delete=models.CASCADE,
        related_name='comments',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='item_comments',
    )
    message = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-pk')

    def __str__(self):
        return f'Comment by {self.user} on {self.item}'


class CustomerMessage(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    message = models.TextField(max_length=2000)
    submitted_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ('is_read', '-submitted_at')

    def __str__(self):
        return f'Message from {self.name} ({self.submitted_at:%Y-%m-%d %H:%M})'


class ChatConversation(models.Model):
    session_token = models.CharField(
        max_length=64,
        unique=True,
        default=secrets.token_urlsafe,
    )
    name = models.CharField(max_length=100)
    email = models.EmailField()
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chat_conversations',
    )
    is_open = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-updated_at',)

    def __str__(self):
        return f'Chat with {self.name} ({self.email})'


class ChatMessage(models.Model):
    class Sender(models.TextChoices):
        VISITOR = 'visitor', 'Visitor'
        BOT = 'bot', 'Chatbot'
        ADMIN = 'admin', 'Staff'

    conversation = models.ForeignKey(
        ChatConversation,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    sender = models.CharField(max_length=10, choices=Sender.choices)
    message = models.CharField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    sender_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_chat_messages',
    )

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return f'{self.get_sender_display()}: {self.message[:60]}'
from django.urls import path
from . import views

# Cart URLs connect the menu buttons and header link to session cart views.
urlpatterns = [
    path('', views.index, name='index'),
    path('cart/', views.cart, name='cart'),
    path('cart/add/<int:item_id>/', views.add_to_cart, name='add-to-cart'),
    path('cart/update/<int:item_id>/', views.update_cart_quantity, name='update-cart-quantity'),
    path('cart/remove/<int:item_id>/', views.remove_from_cart, name='remove-from-cart'),
    # Connect the cart's checkout action to server-side PayPal order creation and capture.
    path('checkout/', views.checkout, name='checkout'),
    path('checkout/paypal/order/', views.create_checkout_order, name='paypal-create-order'),
    path('checkout/paypal/capture/', views.capture_checkout_order, name='paypal-capture-order'),
    path('checkout/complete/', views.checkout_complete, name='checkout-complete'),
    path('item/<int:item_id>/', views.item, name='item-detail'),
    path('item/<int:item_id>/rate/', views.rate_item, name='rate-item'),
    path('item/<int:item_id>/comments/', views.item_comments, name='item-comments'),
    path(
        'item/<int:item_id>/comments/add/',
        views.add_item_comment,
        name='add-item-comment',
    ),
    path('about/', views.about, name='about'),
    path('address/', views.address, name='address'),
    path('contact/', views.contact, name='contact'),
    path('contact/message/', views.submit_customer_message, name='customer-message'),
    path('chat/state/', views.chat_state, name='chat-state'),
    path('chat/start/', views.start_chat, name='chat-start'),
    path('chat/messages/', views.chat_messages, name='chat-messages'),
    path('chat/send/', views.send_chat_message, name='chat-send'),
    path('staff/chat/', views.chat_inbox, name='chat-inbox'),
    path(
        'staff/chat/<int:conversation_id>/messages/',
        views.staff_chat_messages,
        name='staff-chat-messages',
    ),
    path(
        'staff/chat/<int:conversation_id>/',
        views.chat_inbox_detail,
        name='chat-inbox-detail',
    ),
    path('add/', views.create_item, name='create-item'),
    path('item/<int:item_id>/edit/', views.edit_item, name='edit-item'),
    path('delete/<int:item_id>/delete/', views.delete_item, name='delete_item'),
]
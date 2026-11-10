import json
import logging
import re
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .forms import (
    ChatMessageForm,
    ChatStartForm,
    CustomerMessageForm,
    ItemCommentForm,
    ItemForm,
)
from .models import (
    ChatConversation,
    ChatMessage,
    CustomerMessage,
    ItemComment,
    ItemRating,
    Items,
)
from users.models import Profile
from .paypal import (
    PayPalAPIError,
    capture_paypal_order,
    captured_amount,
    captured_id,
    create_paypal_order,
)

logger = logging.getLogger(__name__)


# Build cart lines, a trusted server-side total, and an item/quantity snapshot shared by cart and checkout.
def _get_cart_snapshot(request):
    session_cart = request.session.get('cart', {})
    if not isinstance(session_cart, dict):
        session_cart = {}

    quantities = {}
    for item_id, quantity in session_cart.items():
        if not isinstance(item_id, str) or not item_id.isdecimal():
            continue
        if type(quantity) is not int or quantity < 1:
            continue
        quantities[int(item_id)] = quantity

    items_by_id = Items.objects.filter(
        pk__in=quantities,
        is_available=True,
        is_deleted=False,
    ).in_bulk()

    cart_items = []
    cart_total = Decimal('0.00')
    signature = []
    for item_id, quantity in quantities.items():
        item_obj = items_by_id.get(item_id)
        if item_obj is None:
            continue
        line_total = item_obj.item_price * quantity
        cart_items.append({
            'item': item_obj,
            'quantity': quantity,
            'line_total': line_total,
        })
        cart_total += line_total
        signature.append([item_id, quantity, f'{item_obj.item_price:.2f}'])

    return cart_items, cart_total, signature


# Expire a pending PayPal order whenever cart contents change, preventing stale-total payment.
def _clear_pending_paypal_order(request):
    request.session.pop('paypal_order', None)


def index(request):
    items = Items.objects.annotate(
        rating_average=Avg('ratings__score'),
        rating_count=Count('ratings'),
    ).order_by('item_name', 'pk')
    page_obj = Paginator(items, 12).get_page(request.GET.get('page'))
    for menu_item in page_obj.object_list:
        menu_item.rating_stars = (
            int(float(menu_item.rating_average) + 0.5)
            if menu_item.rating_average is not None
            else 0
        )
    logger.info('Menu list requested')
    context = {
        'title': 'Welcome to the Food Menu App!',
        'items': page_obj.object_list,
        'page_obj': page_obj,
    }
    return render(request, 'food_menu_app/index.html', context)


def item(request, item_id):
    item_obj = get_object_or_404(
        Items.objects.annotate(
            rating_average=Avg('ratings__score'),
            rating_count=Count('ratings'),
        ),
        id=item_id,
    )
    logger.info('Menu item retrieved: id=%s', item_obj.pk)
    # Record the signed-in username or anonymous visitor; mysite/middleware.py logs the request IP.
    logger.info(
        'User %s accessed item',
        request.user.get_username() or 'anonymous',
    )
    # Log the Items model's display name while debugging this detail view.
    logger.debug('Menu item name: %s', item_obj.item_name)
    user_rating = (
        ItemRating.objects.filter(
            item=item_obj,
            user=request.user,
        ).values_list('score', flat=True).first()
        if request.user.is_authenticated
        else None
    )
    item_obj.rating_stars = (
        int(float(item_obj.rating_average) + 0.5)
        if item_obj.rating_average is not None
        else 0
    )
    rating_labels = {
        1: 'Worst',
        2: 'Below average',
        3: 'Average',
        4: 'Good',
        5: 'Greatest / Excellent',
    }
    context = {
        'item': item_obj,
        'comments_count': item_obj.comments.count(),
        'user_rating': user_rating,
        'rating_choices': rating_labels.items(),
        'rating_label': rating_labels.get(user_rating),
    }
    return render(request, 'food_menu_app/detail.html', context)


@login_required(login_url='login')
@require_POST
def rate_item(request, item_id):
    item_obj = get_object_or_404(Items, pk=item_id, is_deleted=False)
    try:
        score = int(request.POST.get('score', ''))
    except (TypeError, ValueError):
        messages.error(request, 'Choose a rating from 1 to 5 stars.')
        return redirect('item-detail', item_id=item_obj.pk)

    if not 1 <= score <= 5:
        messages.error(request, 'Choose a rating from 1 to 5 stars.')
        return redirect('item-detail', item_id=item_obj.pk)

    ItemRating.objects.update_or_create(
        item=item_obj,
        user=request.user,
        defaults={'score': score},
    )
    messages.success(request, 'Your rating has been saved.')
    return redirect('item-detail', item_id=item_obj.pk)


def item_comments(request, item_id):
    item_obj = get_object_or_404(Items, pk=item_id, is_deleted=False)
    comments = item_obj.comments.select_related('user', 'user__profile')
    return render(
        request,
        'food_menu_app/item_comments.html',
        {
            'item': item_obj,
            'comments': comments,
            'form': ItemCommentForm(),
        },
    )


@login_required(login_url='login')
@require_POST
def add_item_comment(request, item_id):
    item_obj = get_object_or_404(Items, pk=item_id, is_deleted=False)
    form = ItemCommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.item = item_obj
        comment.user = request.user
        comment.save()
        messages.success(request, 'Your comment has been added.')
    else:
        messages.error(request, 'Enter a comment of 2,000 characters or fewer.')
    return redirect('item-comments', item_id=item_obj.pk)


# Display session cart contents and calculate line and order totals; paired with cart.html and the cart routes in urls.py.
def cart(request):
    cart_items, cart_total, _ = _get_cart_snapshot(request)

    return render(
        request,
        'food_menu_app/cart.html',
        {'cart_items': cart_items, 'cart_total': cart_total},
    )


# Add a selected quantity of an available item to the session cart; the quantity control is in index.html.
@require_POST
def add_to_cart(request, item_id):
    item_obj = get_object_or_404(
        Items,
        pk=item_id,
        is_available=True,
        is_deleted=False,
    )
    session_cart = request.session.get('cart', {})
    if not isinstance(session_cart, dict):
        session_cart = {}

    # Limit menu form quantities and cumulative session quantities to the 0-9 selector range in index.html.
    try:
        quantity_to_add = int(request.POST.get('quantity', '1'))
    except (TypeError, ValueError):
        quantity_to_add = 0
    if not 1 <= quantity_to_add <= 9:
        messages.error(request, 'Choose a quantity from 1 to 9.')
        return redirect('index')

    key = str(item_obj.pk)
    current_quantity = session_cart.get(key, 0)
    if type(current_quantity) is not int or current_quantity < 0:
        current_quantity = 0
    if current_quantity + quantity_to_add > 9:
        messages.error(request, 'The cart quantity for an item cannot exceed 9.')
        return redirect('cart')

    _clear_pending_paypal_order(request)
    session_cart[key] = current_quantity + quantity_to_add
    request.session['cart'] = session_cart
    messages.success(
        request,
        f'{quantity_to_add} × {item_obj.item_name} added to your cart.',
    )
    return redirect('cart')


# Set the session cart line to the selected quantity; selecting 0 removes it from cart.html.
@require_POST
def update_cart_quantity(request, item_id):
    item_obj = get_object_or_404(
        Items,
        pk=item_id,
        is_available=True,
        is_deleted=False,
    )
    try:
        quantity = int(request.POST.get('quantity', ''))
    except (TypeError, ValueError):
        messages.error(request, 'Choose a quantity from 0 to 9.')
        return redirect('cart')

    if not 0 <= quantity <= 9:
        messages.error(request, 'Choose a quantity from 0 to 9.')
        return redirect('cart')

    session_cart = request.session.get('cart', {})
    if not isinstance(session_cart, dict):
        session_cart = {}

    key = str(item_obj.pk)
    _clear_pending_paypal_order(request)
    if quantity == 0:
        session_cart.pop(key, None)
        messages.success(request, f'{item_obj.item_name} removed from your cart.')
    else:
        session_cart[key] = quantity
        messages.success(
            request,
            f'{item_obj.item_name} quantity updated to {quantity}.',
        )
    request.session['cart'] = session_cart
    return redirect('cart')


# Remove a menu item from the session cart; the POST form is in cart.html.
@require_POST
def remove_from_cart(request, item_id):
    session_cart = request.session.get('cart', {})
    if isinstance(session_cart, dict):
        _clear_pending_paypal_order(request)
        session_cart.pop(str(item_id), None)
        request.session['cart'] = session_cart
    return redirect('cart')


# Render PayPal checkout with a server-calculated total and the public sandbox client ID.
def checkout(request):
    cart_items, cart_total, _ = _get_cart_snapshot(request)
    if not cart_items:
        messages.error(request, 'Your cart is empty.')
        return redirect('cart')

    paypal_enabled = bool(
        settings.PAYPAL_CLIENT_ID
        and settings.PAYPAL_CLIENT_SECRET
        and settings.PAYPAL_MODE in ('sandbox', 'live')
    )
    return render(
        request,
        'food_menu_app/checkout.html',
        {
            'cart_items': cart_items,
            'cart_total': cart_total,
            'paypal_client_id': settings.PAYPAL_CLIENT_ID,
            'paypal_enabled': paypal_enabled,
            'paypal_mode': settings.PAYPAL_MODE,
        },
    )


# Create a PayPal order from the current server-side cart; checkout.html calls this endpoint.
@require_POST
def create_checkout_order(request):
    if not (
        settings.PAYPAL_CLIENT_ID
        and settings.PAYPAL_CLIENT_SECRET
        and settings.PAYPAL_MODE in ('sandbox', 'live')
    ):
        return JsonResponse(
            {'error': 'PayPal is not configured. Set valid credentials and mode in .env.'},
            status=503,
        )

    cart_items, cart_total, signature = _get_cart_snapshot(request)
    if not cart_items:
        return JsonResponse({'error': 'Your cart is empty.'}, status=400)

    try:
        order = create_paypal_order(cart_total)
    except PayPalAPIError as error:
        logger.warning('PayPal order creation failed: %s', error)
        return JsonResponse(
            {'error': 'PayPal could not start checkout. Please try again.'},
            status=502,
        )

    order_id = order.get('id')
    if not isinstance(order_id, str) or not order_id:
        logger.error('PayPal order creation response did not contain an order ID.')
        return JsonResponse(
            {'error': 'PayPal returned an invalid checkout response.'},
            status=502,
        )

    request.session['paypal_order'] = {
        'id': order_id,
        'amount': f'{cart_total:.2f}',
        'cart': signature,
    }
    return JsonResponse({'id': order_id})


# Verify and capture only this session's unchanged cart order; checkout.html invokes this after PayPal approval.
@require_POST
def capture_checkout_order(request):
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid payment confirmation.'}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({'error': 'Invalid payment confirmation.'}, status=400)
    order_id = payload.get('orderID')
    pending_order = request.session.get('paypal_order')
    if (
        not isinstance(order_id, str)
        or not re.fullmatch(r'[A-Za-z0-9-]{1,128}', order_id)
        or not isinstance(pending_order, dict)
        or pending_order.get('id') != order_id
    ):
        return JsonResponse({'error': 'This PayPal order is not valid for your cart.'}, status=400)

    cart_items, cart_total, signature = _get_cart_snapshot(request)
    if (
        not cart_items
        or pending_order.get('cart') != signature
        or pending_order.get('amount') != f'{cart_total:.2f}'
    ):
        _clear_pending_paypal_order(request)
        return JsonResponse(
            {'error': 'Your cart changed. Return to the cart and restart checkout.'},
            status=409,
        )

    try:
        capture = capture_paypal_order(order_id)
        amount_paid = captured_amount(capture)
    except PayPalAPIError as error:
        logger.warning('PayPal payment capture failed: %s', error)
        return JsonResponse(
            {'error': 'PayPal could not confirm payment. Please try again.'},
            status=502,
        )

    if (
        capture.get('status') != 'COMPLETED'
        or amount_paid != cart_total
    ):
        logger.error('PayPal capture did not match the expected order amount.')
        return JsonResponse(
            {'error': 'PayPal did not confirm the expected payment.'},
            status=502,
        )

    try:
        capture_id = captured_id(capture)
    except PayPalAPIError as error:
        logger.error('PayPal capture response was invalid: %s', error)
        return JsonResponse(
            {'error': 'PayPal returned an invalid payment confirmation.'},
            status=502,
        )

    request.session.pop('cart', None)
    request.session.pop('paypal_order', None)
    request.session['payment_confirmation'] = capture_id
    return JsonResponse({
        'status': 'COMPLETED',
        'redirect_url': reverse('checkout-complete'),
    })


# Show the session-bound PayPal capture receipt after successful server-verified payment.
def checkout_complete(request):
    capture_id = request.session.get('payment_confirmation')
    if not capture_id:
        return redirect('index')
    return render(
        request,
        'food_menu_app/checkout_complete.html',
        {'capture_id': capture_id},
    )


def about(request):
    return render(request, 'food_menu_app/about.html')


def address(request):
    return render(request, 'food_menu_app/address.html')


def contact(request):
    return render(request, 'food_menu_app/contact.html')


@require_POST
def submit_customer_message(request):
    form = CustomerMessageForm(request.POST)
    if form.is_valid():
        form.save()
        messages.success(
            request,
            'Thanks for reaching out. Your message has been sent to the admin.',
        )
    else:
        messages.error(
            request,
            'Please enter your name, a valid email address, and a message of 2,000 characters or fewer.',
        )
    return redirect('index')


def _chat_conversation_for_session(request):
    session_token = request.session.get('chat_session_token')
    if not session_token:
        return None
    return ChatConversation.objects.filter(session_token=session_token).first()


def _serialize_chat_messages(conversation, after_id=0):
    serialized = []
    chat_messages = conversation.messages.filter(pk__gt=after_id).select_related(
        'sender_user',
        'sender_user__profile',
        'conversation__user',
        'conversation__user__profile',
    )
    for chat_message in chat_messages:
        identity_user = chat_message.sender_user
        if chat_message.sender == ChatMessage.Sender.VISITOR:
            identity_user = identity_user or conversation.user

        if chat_message.sender == ChatMessage.Sender.BOT:
            sender_name = 'FoodMenu Assistant'
        elif identity_user:
            sender_name = identity_user.get_username()
        elif chat_message.sender == ChatMessage.Sender.VISITOR:
            sender_name = conversation.name
        else:
            sender_name = 'Staff'

        avatar_url = ''
        if identity_user:
            try:
                profile_image = identity_user.profile.profile_image
            except Profile.DoesNotExist:
                pass
            else:
                if profile_image:
                    avatar_url = profile_image.url

        serialized.append({
            'id': chat_message.pk,
            'sender': chat_message.sender,
            'sender_name': sender_name,
            'avatar_url': avatar_url,
            'message': chat_message.message,
            'created_at': chat_message.created_at.isoformat(),
        })
    return serialized


def _chat_state_payload(conversation):
    return {
        'active': True,
        'messages': _serialize_chat_messages(conversation),
    }


def _chatbot_reply(message):
    text = message.casefold()
    available_items = Items.objects.filter(
        is_available=True,
        is_deleted=False,
    ).order_by('item_name')

    for item in available_items:
        if item.item_name.casefold() in text:
            return (
                f'{item.item_name} is currently available for '
                f'${item.item_price:.2f}. {item.item_desc}'
            )

    if any(word in text for word in ('hello', 'hi', 'hey', 'good morning')):
        return (
            'Hello! I can help with menu items and prices. '
            'For anything else, our staff can reply in this chat.'
        )

    if any(word in text for word in ('menu', 'what food', 'what do you have')):
        menu_items = list(available_items[:10])
        if not menu_items:
            return 'There are no menu items available right now.'
        return 'Available now: ' + '; '.join(
            f'{item.item_name} (${item.item_price:.2f})'
            for item in menu_items
        ) + '.'

    if any(word in text for word in ('hour', 'open', 'closing time', 'close')):
        return (
            "I don't have confirmed opening hours. I've added your message "
            'to our staff inbox so a team member can reply here.'
        )

    if any(word in text for word in ('human', 'person', 'staff', 'admin')):
        return (
            "I've added your request to our staff inbox. A team member can "
            'reply here as soon as they are available.'
        )

    return (
        "I don't have a confirmed answer for that yet. Your message is "
        'available to our staff, and a team member can reply here.'
    )


@require_GET
@never_cache
def chat_state(request):
    conversation = _chat_conversation_for_session(request)
    if conversation is None:
        return JsonResponse({'active': False})
    return JsonResponse(_chat_state_payload(conversation))


@require_POST
def start_chat(request):
    form = ChatStartForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'errors': form.errors}, status=400)

    conversation = _chat_conversation_for_session(request)
    if conversation is None:
        conversation = ChatConversation.objects.create(
            name=form.cleaned_data['name'],
            email=form.cleaned_data['email'],
            user=request.user if request.user.is_authenticated else None,
        )
        request.session['chat_session_token'] = conversation.session_token
        ChatMessage.objects.create(
            conversation=conversation,
            sender=ChatMessage.Sender.BOT,
            message=(
                'Hi! I’m the FoodMenuApp assistant. Ask me about our menu '
                'or prices, or leave a message for our team.'
            ),
        )
    return JsonResponse(_chat_state_payload(conversation), status=201)


@require_GET
@never_cache
def chat_messages(request):
    conversation = _chat_conversation_for_session(request)
    if conversation is None:
        return JsonResponse({'error': 'Start a chat first.'}, status=404)
    try:
        after_id = int(request.GET.get('after', '0'))
    except ValueError:
        return JsonResponse({'error': 'Invalid message cursor.'}, status=400)
    if after_id < 0:
        return JsonResponse({'error': 'Invalid message cursor.'}, status=400)
    return JsonResponse({
        'messages': _serialize_chat_messages(conversation, after_id),
    })


@staff_member_required
@require_GET
@never_cache
def staff_chat_messages(request, conversation_id):
    conversation = get_object_or_404(ChatConversation, pk=conversation_id)
    try:
        after_id = int(request.GET.get('after', '0'))
    except ValueError:
        return JsonResponse({'error': 'Invalid message cursor.'}, status=400)
    if after_id < 0:
        return JsonResponse({'error': 'Invalid message cursor.'}, status=400)
    return JsonResponse({
        'messages': _serialize_chat_messages(conversation, after_id),
    })


@require_POST
def send_chat_message(request):
    conversation = _chat_conversation_for_session(request)
    if conversation is None:
        return JsonResponse({'error': 'Start a chat first.'}, status=404)
    if not conversation.is_open:
        return JsonResponse({'error': 'This chat has been closed.'}, status=409)

    form = ChatMessageForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'errors': form.errors}, status=400)

    visitor_message = form.cleaned_data['message']
    visitor_message_obj = ChatMessage.objects.create(
        conversation=conversation,
        sender=ChatMessage.Sender.VISITOR,
        message=visitor_message,
        sender_user=conversation.user,
    )
    ChatMessage.objects.create(
        conversation=conversation,
        sender=ChatMessage.Sender.BOT,
        message=_chatbot_reply(visitor_message),
    )
    ChatConversation.objects.filter(pk=conversation.pk).update(
        updated_at=timezone.now(),
    )
    return JsonResponse({
        'messages': _serialize_chat_messages(
            conversation,
            after_id=visitor_message_obj.pk - 1,
        ),
    }, status=201)


@staff_member_required
def chat_inbox(request):
    conversations = ChatConversation.objects.all()
    return render(
        request,
        'food_menu_app/chat_inbox.html',
        {'conversations': conversations},
    )


@staff_member_required
def chat_inbox_detail(request, conversation_id):
    conversation = get_object_or_404(ChatConversation, pk=conversation_id)
    form = ChatMessageForm()
    if request.method == 'POST':
        form = ChatMessageForm(request.POST)
        if form.is_valid():
            ChatMessage.objects.create(
                conversation=conversation,
                sender=ChatMessage.Sender.ADMIN,
                message=form.cleaned_data['message'],
                sender_user=request.user,
            )
            ChatConversation.objects.filter(pk=conversation.pk).update(
                updated_at=timezone.now(),
            )
            return redirect('chat-inbox-detail', conversation_id=conversation.pk)
    return render(
        request,
        'food_menu_app/chat_inbox_detail.html',
        {
            'conversation': conversation,
            'chat_messages': conversation.messages.all(),
            'form': form,
        },
    )


@login_required(login_url='login')
def create_item(request):
    form = ItemForm(
        request.POST if request.method == 'POST' else None,
        request.FILES or None,
    )
    if request.method == 'POST' and form.is_valid():
        item_obj = form.save(commit=False)
        item_obj.user_name = request.user
        item_obj.save()
        return redirect('item-detail', item_id=item_obj.id)

    context = {
        'form': form,
        'page_title': 'Add a menu item',
        'submit_label': 'Add item',
    }
    return render(request, 'food_menu_app/item_form.html', context)


@login_required(login_url='login')
def edit_item(request, item_id):
    item_obj = get_object_or_404(
        Items,
        id=item_id,
        user_name=request.user,
    )
    form = ItemForm(
        request.POST if request.method == 'POST' else None,
        request.FILES or None,
        instance=item_obj,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('item-detail', item_id=item_obj.id)

    context = {
        'form': form,
        'item': item_obj,
        'page_title': f'Edit {item_obj.item_name}',
        'submit_label': 'Save changes',
    }
    return render(request, 'food_menu_app/item_update_form.html', context)


@login_required(login_url='login')
def delete_item(request, item_id):
    item_obj = get_object_or_404(
        Items,
        id=item_id,
        user_name=request.user,
    )

    if request.method == 'POST':
        item_obj.delete()
        return redirect('index')

    return render(
        request,
        'food_menu_app/item_confirm_delete.html',
        {'item': item_obj},
    )
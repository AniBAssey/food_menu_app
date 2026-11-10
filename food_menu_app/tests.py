from datetime import date
from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image
from django.contrib.auth.models import AnonymousUser, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils.formats import date_format

from .models import (
    Category,
    ChatConversation,
    ChatMessage,
    CustomerMessage,
    ItemRating,
    ItemComment,
    Items,
)
from .serializers import ItemsSerializer


@override_settings(STORAGES={
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
})
class MenuAuthenticationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='menu-test-user',
            password='test-password',
        )
        self.item = Items.objects.create(
            user_name=self.user,
            item_name='Test dish',
            item_desc='A test menu item',
            item_price=12,
        )

    # Ensure the menu serializer returns public item fields but not ownership or soft-delete controls.
    def test_item_serializer_exposes_public_menu_fields_only(self):
        serialized_item = ItemsSerializer(self.item).data

        self.assertEqual(serialized_item['id'], self.item.pk)
        self.assertEqual(serialized_item['item_name'], self.item.item_name)
        self.assertEqual(serialized_item['item_desc'], self.item.item_desc)
        self.assertEqual(serialized_item['item_price'], '12.00')
        self.assertIn('category', serialized_item)
        self.assertNotIn('user_name', serialized_item)
        self.assertNotIn('is_deleted', serialized_item)
        self.assertNotIn('deleted_at', serialized_item)

    def test_menu_management_requires_login(self):
        protected_urls = (
            reverse('create-item'),
            reverse('edit-item', args=[self.item.pk]),
            reverse('delete_item', args=[self.item.pk]),
        )

        for url in protected_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(
                    response,
                    f'{reverse("login")}?next={url}',
                )

    def test_menu_browsing_remains_public(self):
        self.assertEqual(self.client.get(reverse('index')).status_code, 200)
        response = self.client.get(
            reverse('item-detail', args=[self.item.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'food_menu_app/detail.html')

    # Ensure menu cards show each item's description and creation time from Items.created_at.
    def test_menu_cards_display_item_description_and_creation_time(self):
        response = self.client.get(reverse('index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.item.item_desc)
        self.assertContains(
            response,
            date_format(self.item.created_at, 'M j, Y, g:i a'),
        )

    def test_menu_and_detail_show_average_rating_and_count(self):
        second_user = User.objects.create_user(
            username='rating-test-user',
            password='test-password',
        )
        ItemRating.objects.create(item=self.item, user=self.user, score=4)
        ItemRating.objects.create(item=self.item, user=second_user, score=5)

        menu_response = self.client.get(reverse('index'))
        detail_response = self.client.get(
            reverse('item-detail', args=[self.item.pk]),
        )

        self.assertContains(menu_response, '4.5 / 5')
        self.assertContains(menu_response, '(2 ratings)')
        self.assertContains(detail_response, '4.5 / 5')
        self.assertContains(detail_response, '(2 ratings)')

    def test_unrated_items_show_stars_without_not_rated_text(self):
        menu_response = self.client.get(reverse('index'))
        detail_response = self.client.get(
            reverse('item-detail', args=[self.item.pk]),
        )

        self.assertNotContains(menu_response, 'Not rated yet')
        self.assertNotContains(detail_response, 'Not rated yet')
        self.assertContains(menu_response, 'text-amber-200')
        self.assertContains(detail_response, 'text-amber-200')

    def test_signed_in_user_can_rate_and_update_rating(self):
        self.client.force_login(self.user)
        url = reverse('rate-item', args=[self.item.pk])

        response = self.client.post(url, {'score': '4'})
        self.assertRedirects(
            response,
            reverse('item-detail', args=[self.item.pk]),
        )
        self.assertEqual(
            ItemRating.objects.get(item=self.item, user=self.user).score,
            4,
        )

        response = self.client.post(url, {'score': '2'})
        self.assertRedirects(
            response,
            reverse('item-detail', args=[self.item.pk]),
        )
        self.assertEqual(
            ItemRating.objects.filter(item=self.item, user=self.user).count(),
            1,
        )
        self.assertEqual(
            ItemRating.objects.get(item=self.item, user=self.user).score,
            2,
        )

    def test_rating_form_uses_five_labeled_star_choices(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('item-detail', args=[self.item.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="radio" name="score"')
        self.assertEqual(response.content.count(b'name="score"'), 5)
        for label in (
            'Worst',
            'Below average',
            'Average',
            'Good',
            'Greatest / Excellent',
        ):
            with self.subTest(label=label):
                self.assertContains(response, label)

    def test_rating_requires_login_and_rejects_scores_outside_one_to_five(self):
        url = reverse('rate-item', args=[self.item.pk])
        anonymous_response = self.client.post(url, {'score': '5'})
        self.assertRedirects(
            anonymous_response,
            f'{reverse("login")}?next={url}',
        )

        self.client.force_login(self.user)
        for invalid_score in ('0', '6', 'not-a-score'):
            with self.subTest(score=invalid_score):
                response = self.client.post(url, {'score': invalid_score})
                self.assertRedirects(
                    response,
                    reverse('item-detail', args=[self.item.pk]),
                )
        self.assertFalse(ItemRating.objects.exists())

    def test_customer_comments_have_a_separate_public_page(self):
        comment_user = User.objects.create_user(
            username='comment-customer',
            password='test-password',
        )
        ItemComment.objects.create(
            item=self.item,
            user=comment_user,
            message='Fresh and delicious.',
        )

        response = self.client.get(
            reverse('item-comments', args=[self.item.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'food_menu_app/item_comments.html')
        self.assertContains(response, 'Customer comments (1)')
        self.assertContains(response, '@comment-customer')
        self.assertContains(response, 'Fresh and delicious.')

    def test_signed_in_customer_can_post_a_comment_for_an_item(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('add-item-comment', args=[self.item.pk]),
            {'message': 'Would order this again.'},
        )

        self.assertRedirects(
            response,
            reverse('item-comments', args=[self.item.pk]),
        )
        comment = ItemComment.objects.get()
        self.assertEqual(comment.item, self.item)
        self.assertEqual(comment.user, self.user)
        self.assertEqual(comment.message, 'Would order this again.')

    def test_anonymous_customer_must_log_in_to_post_comment(self):
        response = self.client.post(
            reverse('add-item-comment', args=[self.item.pk]),
            {'message': 'A customer comment'},
        )

        self.assertRedirects(
            response,
            f'{reverse("login")}?next={reverse("add-item-comment", args=[self.item.pk])}',
        )
        self.assertFalse(ItemComment.objects.exists())

    def test_menu_and_detail_pages_render_uploaded_item_image_url(self):
        image_data = BytesIO()
        Image.new('RGB', (1, 1), color='green').save(
            image_data,
            format='PNG',
        )

        with TemporaryDirectory() as media_root, override_settings(
            MEDIA_ROOT=media_root
        ):
            self.item.item_image = SimpleUploadedFile(
                'menu.png',
                image_data.getvalue(),
                content_type='image/png',
            )
            self.item.save()
            image_url = self.item.item_image.url

            for url in (
                reverse('index'),
                reverse('item-detail', args=[self.item.pk]),
            ):
                with self.subTest(url=url):
                    response = self.client.get(url)
                    self.assertContains(response, f'src="{image_url}"')

    def test_item_image_url_does_not_require_a_storage_existence_check(self):
        self.item.item_image = 'items/image-on-remote-storage.jpg'

        self.assertEqual(
            self.item.item_image_src,
            '/media/items/image-on-remote-storage.jpg',
        )

    # Verify the menu template remains safe for existing date-only database values.
    def test_menu_cards_handle_legacy_date_only_created_at_values(self):
        legacy_created_at = date(2026, 10, 10)
        self.item.created_at = legacy_created_at
        page_obj = Paginator([self.item], 12).get_page(1)

        rendered_menu = render_to_string(
            'food_menu_app/index.html',
            {
                'title': 'Menu',
                'items': page_obj.object_list,
                'page_obj': page_obj,
                'user': AnonymousUser(),
            },
        )

        self.assertIn(
            f'Added {date_format(legacy_created_at, "M j, Y")}',
            rendered_menu,
        )

    # Exercise the menu button, session quantities, cart totals, and navbar count wired through views.py.
    def test_add_to_cart_updates_session_and_displays_order_total(self):
        add_url = reverse('add-to-cart', args=[self.item.pk])

        first_response = self.client.post(add_url)
        self.assertRedirects(first_response, reverse('cart'))
        second_response = self.client.post(add_url)
        self.assertRedirects(second_response, reverse('cart'))

        response = self.client.get(reverse('cart'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['cart_count'], 2)
        self.assertContains(response, self.item.item_name)
        self.assertContains(response, '2 ×')
        self.assertContains(response, '24.00')

    # Ensure cart removal uses POST and updates the session badge and empty-cart state.
    def test_remove_from_cart_clears_item_and_cart_badge(self):
        self.client.post(reverse('add-to-cart', args=[self.item.pk]))
        cart_response = self.client.get(reverse('cart'))

        self.assertContains(cart_response, 'Remove item')
        self.assertContains(
            cart_response,
            f'action="{reverse("remove-from-cart", args=[self.item.pk])}"',
        )

        response = self.client.post(
            reverse('remove-from-cart', args=[self.item.pk])
        )

        self.assertRedirects(response, reverse('cart'))
        self.assertEqual(self.client.session['cart'], {})
        cart_response = self.client.get(reverse('cart'))
        self.assertContains(cart_response, 'Your cart is empty.')
        self.assertEqual(cart_response.context['cart_count'], 0)

    # Verify menu add quantities and cart updates accept 1-9 and use 0 to remove an item.
    def test_cart_quantity_can_be_selected_from_zero_to_nine(self):
        add_response = self.client.post(
            reverse('add-to-cart', args=[self.item.pk]),
            {'quantity': '4'},
        )
        self.assertRedirects(add_response, reverse('cart'))
        self.assertEqual(self.client.session['cart'][str(self.item.pk)], 4)

        update_response = self.client.post(
            reverse('update-cart-quantity', args=[self.item.pk]),
            {'quantity': '9'},
        )
        self.assertRedirects(update_response, reverse('cart'))
        cart_response = self.client.get(reverse('cart'))
        self.assertEqual(cart_response.context['cart_count'], 9)
        self.assertContains(cart_response, '9 ×')
        self.assertContains(cart_response, '108.00')

        zero_response = self.client.post(
            reverse('update-cart-quantity', args=[self.item.pk]),
            {'quantity': '0'},
        )
        self.assertRedirects(zero_response, reverse('cart'))
        self.assertEqual(self.client.session['cart'], {})

    # Reject quantities outside 0-9 instead of storing invalid values in the session.
    def test_cart_quantity_rejects_values_outside_allowed_range(self):
        response = self.client.post(
            reverse('update-cart-quantity', args=[self.item.pk]),
            {'quantity': '10'},
        )

        self.assertRedirects(response, reverse('cart'))
        self.assertNotIn('cart', self.client.session)

    def test_menu_views_log_requests_without_changing_responses(self):
        with self.assertLogs('food_menu_app.views', level='INFO') as logs:
            index_response = self.client.get(reverse('index'))
            item_response = self.client.get(
                reverse('item-detail', args=[self.item.pk])
            )

        self.assertEqual(index_response.status_code, 200)
        self.assertEqual(item_response.status_code, 200)
        self.assertEqual(
            [record.getMessage() for record in logs.records],
            [
                'Menu list requested',
                f'Menu item retrieved: id={self.item.pk}',
                'User anonymous accessed item',
            ],
        )

    # Verify mysite/middleware.py logs the direct client IP for each request.
    def test_request_logs_include_client_ip(self):
        client_ip = '203.0.113.17'
        username = self.user.get_username()
        self.client.force_login(self.user)

        with self.assertLogs('mysite.middleware', level='INFO') as logs:
            response = self.client.get(
                reverse('index'),
                REMOTE_ADDR=client_ip,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [record.getMessage() for record in logs.records],
            [
                (
                    f'Request started: GET /food_menu_app/ '
                    f'client_ip={client_ip} username={username}'
                ),
                (
                    'Request completed: GET /food_menu_app/ with status '
                    f'200 client_ip={client_ip} username={username}'
                ),
            ],
        )

    def test_edit_item_uses_update_form_and_saves_changes(self):
        self.client.force_login(self.user)
        url = reverse('edit-item', args=[self.item.pk])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            'food_menu_app/item_update_form.html',
        )
        self.assertContains(response, 'enctype="multipart/form-data"')

        response = self.client.post(url, {
            'item_name': 'Updated dish',
            'item_desc': 'Updated description',
            'item_price': 15,
        })

        self.assertRedirects(
            response,
            reverse('item-detail', args=[self.item.pk]),
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.item_name, 'Updated dish')
        self.assertEqual(self.item.item_price, 15)

    def test_delete_item_requires_confirmation_then_deletes(self):
        self.client.force_login(self.user)
        url = reverse('delete_item', args=[self.item.pk])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            'food_menu_app/item_confirm_delete.html',
        )
        self.assertContains(response, self.item.item_name)

        response = self.client.post(url)

        self.assertRedirects(response, reverse('index'))
        self.assertFalse(Items.objects.filter(pk=self.item.pk).exists())

    def test_create_item_assigns_current_user(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('create-item'), {
            'item_name': 'New dish',
            'item_desc': 'A freshly added dish',
            'item_price': '20.50',
        })

        created_item = Items.objects.get(item_name='New dish')
        self.assertRedirects(
            response,
            reverse('item-detail', args=[created_item.pk]),
        )
        self.assertEqual(created_item.user_name, self.user)
        self.assertEqual(created_item.item_price, Decimal('20.50'))

    def test_users_cannot_edit_or_delete_items_they_do_not_own(self):
        other_user = User.objects.create_user(
            username='another-menu-user',
            password='test-password',
        )
        self.client.force_login(other_user)

        edit_response = self.client.get(
            reverse('edit-item', args=[self.item.pk])
        )
        delete_response = self.client.get(
            reverse('delete_item', args=[self.item.pk])
        )

        self.assertEqual(edit_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)
        self.assertTrue(Items.objects.filter(pk=self.item.pk).exists())

    def test_menu_list_is_paginated(self):
        for number in range(12):
            Items.objects.create(
                user_name=self.user,
                item_name=f'Extra dish {number:02}',
                item_desc='A test menu item',
                item_price=10,
            )

        response = self.client.get(reverse('index'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['items']), 12)
        self.assertEqual(response.context['page_obj'].paginator.count, 13)
        self.assertContains(response, 'Next')

    def test_create_item_uploads_image_file(self):
        self.client.force_login(self.user)
        image_data = BytesIO()
        Image.new('RGB', (1, 1), color='green').save(
            image_data,
            format='PNG',
        )

        with TemporaryDirectory() as media_root, override_settings(
            MEDIA_ROOT=media_root
        ):
            response = self.client.post(
                reverse('create-item'),
                {
                    'item_name': 'Dish with image',
                    'item_desc': 'An item with an uploaded image',
                    'item_price': 20,
                    'item_image': SimpleUploadedFile(
                        'dish.png',
                        image_data.getvalue(),
                        content_type='image/png',
                    ),
                },
            )

            created_item = Items.objects.get(item_name='Dish with image')
            self.assertRedirects(
                response,
                reverse('item-detail', args=[created_item.pk]),
            )
            self.assertEqual(created_item.item_image.name, 'items/dish.png')
            self.assertTrue(created_item.item_image.storage.exists(
                created_item.item_image.name
            ))

    def test_item_can_be_assigned_to_category(self):
        category = Category.objects.create(name='Main courses')
        self.item.category = category
        self.item.save()

        self.assertEqual(category.items.get(pk=self.item.pk), self.item)
        self.assertEqual(str(category), 'Main courses')

    def test_deleting_category_keeps_items_uncategorized(self):
        category = Category.objects.create(name='Desserts')
        self.item.category = category
        self.item.save()

        category.delete()
        self.item.refresh_from_db()

        self.assertIsNone(self.item.category)
        self.assertTrue(Items.objects.filter(pk=self.item.pk).exists())

    # Render checkout with server-calculated prices and keep PayPal private credentials out of HTML.
    @override_settings(
        PAYPAL_CLIENT_ID='sandbox-public-client',
        PAYPAL_CLIENT_SECRET='private-test-secret',
        PAYPAL_MODE='sandbox',
    )
    def test_checkout_shows_server_cart_total_without_secret(self):
        self.client.post(
            reverse('add-to-cart', args=[self.item.pk]),
            {'quantity': '2'},
        )

        response = self.client.get(reverse('checkout'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '24.00')
        self.assertContains(response, 'sandbox-public-client')
        self.assertNotContains(response, 'private-test-secret')

    # Prevent starting checkout when PayPal credentials are unavailable.
    @override_settings(PAYPAL_CLIENT_ID='', PAYPAL_CLIENT_SECRET='', PAYPAL_MODE='sandbox')
    def test_checkout_displays_configuration_notice_when_paypal_unavailable(self):
        self.client.post(reverse('add-to-cart', args=[self.item.pk]))

        response = self.client.get(reverse('checkout'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'PayPal checkout is unavailable')
        self.assertNotContains(response, 'paypal-button-container')

    # Ensure the order amount comes from database-backed cart contents, not submitted browser values.
    @override_settings(
        PAYPAL_CLIENT_ID='public-client',
        PAYPAL_CLIENT_SECRET='private-secret',
        PAYPAL_MODE='sandbox',
    )
    @patch('food_menu_app.views.create_paypal_order')
    def test_create_paypal_order_uses_server_total(self, create_order):
        create_order.return_value = {'id': 'PAYPAL-ORDER-123'}
        self.client.post(
            reverse('add-to-cart', args=[self.item.pk]),
            {'quantity': '3'},
        )

        response = self.client.post(
            reverse('paypal-create-order'),
            data='{"amount":"0.01"}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'id': 'PAYPAL-ORDER-123'})
        create_order.assert_called_once_with(Decimal('36.00'))
        self.assertEqual(
            self.client.session['paypal_order']['amount'],
            '36.00',
        )

    # Clear the cart only after PayPal reports a completed USD capture matching the pending order.
    @override_settings(
        PAYPAL_CLIENT_ID='public-client',
        PAYPAL_CLIENT_SECRET='private-secret',
        PAYPAL_MODE='sandbox',
    )
    @patch('food_menu_app.views.capture_paypal_order')
    @patch('food_menu_app.views.create_paypal_order')
    def test_successful_paypal_capture_clears_cart_and_shows_receipt(
        self,
        create_order,
        capture_order,
    ):
        create_order.return_value = {'id': 'PAYPAL-ORDER-123'}
        capture_order.return_value = {
            'status': 'COMPLETED',
            'purchase_units': [{
                'payments': {
                    'captures': [{
                        'id': 'CAPTURE-123',
                        'amount': {
                            'currency_code': 'USD',
                            'value': '12.00',
                        },
                    }],
                },
            }],
        }
        self.client.post(reverse('add-to-cart', args=[self.item.pk]))
        self.client.post(reverse('paypal-create-order'))

        response = self.client.post(
            reverse('paypal-capture-order'),
            data='{"orderID":"PAYPAL-ORDER-123"}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'COMPLETED')
        self.assertEqual(response.json()['redirect_url'], reverse('checkout-complete'))
        self.assertNotIn('cart', self.client.session)
        self.assertEqual(self.client.session['payment_confirmation'], 'CAPTURE-123')
        self.assertContains(self.client.get(reverse('checkout-complete')), 'CAPTURE-123')
        capture_order.assert_called_once_with('PAYPAL-ORDER-123')

    # Preserve the cart and refuse receipt confirmation when the capture is incomplete or mispriced.
    @override_settings(
        PAYPAL_CLIENT_ID='public-client',
        PAYPAL_CLIENT_SECRET='private-secret',
        PAYPAL_MODE='sandbox',
    )
    @patch('food_menu_app.views.capture_paypal_order')
    @patch('food_menu_app.views.create_paypal_order')
    def test_incorrect_paypal_capture_does_not_clear_cart(
        self,
        create_order,
        capture_order,
    ):
        create_order.return_value = {'id': 'PAYPAL-ORDER-123'}
        capture_order.return_value = {
            'status': 'COMPLETED',
            'purchase_units': [{
                'payments': {
                    'captures': [{
                        'id': 'CAPTURE-123',
                        'amount': {
                            'currency_code': 'USD',
                            'value': '11.99',
                        },
                    }],
                },
            }],
        }
        self.client.post(reverse('add-to-cart', args=[self.item.pk]))
        self.client.post(reverse('paypal-create-order'))

        response = self.client.post(
            reverse('paypal-capture-order'),
            data='{"orderID":"PAYPAL-ORDER-123"}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.client.session['cart'], {str(self.item.pk): 1})
        self.assertNotIn('payment_confirmation', self.client.session)

    # Prevent capturing an order if its session cart changed after order creation.
    @override_settings(
        PAYPAL_CLIENT_ID='public-client',
        PAYPAL_CLIENT_SECRET='private-secret',
        PAYPAL_MODE='sandbox',
    )
    @patch('food_menu_app.views.capture_paypal_order')
    @patch('food_menu_app.views.create_paypal_order')
    def test_changed_cart_cannot_capture_stale_paypal_order(
        self,
        create_order,
        capture_order,
    ):
        create_order.return_value = {'id': 'PAYPAL-ORDER-123'}
        self.client.post(reverse('add-to-cart', args=[self.item.pk]))
        self.client.post(reverse('paypal-create-order'))
        self.client.post(
            reverse('update-cart-quantity', args=[self.item.pk]),
            {'quantity': '2'},
        )

        response = self.client.post(
            reverse('paypal-capture-order'),
            data='{"orderID":"PAYPAL-ORDER-123"}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        capture_order.assert_not_called()
        self.assertEqual(self.client.session['cart'][str(self.item.pk)], 2)


class CustomerMessageTests(TestCase):
    def test_chat_widget_is_available_on_menu_page(self):
        response = self.client.get(reverse('index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Chat with us')
        self.assertContains(response, reverse('chat-start'))
        self.assertContains(response, reverse('chat-send'))

    def test_customer_can_send_message_for_admin_review(self):
        response = self.client.post(
            reverse('customer-message'),
            {
                'name': 'Jordan Customer',
                'email': 'jordan@example.com',
                'message': 'Can you tell me about today’s specials?',
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('index'))
        self.assertEqual(CustomerMessage.objects.count(), 1)
        customer_message = CustomerMessage.objects.get()
        self.assertEqual(customer_message.name, 'Jordan Customer')
        self.assertEqual(customer_message.email, 'jordan@example.com')
        self.assertFalse(customer_message.is_read)
        self.assertContains(
            response,
            'Your message has been sent to the admin.',
        )

    def test_invalid_customer_message_is_not_saved(self):
        response = self.client.post(
            reverse('customer-message'),
            {
                'name': 'Jordan Customer',
                'email': 'not-an-email',
                'message': 'Please contact me.',
            },
        )

        self.assertRedirects(response, reverse('index'))
        self.assertEqual(CustomerMessage.objects.count(), 0)


class LiveChatTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='chat-menu-owner',
            password='test-password',
        )
        self.item = Items.objects.create(
            user_name=self.user,
            item_name='Test pizza',
            item_desc='A fresh tomato pizza',
            item_price=12,
        )

    def start_chat(self, client=None):
        chat_client = client or self.client
        response = chat_client.post(
            reverse('chat-start'),
            {'name': 'Taylor Customer', 'email': 'taylor@example.com'},
        )
        self.assertEqual(response.status_code, 201)
        return ChatConversation.objects.get(email='taylor@example.com')

    def test_chat_starts_and_chatbot_answers_menu_questions(self):
        conversation = self.start_chat()
        start_response = self.client.get(reverse('chat-state'))
        self.assertTrue(start_response.json()['active'])
        self.assertEqual(
            start_response.json()['messages'][0]['sender'],
            ChatMessage.Sender.BOT,
        )

        response = self.client.post(
            reverse('chat-send'),
            {'message': 'How much is the Test pizza?'},
        )

        self.assertEqual(response.status_code, 201)
        chat_messages = response.json()['messages']
        self.assertEqual(
            [message['sender'] for message in chat_messages],
            [ChatMessage.Sender.VISITOR, ChatMessage.Sender.BOT],
        )
        self.assertIn('$12.00', chat_messages[-1]['message'])
        self.assertEqual(conversation.messages.count(), 3)

    def test_chat_messages_are_scoped_to_the_visitors_session(self):
        self.start_chat()
        other_client = Client()

        response = other_client.get(reverse('chat-messages'))

        self.assertEqual(response.status_code, 404)

    def test_signed_in_visitor_username_is_attached_to_chat_messages(self):
        self.client.force_login(self.user)
        self.start_chat()

        response = self.client.post(
            reverse('chat-send'),
            {'message': 'Hello'},
        )

        self.assertEqual(response.status_code, 201)
        visitor_message = response.json()['messages'][0]
        self.assertEqual(visitor_message['sender_name'], self.user.username)
        self.assertEqual(visitor_message['avatar_url'], '')

    def test_chat_poll_requests_are_not_written_to_request_logs(self):
        self.start_chat()

        with self.assertNoLogs('mysite.middleware', level='INFO'):
            response = self.client.get(reverse('chat-messages'))

        self.assertEqual(response.status_code, 200)

    def test_staff_can_reply_and_customer_receives_reply_in_live_chat(self):
        conversation = self.start_chat()
        staff_user = User.objects.create_user(
            username='chat-staff',
            password='test-password',
            is_staff=True,
        )
        staff_client = Client()
        staff_client.force_login(staff_user)

        inbox_response = staff_client.get(reverse('chat-inbox'))
        self.assertEqual(inbox_response.status_code, 200)
        self.assertContains(inbox_response, 'Live chat inbox')
        conversation_response = staff_client.get(
            reverse('chat-inbox-detail', args=[conversation.pk]),
        )
        self.assertContains(conversation_response, 'Staff: @chat-staff')
        detail_response = staff_client.post(
            reverse('chat-inbox-detail', args=[conversation.pk]),
            {'message': 'A staff member is here to help.'},
        )

        self.assertRedirects(
            detail_response,
            reverse('chat-inbox-detail', args=[conversation.pk]),
        )
        messages_response = self.client.get(
            reverse('chat-messages'),
            {'after': 1},
        )
        self.assertEqual(messages_response.status_code, 200)
        self.assertEqual(
            messages_response.json()['messages'][-1]['sender'],
            ChatMessage.Sender.ADMIN,
        )
        self.assertEqual(
            messages_response.json()['messages'][-1]['message'],
            'A staff member is here to help.',
        )
        self.assertEqual(
            messages_response.json()['messages'][-1]['sender_name'],
            staff_user.username,
        )

    def test_non_staff_cannot_open_staff_inbox(self):
        response = self.client.get(reverse('chat-inbox'))

        self.assertEqual(response.status_code, 302)

    def test_customer_message_endpoint_rejects_get(self):
        response = self.client.get(reverse('customer-message'))

        self.assertEqual(response.status_code, 405)

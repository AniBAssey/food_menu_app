"""PayPal REST API helpers used by food_menu_app.views checkout endpoints."""

import base64
import json
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


class PayPalAPIError(Exception):
    """Represent PayPal configuration, transport, and API response failures."""


# Call PayPal's server API without exposing the client secret to checkout.html.
def paypal_api_request(path, method='POST', payload=None, access_token=None):
    client_id = settings.PAYPAL_CLIENT_ID
    client_secret = settings.PAYPAL_CLIENT_SECRET
    if not client_id or not client_secret:
        raise PayPalAPIError('PayPal sandbox credentials are not configured.')

    mode = settings.PAYPAL_MODE
    if mode not in ('sandbox', 'live'):
        raise PayPalAPIError('PAYPAL_MODE must be set to sandbox or live.')

    api_host = (
        'https://api-m.paypal.com'
        if mode == 'live'
        else 'https://api-m.sandbox.paypal.com'
    )
    headers = {'Accept': 'application/json'}
    data = None

    if access_token is None:
        credentials = base64.b64encode(
            f'{client_id}:{client_secret}'.encode('utf-8')
        ).decode('ascii')
        headers.update({
            'Authorization': f'Basic {credentials}',
            'Content-Type': 'application/x-www-form-urlencoded',
        })
        data = b'grant_type=client_credentials'
        url = f'{api_host}/v1/oauth2/token'
    else:
        headers['Authorization'] = f'Bearer {access_token}'
        url = f'{api_host}{path}'
        if payload is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(payload).encode('utf-8')

    api_request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(api_request, timeout=15) as response:
            result = json.loads(response.read().decode('utf-8'))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise PayPalAPIError('PayPal could not complete the request.') from error

    if not isinstance(result, dict):
        raise PayPalAPIError('PayPal returned an invalid response.')
    return result


# Create an OAuth-authenticated PayPal order using a server-calculated USD total.
def create_paypal_order(amount):
    token_response = paypal_api_request('/v1/oauth2/token')
    access_token = token_response.get('access_token')
    if not isinstance(access_token, str) or not access_token:
        raise PayPalAPIError('PayPal did not provide an access token.')

    return paypal_api_request(
        '/v2/checkout/orders',
        method='POST',
        payload={
            'intent': 'CAPTURE',
            'purchase_units': [{
                'amount': {
                    'currency_code': 'USD',
                    'value': f'{amount:.2f}',
                },
            }],
        },
        access_token=access_token,
    )


# Capture an approved PayPal order using server-side OAuth credentials.
def capture_paypal_order(order_id):
    token_response = paypal_api_request('/v1/oauth2/token')
    access_token = token_response.get('access_token')
    if not isinstance(access_token, str) or not access_token:
        raise PayPalAPIError('PayPal did not provide an access token.')

    return paypal_api_request(
        f'/v2/checkout/orders/{order_id}/capture',
        method='POST',
        payload={},
        access_token=access_token,
    )


# Parse the total captured by PayPal so views.py can compare it with the session order.
def captured_amount(response):
    try:
        capture = response['purchase_units'][0]['payments']['captures'][0]
        if capture['amount']['currency_code'] != 'USD':
            raise PayPalAPIError('PayPal returned an unexpected capture currency.')
        return Decimal(capture['amount']['value'])
    except PayPalAPIError:
        raise
    except (KeyError, IndexError, TypeError, ValueError):
        raise PayPalAPIError('PayPal returned an invalid capture amount.') from None


# Extract a capture identifier from PayPal's verified response for the receipt page.
def captured_id(response):
    try:
        capture_id = response['purchase_units'][0]['payments']['captures'][0]['id']
    except (KeyError, IndexError, TypeError):
        raise PayPalAPIError('PayPal returned an invalid capture ID.') from None
    if not isinstance(capture_id, str) or not capture_id:
        raise PayPalAPIError('PayPal returned an invalid capture ID.')
    return capture_id

# Expose the validated session cart count to base.html; register this processor in mysite/settings.py.
def cart_count(request):
    session_cart = request.session.get('cart', {})
    if not isinstance(session_cart, dict):
        return {'cart_count': 0}

    return {
        'cart_count': sum(
            quantity
            for quantity in session_cart.values()
            if type(quantity) is int and quantity > 0
        ),
    }

import logging

logger = logging.getLogger(__name__)

CHAT_POLL_PATHS = (
    '/food_menu_app/chat/messages/',
)


class LogRequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip database/user lookups for static and media files to prevent crashes and DB timeouts
        if request.path.startswith(('/media/', '/static/')):
            return self.get_response(request)

        is_chat_poll = (
            request.path in CHAT_POLL_PATHS
            or (
                request.path.startswith('/food_menu_app/staff/chat/')
                and request.path.endswith('/messages/')
            )
        )
        if is_chat_poll:
            return self.get_response(request)

        username = request.user.get_username() if request.user.is_authenticated else 'anonymous'
        logger.info(
            'Request started: %s %s client_ip=%s username=%s',
            request.method,
            request.path,
            request.META.get('REMOTE_ADDR'),
            username,
        )
        
        response = self.get_response(request)
        
        logger.info(
            'Request completed: %s %s with status %s client_ip=%s username=%s',
            request.method,
            request.path,
            response.status_code,
            request.META.get('REMOTE_ADDR'),
            username,
        )
        return response

# class LogRequestMiddleware:
#     # Save Django's next request handler so this middleware can pass requests through.
#     def __init__(self, get_response):
#         self.get_response = get_response

#     # Log each request and its response status while preserving normal request handling.
#     def __call__(self, request):
#         # settings.py enables this middleware and configures its logs; use the direct peer IP, not an untrusted forwarded header.
#         client_ip = request.META.get('REMOTE_ADDR', 'unknown')
#         username = request.user.get_username() if request.user.is_authenticated else 'anonymous'
#         logger.info(
#             'Request started: %s %s client_ip=%s username=%s',
#             request.method,
#             request.path,
#             client_ip,
#             username,
#         )
#         response = self.get_response(request)
#         logger.info(
#             'Request completed: %s %s with status %s client_ip=%s username=%s',
#             request.method,
#             request.path,
#             response.status_code,
#             client_ip,
#             username,
#         )
#         return response
        
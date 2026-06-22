# store/utils.py
from .models import Cart

def get_or_create_cart(request):
    """
    Return a Cart tied to request.user (if authenticated) or to session_key (anonymous).
    """
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
        return cart

    session_key = request.session.session_key
    if not session_key:
        request.session.save()
        session_key = request.session.session_key
    cart, _ = Cart.objects.get_or_create(session_key=session_key)
    return cart
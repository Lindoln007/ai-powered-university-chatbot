from . import guest
from .models import Conversation


def owned_conversations(request):
    """Conversations that belong to the requester: their account, or their guest session."""
    if request.user.is_authenticated:
        return Conversation.objects.filter(user=request.user)
    session_id = guest.get_guest_session_id(request)
    if session_id:
        return Conversation.objects.filter(user__isnull=True, guest_session_id=session_id)
    return Conversation.objects.none()

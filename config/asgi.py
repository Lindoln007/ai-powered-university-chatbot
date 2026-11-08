import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()

# Load the Sentence Transformer once per server process, in the background.
from nlp_engine.model_loader import warm_up_in_background  # noqa: E402

warm_up_in_background()

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from nlp_engine import embeddings
from nlp_engine.model_loader import ModelUnavailableError, embedding_dimension, get_model


class Command(BaseCommand):
    help = "Download (if necessary) and verify the local Sentence Transformer model."

    def handle(self, *args, **options):
        self.stdout.write(f"Model: {settings.NLP_MODEL_NAME}")
        self.stdout.write(f"Cache directory: {settings.NLP_MODEL_CACHE_DIR}")
        try:
            model = get_model()
        except ModelUnavailableError as exc:
            raise CommandError(str(exc)) from exc
        vector = embeddings.encode_one("What programmes does the university offer?")
        self.stdout.write(f"Embedding dimension: {embedding_dimension(model)}")
        self.stdout.write(f"Test embedding norm: {float((vector ** 2).sum() ** 0.5):.4f}")
        self.stdout.write(self.style.SUCCESS("The model is available locally and working."))

from django.core.management.base import BaseCommand, CommandError

from knowledge_base import services
from nlp_engine.model_loader import ModelUnavailableError


class Command(BaseCommand):
    help = "Generate missing or outdated embeddings for FAQs, alternative questions and articles."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Regenerate every embedding, even if up to date.")

    def handle(self, *args, **options):
        try:
            counts = services.refresh_all_embeddings(force=options["force"])
        except ModelUnavailableError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(", ".join(f"{name}: {count}" for name, count in counts.items()))
        self.stdout.write(self.style.SUCCESS("Embeddings are up to date."))

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from knowledge_base.importer import DatasetError, import_dataset
from nlp_engine.model_loader import ModelUnavailableError


class Command(BaseCommand):
    help = "Validate and import the university FAQ dataset (JSON) into PostgreSQL and generate embeddings."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=str(settings.BASE_DIR / "data" / "university_faqs.json"),
                            help="Path to the dataset JSON file (default: data/university_faqs.json).")
        parser.add_argument("--skip-embeddings", action="store_true",
                            help="Import records without generating embeddings (they are generated later).")

    def handle(self, *args, **options):
        path = Path(options["path"])
        self.stdout.write(f"Importing dataset from {path}")
        try:
            summary = import_dataset(path, generate_embeddings=not options["skip_embeddings"])
        except DatasetError as exc:
            raise CommandError(str(exc)) from exc
        except ModelUnavailableError as exc:
            raise CommandError(f"Records were imported, but embeddings could not be generated: {exc}") from exc

        if summary.errors:
            for error in summary.errors:
                self.stderr.write(self.style.ERROR(f"  - {error}"))
            raise CommandError(f"Validation failed with {len(summary.errors)} error(s). Nothing was imported.")

        for line in summary.lines():
            self.stdout.write(f"  {line}")
        self.stdout.write(self.style.SUCCESS("Import completed successfully."))

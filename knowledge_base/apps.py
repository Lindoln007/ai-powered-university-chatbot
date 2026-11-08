from django.apps import AppConfig


class KnowledgeBaseConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "knowledge_base"
    verbose_name = "University knowledge base"

    def ready(self):
        from nlp_engine.model_loader import register_warmup_step

        from . import services, signals  # noqa: F401

        # Build the in-memory search index during start-up instead of on the first question.
        register_warmup_step(services.get_faq_index)

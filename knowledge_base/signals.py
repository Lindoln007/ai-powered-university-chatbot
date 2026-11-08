"""Keep stored embeddings in sync with knowledge base edits.

Whenever an FAQ, alternative question or article is created or updated
(through Django Admin, the REST API or the shell) its embedding is refreshed
if the underlying text changed. Deleting a record, or changing its
publication/verification status, invalidates the in-memory search index so
outdated entries are never used.
"""

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from nlp_engine.model_loader import ModelUnavailableError

from . import services
from .models import FAQ, AlternativeQuestion, KnowledgeArticle

logger = logging.getLogger(__name__)


def _safe_refresh(refresh, instance):
    try:
        refresh(instance)
    except ModelUnavailableError as exc:
        # The record is saved without an embedding; it is embedded automatically
        # the next time the search index is built, once the model is available.
        logger.warning("Embedding for %r not refreshed: %s", instance, exc)


@receiver(post_save, sender=FAQ)
def faq_saved(sender, instance, raw=False, **kwargs):
    services.invalidate_indexes()
    if not raw and services.auto_embedding_enabled():
        _safe_refresh(services.refresh_faq_embeddings, instance)


@receiver(post_save, sender=AlternativeQuestion)
def alternative_saved(sender, instance, raw=False, **kwargs):
    services.invalidate_indexes()
    if not raw and services.auto_embedding_enabled():
        _safe_refresh(services.refresh_alternative_embedding, instance)


@receiver(post_save, sender=KnowledgeArticle)
def article_saved(sender, instance, raw=False, **kwargs):
    services.invalidate_indexes()
    if not raw and services.auto_embedding_enabled():
        _safe_refresh(services.refresh_article_embedding, instance)


@receiver(post_delete, sender=FAQ)
@receiver(post_delete, sender=AlternativeQuestion)
@receiver(post_delete, sender=KnowledgeArticle)
def knowledge_deleted(sender, instance, **kwargs):
    services.invalidate_indexes()

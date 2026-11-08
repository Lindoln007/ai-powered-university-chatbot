"""Validated, repeatable import of the knowledge base dataset (JSON).

Records are matched on their ``reference_code`` (FAQs, articles) or ``slug``
(categories), so running the import again updates existing rows instead of
creating duplicates. Alternative questions are synchronised to exactly the
list in the file for every imported FAQ.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.utils.text import slugify

from nlp_engine.intent_classifier import Intent

from . import services
from .models import (
    FAQ,
    AlternativeQuestion,
    InformationType,
    KnowledgeArticle,
    KnowledgeCategory,
    PublicationStatus,
    VerificationStatus,
)

STATUS_FIELDS = ("source_description", "source_url", "verification_status", "publication_status", "information_type")


class DatasetError(Exception):
    pass


@dataclass
class ImportSummary:
    categories_created: int = 0
    categories_updated: int = 0
    faqs_created: int = 0
    faqs_updated: int = 0
    faqs_unchanged: int = 0
    alternatives_created: int = 0
    alternatives_removed: int = 0
    articles_created: int = 0
    articles_updated: int = 0
    articles_unchanged: int = 0
    embeddings: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)

    def lines(self) -> list[str]:
        return [
            f"Categories: {self.categories_created} created, {self.categories_updated} updated",
            f"FAQs: {self.faqs_created} created, {self.faqs_updated} updated, {self.faqs_unchanged} unchanged",
            f"Alternative questions: {self.alternatives_created} created, {self.alternatives_removed} removed",
            f"Articles: {self.articles_created} created, {self.articles_updated} updated, "
            f"{self.articles_unchanged} unchanged",
            "Embeddings generated: " + (", ".join(f"{k}={v}" for k, v in self.embeddings.items()) or "skipped"),
        ]


def _validate_choice(record: dict, name: str, choices, label: str, errors: list):
    value = record.get(name)
    if value not in choices.values:
        errors.append(f"{label}: invalid {name} '{value}' (allowed: {', '.join(choices.values)})")


def _validate_text(record: dict, name: str, max_length: int | None, label: str, errors: list):
    value = record.get(name)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label}: '{name}' is required and must be non-empty text")
    elif max_length and len(value) > max_length:
        errors.append(f"{label}: '{name}' exceeds {max_length} characters")


def load_dataset(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise DatasetError(f"Dataset file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DatasetError(f"Dataset file is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("faqs"), list):
        raise DatasetError("Dataset must be a JSON object with a 'faqs' list.")
    return data


def validate_dataset(data: dict) -> tuple[list, list, list, list[str]]:
    """Return normalised (categories, faqs, articles, errors)."""
    errors: list[str] = []
    defaults = data.get("metadata", {}).get("defaults", {})
    url_validator = URLValidator()

    categories = []
    known_slugs = set(KnowledgeCategory.objects.values_list("slug", flat=True))
    for index, raw in enumerate(data.get("categories", []), start=1):
        label = f"Category #{index}"
        _validate_text(raw, "name", 120, label, errors)
        slug = raw.get("slug") or slugify(raw.get("name", ""))
        intent = raw.get("intent", "")
        if intent and intent not in Intent.LABELS:
            errors.append(f"{label}: unknown intent '{intent}'")
        categories.append({"name": raw.get("name", "").strip(), "slug": slug,
                           "description": raw.get("description", ""), "intent": intent})
        known_slugs.add(slug)

    def normalise_record(raw: dict, label: str) -> dict:
        record = {**defaults, **raw}
        if record.get("category") not in known_slugs:
            errors.append(f"{label}: unknown category '{record.get('category')}'")
        _validate_choice(record, "verification_status", VerificationStatus, label, errors)
        _validate_choice(record, "publication_status", PublicationStatus, label, errors)
        _validate_choice(record, "information_type", InformationType, label, errors)
        if (record.get("information_type") == InformationType.DEMONSTRATION
                and record.get("verification_status") == VerificationStatus.VERIFIED):
            errors.append(f"{label}: demonstration information cannot be marked as verified")
        if record.get("source_url"):
            try:
                url_validator(record["source_url"])
            except ValidationError:
                errors.append(f"{label}: invalid source_url")
        if not record.get("reference_code"):
            errors.append(f"{label}: 'reference_code' is required for repeatable imports")
        return record

    faqs, seen_codes, seen_questions = [], set(), set()
    for index, raw in enumerate(data["faqs"], start=1):
        label = f"FAQ #{index} ({raw.get('reference_code', 'no code')})"
        record = normalise_record(raw, label)
        _validate_text(record, "question", 500, label, errors)
        _validate_text(record, "answer", None, label, errors)
        code = record.get("reference_code")
        if code in seen_codes:
            errors.append(f"{label}: duplicate reference_code")
        seen_codes.add(code)
        question_key = str(record.get("question", "")).strip().lower()
        if question_key in seen_questions:
            errors.append(f"{label}: duplicate question text")
        seen_questions.add(question_key)
        alternatives = record.get("alternative_questions", [])
        keywords = record.get("keywords", [])
        if not isinstance(alternatives, list) or not all(isinstance(a, str) and a.strip() for a in alternatives):
            errors.append(f"{label}: 'alternative_questions' must be a list of non-empty strings")
            alternatives = []
        if not isinstance(keywords, list) or not all(isinstance(k, str) for k in keywords):
            errors.append(f"{label}: 'keywords' must be a list of strings")
            keywords = []
        unique_alternatives = []
        for text in alternatives:
            text = " ".join(text.split())
            if text.lower() != question_key and text not in unique_alternatives:
                unique_alternatives.append(text)
        record["alternative_questions"] = unique_alternatives
        record["keywords"] = [k.strip() for k in keywords if k.strip()]
        faqs.append(record)

    articles = []
    for index, raw in enumerate(data.get("articles", []), start=1):
        label = f"Article #{index} ({raw.get('reference_code', 'no code')})"
        record = normalise_record(raw, label)
        _validate_text(record, "title", 255, label, errors)
        _validate_text(record, "content", None, label, errors)
        articles.append(record)

    return categories, faqs, articles, errors


def _apply(instance, values: dict) -> bool:
    changed = False
    for key, value in values.items():
        if getattr(instance, key) != value:
            setattr(instance, key, value)
            changed = True
    return changed


def import_dataset(path: Path, generate_embeddings: bool = True) -> ImportSummary:
    data = load_dataset(path)
    categories, faqs, articles, errors = validate_dataset(data)
    summary = ImportSummary(errors=errors)
    if errors:
        return summary

    with services.suspend_auto_embedding(), transaction.atomic():
        category_map = {}
        for item in categories:
            category, created = KnowledgeCategory.objects.get_or_create(
                slug=item["slug"], defaults={k: v for k, v in item.items() if k != "slug"})
            if created:
                summary.categories_created += 1
            elif _apply(category, {k: v for k, v in item.items() if k != "slug"}):
                category.save()
                summary.categories_updated += 1
            category_map[item["slug"]] = category
        for category in KnowledgeCategory.objects.exclude(slug__in=category_map):
            category_map[category.slug] = category

        for record in faqs:
            values = {
                "question": record["question"].strip(),
                "answer": record["answer"].strip(),
                "category": category_map[record["category"]],
                "keywords": record["keywords"],
                **{name: record.get(name, "") or "" for name in STATUS_FIELDS},
            }
            faq = FAQ.objects.filter(reference_code=record["reference_code"]).first()
            if faq is None:
                faq = FAQ.objects.create(reference_code=record["reference_code"], **values)
                summary.faqs_created += 1
            elif _apply(faq, values):
                faq.save()
                summary.faqs_updated += 1
            else:
                summary.faqs_unchanged += 1

            existing = {alt.question_text: alt for alt in faq.alternative_questions.all()}
            for text, alternative in existing.items():
                if text not in record["alternative_questions"]:
                    alternative.delete()
                    summary.alternatives_removed += 1
            for text in record["alternative_questions"]:
                if text not in existing:
                    AlternativeQuestion.objects.create(faq=faq, question_text=text)
                    summary.alternatives_created += 1

        for record in articles:
            values = {
                "title": record["title"].strip(),
                "content": record["content"].strip(),
                "category": category_map[record["category"]],
                **{name: record.get(name, "") or "" for name in STATUS_FIELDS},
            }
            article = KnowledgeArticle.objects.filter(reference_code=record["reference_code"]).first()
            if article is None:
                KnowledgeArticle.objects.create(reference_code=record["reference_code"], **values)
                summary.articles_created += 1
            elif _apply(article, values):
                article.save()
                summary.articles_updated += 1
            else:
                summary.articles_unchanged += 1

    services.invalidate_indexes()
    if generate_embeddings:
        summary.embeddings = services.refresh_all_embeddings()
    return summary

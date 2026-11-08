"""Lightweight semantic intent detection.

Each intent is described by a handful of example phrases (configurable in
``data/intents.json``). The example phrases are embedded once with the same
Sentence Transformer; an incoming question is assigned the intent whose
example phrases it is most similar to (cosine similarity). If no intent is
similar enough, the question is classified as ``unknown``.

No separate classification model is trained, which keeps the component simple
and easy to improve later (e.g. by adding examples or replacing the class).
"""

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from django.conf import settings
from sklearn.metrics.pairwise import cosine_similarity

from . import embeddings


class Intent:
    ADMISSIONS = "admissions_enquiry"
    PROGRAMME = "programme_enquiry"
    FEES = "fees_enquiry"
    REGISTRATION = "registration_enquiry"
    EXAMINATION = "examination_enquiry"
    ACADEMIC_CALENDAR = "academic_calendar_enquiry"
    STUDENT_SERVICES = "student_services_enquiry"
    LIBRARY = "library_enquiry"
    ACCOMMODATION = "accommodation_enquiry"
    CONTACT = "contact_information_enquiry"
    GENERAL = "general_university_enquiry"
    UNKNOWN = "unknown"

    LABELS = {
        ADMISSIONS: "Admissions Enquiry",
        PROGRAMME: "Programme Enquiry",
        FEES: "Fees Enquiry",
        REGISTRATION: "Registration Enquiry",
        EXAMINATION: "Examination Enquiry",
        ACADEMIC_CALENDAR: "Academic Calendar Enquiry",
        STUDENT_SERVICES: "Student Services Enquiry",
        LIBRARY: "Library Enquiry",
        ACCOMMODATION: "Accommodation Enquiry",
        CONTACT: "Contact Information Enquiry",
        GENERAL: "General University Enquiry",
        UNKNOWN: "Unknown Intent",
    }

    @classmethod
    def choices(cls):
        return list(cls.LABELS.items())


@dataclass
class IntentResult:
    intent: str
    confidence: float
    scores: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return Intent.LABELS.get(self.intent, self.intent)


class IntentClassifier:
    def __init__(self, examples: dict[str, list[str]], threshold: float):
        unknown = [name for name in examples if name not in Intent.LABELS]
        if unknown:
            raise ValueError(f"Unknown intent names in configuration: {unknown}")
        self.examples = {name: phrases for name, phrases in examples.items() if phrases}
        self.threshold = threshold
        self._matrix = None
        self._labels: list[str] = []
        self._lock = threading.Lock()

    @classmethod
    def from_file(cls, path: Path, threshold: float) -> "IntentClassifier":
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return cls(data["intents"], threshold)

    def _ensure_index(self):
        if self._matrix is None:
            with self._lock:
                if self._matrix is None:
                    labels, phrases = [], []
                    for name, examples in self.examples.items():
                        labels.extend([name] * len(examples))
                        phrases.extend(examples)
                    self._matrix = embeddings.encode(phrases)
                    self._labels = labels

    def classify(self, query_embedding: np.ndarray) -> IntentResult:
        self._ensure_index()
        similarities = cosine_similarity(query_embedding.reshape(1, -1), self._matrix)[0]
        scores: dict[str, float] = {}
        for label, score in zip(self._labels, similarities):
            if score > scores.get(label, -1.0):
                scores[label] = float(score)
        best_intent = max(scores, key=scores.get)
        best_score = scores[best_intent]
        rounded = {name: round(value, 4) for name, value in sorted(scores.items(), key=lambda kv: -kv[1])}
        if best_score < self.threshold:
            return IntentResult(Intent.UNKNOWN, round(best_score, 4), rounded)
        return IntentResult(best_intent, round(best_score, 4), rounded)


_classifier = None
_classifier_lock = threading.Lock()


def get_intent_classifier() -> IntentClassifier:
    global _classifier
    if _classifier is None:
        with _classifier_lock:
            if _classifier is None:
                _classifier = IntentClassifier.from_file(settings.NLP_INTENTS_FILE, settings.NLP_INTENT_THRESHOLD)
    return _classifier

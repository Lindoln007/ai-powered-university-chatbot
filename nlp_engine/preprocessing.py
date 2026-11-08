"""Light-touch text preprocessing.

The Sentence Transformer was trained on natural sentences, so preprocessing
only cleans the text (whitespace, Unicode punctuation variants, repeated
punctuation, control characters). Words are never removed or stemmed because
that could change the meaning of the question before it is embedded.
"""

import re
import unicodedata
from dataclasses import dataclass

from django.conf import settings


class PreprocessingError(ValueError):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProcessedQuestion:
    original: str
    cleaned: str

    @property
    def word_count(self) -> int:
        return len(self.cleaned.split())


_PUNCTUATION_MAP = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "–": "-", "—": "-", "−": "-",
    "…": "...", " ": " ",
})
_CONTROL_CHARS = re.compile(r"[\u0000-\u0008\u000b-\u001f\u007f-\u009f​-‏﻿]")
_REPEATED_PUNCTUATION = re.compile(r"([?!.,])\1+")
_MIXED_END_PUNCTUATION = re.compile(r"[?!]{2,}")
_WHITESPACE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([?!.,;:])")
_HAS_LETTER_OR_DIGIT = re.compile(r"[^\W_]", re.UNICODE)


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_PUNCTUATION_MAP)
    text = _CONTROL_CHARS.sub(" ", text)
    text = _MIXED_END_PUNCTUATION.sub("?", text) if "?" in text else text
    text = _REPEATED_PUNCTUATION.sub(r"\1", text)
    text = _WHITESPACE.sub(" ", text).strip()
    text = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", text)
    return text


def preprocess(text, max_length: int | None = None) -> ProcessedQuestion:
    """Validate and normalise a user question. Raises PreprocessingError on invalid input."""
    if max_length is None:
        max_length = settings.CHATBOT_MAX_QUESTION_LENGTH
    if not isinstance(text, str):
        raise PreprocessingError("The question must be text.", "invalid_type")
    cleaned = normalise(text)
    if not cleaned:
        raise PreprocessingError("Please enter a question.", "empty")
    if len(cleaned) > max_length:
        raise PreprocessingError(
            f"The question is too long. Please keep it under {max_length} characters.", "too_long"
        )
    if not _HAS_LETTER_OR_DIGIT.search(cleaned):
        raise PreprocessingError("The question must contain letters or numbers.", "no_content")
    return ProcessedQuestion(original=text, cleaned=cleaned)


# ---------------------------------------------------------------------------
# Conversational helpers
# ---------------------------------------------------------------------------
_GREETINGS = re.compile(
    r"^(hi|hello|hey|hiya|greetings|good (morning|afternoon|evening)|moni|muli bwanji)( there)?( chatbot| bot)?[!.]*$",
    re.IGNORECASE,
)
_THANKS = re.compile(r"^(thanks|thank you|thank you very much|thanks a lot|zikomo|cheers|ok,? thanks)[!.]*$", re.IGNORECASE)
_GOODBYE = re.compile(r"^(bye|goodbye|see you|see you later|that'?s all)[!.]*$", re.IGNORECASE)

_FOLLOW_UP_START = re.compile(
    r"^(and|also|what about|how about|what of|and what about|and how about|then|so|plus)\b", re.IGNORECASE
)
_REFERRING_WORDS = re.compile(r"\b(it|its|it's|that|this|those|these|they|them|their|there|same)\b", re.IGNORECASE)


def detect_small_talk(cleaned: str) -> str | None:
    """Return 'greeting', 'thanks' or 'goodbye' for pure small-talk messages, else None."""
    text = cleaned.strip()
    if _GREETINGS.match(text):
        return "greeting"
    if _THANKS.match(text):
        return "thanks"
    if _GOODBYE.match(text):
        return "goodbye"
    return None


def looks_like_follow_up(cleaned: str) -> bool:
    """Heuristic: does this short message depend on the previous question for its meaning?"""
    words = cleaned.split()
    if _FOLLOW_UP_START.match(cleaned):
        return True
    return len(words) <= 8 and bool(_REFERRING_WORDS.search(cleaned))

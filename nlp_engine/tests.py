from unittest import mock

import numpy as np
from django.test import SimpleTestCase, override_settings

from . import embeddings, model_loader
from .intent_classifier import Intent, get_intent_classifier
from .preprocessing import PreprocessingError, detect_small_talk, looks_like_follow_up, preprocess
from .response_generator import FALLBACK_MESSAGE, ResponseGenerator, RetrievedKnowledge
from .semantic_search import IndexEntry, SearchHit, SemanticIndex, decide


class PreprocessingTests(SimpleTestCase):
    def test_whitespace_and_punctuation_are_normalised(self):
        result = preprocess("  How   do I\tapply ???  ")
        self.assertEqual(result.cleaned, "How do I apply?")

    def test_unicode_quotes_and_dashes_are_normalised(self):
        self.assertEqual(preprocess("What’s the fee — per year…").cleaned, "What's the fee - per year.")

    def test_original_question_is_preserved(self):
        result = preprocess("  Hello   there ")
        self.assertEqual(result.original, "  Hello   there ")

    def test_words_are_not_removed(self):
        self.assertEqual(preprocess("What is the cost of the course?").cleaned, "What is the cost of the course?")

    def test_empty_question_is_rejected(self):
        for value in ["", "    ", "\n\t"]:
            with self.assertRaises(PreprocessingError) as ctx:
                preprocess(value)
            self.assertEqual(ctx.exception.code, "empty")

    def test_question_without_letters_is_rejected(self):
        with self.assertRaises(PreprocessingError) as ctx:
            preprocess("?!?!...")
        self.assertEqual(ctx.exception.code, "no_content")

    def test_too_long_question_is_rejected(self):
        with self.assertRaises(PreprocessingError) as ctx:
            preprocess("a" * 51, max_length=50)
        self.assertEqual(ctx.exception.code, "too_long")

    def test_non_text_is_rejected(self):
        with self.assertRaises(PreprocessingError):
            preprocess(42)

    def test_small_talk_detection(self):
        self.assertEqual(detect_small_talk("Hello"), "greeting")
        self.assertEqual(detect_small_talk("thank you!"), "thanks")
        self.assertEqual(detect_small_talk("Goodbye"), "goodbye")
        self.assertIsNone(detect_small_talk("Hello, how do I apply?"))

    def test_follow_up_detection(self):
        self.assertTrue(looks_like_follow_up("What about the fees?"))
        self.assertTrue(looks_like_follow_up("How much does it cost?"))
        self.assertFalse(looks_like_follow_up("What are the admission requirements for the nursing programme?"))


class EmbeddingTests(SimpleTestCase):
    def test_embedding_has_384_dimensions_and_unit_length(self):
        vector = embeddings.encode_one("What programmes does the university offer?")
        self.assertEqual(vector.shape, (384,))
        self.assertAlmostEqual(float(np.linalg.norm(vector)), 1.0, places=4)

    def test_batch_encoding(self):
        matrix = embeddings.encode(["How do I apply?", "Where is the library?", "How do I apply?"])
        self.assertEqual(matrix.shape, (3, 384))
        np.testing.assert_allclose(matrix[0], matrix[2])

    def test_cached_texts_are_not_re_encoded(self):
        embeddings.encode_one("A sentence used to test the embedding cache.")
        with mock.patch.object(embeddings, "get_model") as get_model:
            embeddings.encode_one("A sentence used to test the embedding cache.")
            get_model.assert_not_called()

    def test_storage_round_trip(self):
        vector = embeddings.encode_one("Round trip test")
        restored = embeddings.from_storage(embeddings.to_storage(vector))
        np.testing.assert_allclose(vector, restored, atol=1e-6)

    def test_fingerprint_changes_with_text(self):
        self.assertNotEqual(embeddings.text_fingerprint("a"), embeddings.text_fingerprint("b"))
        self.assertEqual(embeddings.text_fingerprint("a"), embeddings.text_fingerprint("a"))


class SemanticSimilarityTests(SimpleTestCase):
    """The model must judge meaning, not shared words."""

    def similarity(self, a, b):
        va, vb = embeddings.encode([a, b])
        return float(np.dot(va, vb))

    def test_paraphrases_are_more_similar_than_unrelated_sentences(self):
        stored = "What programmes does the university offer?"
        paraphrase = self.similarity(stored, "Which courses can I study here?")
        unrelated = self.similarity(stored, "How do I bake a chocolate cake?")
        self.assertGreater(paraphrase, 0.45)
        self.assertLess(unrelated, 0.3)
        self.assertGreater(paraphrase, unrelated + 0.3)

    def test_admission_paraphrase(self):
        self.assertGreater(self.similarity("What are the admission requirements?",
                                           "What grades do I need to qualify?"), 0.45)


class ModelLoaderTests(SimpleTestCase):
    def test_model_is_loaded_once(self):
        self.assertIs(model_loader.get_model(), model_loader.get_model())
        self.assertTrue(model_loader.model_status()["loaded"])

    def test_missing_model_raises_clear_error(self):
        with mock.patch.object(model_loader, "_model", None), \
                mock.patch("sentence_transformers.SentenceTransformer", side_effect=OSError("not found")):
            with self.assertRaises(model_loader.ModelUnavailableError) as ctx:
                model_loader.get_model()
        self.assertIn("download_model", str(ctx.exception))

    @override_settings(NLP_OFFLINE=True)
    def test_model_runs_offline_from_local_cache(self):
        """Loading a fresh instance with network access forbidden proves no external API is needed."""
        with mock.patch.object(model_loader, "_model", None):
            model = model_loader.get_model()
            vector = model.encode(["offline check"], normalize_embeddings=True)
        self.assertEqual(vector.shape, (1, 384))


class IntentClassifierTests(SimpleTestCase):
    def test_intents_are_detected(self):
        classifier = get_intent_classifier()
        cases = {
            "How can I apply to study here?": Intent.ADMISSIONS,
            "Which degrees do you offer?": Intent.PROGRAMME,
            "How much is tuition?": Intent.FEES,
            "When does the library close?": Intent.LIBRARY,
            "Is there a hostel for first years?": Intent.ACCOMMODATION,
            "How do I check my exam results?": Intent.EXAMINATION,
            "What about the fees?": Intent.FEES,
        }
        for question, expected in cases.items():
            with self.subTest(question=question):
                self.assertEqual(classifier.classify(embeddings.encode_one(question)).intent, expected)

    def test_unrelated_question_is_unknown(self):
        result = get_intent_classifier().classify(embeddings.encode_one("How do I bake a chocolate cake?"))
        self.assertEqual(result.intent, Intent.UNKNOWN)
        self.assertEqual(result.label, "Unknown Intent")


def _unit(vector):
    vector = np.asarray(vector, dtype=np.float32)
    return vector / np.linalg.norm(vector)


class SemanticIndexTests(SimpleTestCase):
    def setUp(self):
        entries = [IndexEntry(1, "a", "question"), IndexEntry(1, "a2", "alternative"), IndexEntry(2, "b", "question")]
        matrix = np.vstack([_unit([1, 0, 0]), _unit([0.9, 0.1, 0]), _unit([0, 1, 0])])
        self.index = SemanticIndex(entries, matrix)

    def test_results_are_grouped_by_record_and_ranked(self):
        hits = self.index.search(_unit([1, 0.05, 0]), top_k=5)
        self.assertEqual([hit.key for hit in hits], [1, 2])
        self.assertEqual(hits[0].matched_text, "a")
        self.assertGreater(hits[0].score, hits[1].score)

    def test_empty_index(self):
        empty = SemanticIndex([], np.zeros((0, 3)))
        self.assertEqual(empty.search(_unit([1, 0, 0])), [])


class DecisionTests(SimpleTestCase):
    def hits(self, *scores):
        return [SearchHit(index, score, f"q{index}", "question") for index, score in enumerate(scores, start=1)]

    def test_below_threshold_is_no_match(self):
        self.assertEqual(decide(self.hits(0.40, 0.2), 0.5, 0.03, 0.75).outcome, "no_match")
        self.assertEqual(decide([], 0.5, 0.03, 0.75).outcome, "no_match")

    def test_clear_winner_is_answered(self):
        decision = decide(self.hits(0.62, 0.50), 0.5, 0.03, 0.75)
        self.assertEqual((decision.outcome, decision.best.key), ("answer", 1))

    def test_close_scores_request_clarification(self):
        decision = decide(self.hits(0.62, 0.61, 0.40), 0.5, 0.03, 0.75)
        self.assertEqual(decision.outcome, "clarification")
        self.assertEqual([hit.key for hit in decision.candidates], [1, 2])

    def test_high_confidence_skips_clarification(self):
        self.assertEqual(decide(self.hits(0.80, 0.79), 0.5, 0.03, 0.75).outcome, "answer")

    def test_intent_breaks_ties(self):
        decision = decide(self.hits(0.62, 0.61), 0.5, 0.03, 0.75, preferred_keys={2})
        self.assertEqual((decision.outcome, decision.best.key), ("answer", 2))


class ResponseGeneratorTests(SimpleTestCase):
    def knowledge(self, **overrides):
        values = dict(id=1, reference_code="X-1", question="Q?", answer="An answer.", category="Admissions",
                      information_type="demonstration", verification_status="unverified")
        values.update(overrides)
        return RetrievedKnowledge(**values)

    def test_demonstration_answers_are_labelled(self):
        response = ResponseGenerator("Test University").answer(self.knowledge())
        self.assertIn("[Demonstration information]", response.content)
        self.assertIn("not official information from Test University", response.disclaimer)
        self.assertFalse(response.is_verified)

    def test_verified_answers_have_no_disclaimer(self):
        response = ResponseGenerator("Test University").answer(
            self.knowledge(information_type="institutional", verification_status="verified"))
        self.assertIsNone(response.disclaimer)
        self.assertEqual(response.content, "An answer.")
        self.assertTrue(response.is_verified)

    def test_fallback_does_not_invent_an_answer(self):
        response = ResponseGenerator("Test University").fallback()
        self.assertEqual(response.content, FALLBACK_MESSAGE)
        self.assertFalse(response.answered)

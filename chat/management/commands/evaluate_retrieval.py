"""Evaluate semantic retrieval and choose the similarity threshold empirically.

Uses held-out paraphrases (data/evaluation_questions.json) that are NOT in the
knowledge base, plus out-of-scope questions, and reports for a range of
thresholds how many in-scope questions are answered correctly and how many
out-of-scope questions are correctly rejected.
"""

import json
from pathlib import Path

import numpy as np
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from knowledge_base import services as knowledge
from knowledge_base.models import FAQ
from nlp_engine import embeddings
from nlp_engine.intent_classifier import Intent, get_intent_classifier
from nlp_engine.model_loader import ModelUnavailableError
from nlp_engine.semantic_search import decide


class Command(BaseCommand):
    help = "Measure retrieval accuracy on held-out questions and recommend a similarity threshold."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=str(settings.BASE_DIR / "data" / "evaluation_questions.json"))
        parser.add_argument("--min", type=float, default=0.30)
        parser.add_argument("--max", type=float, default=0.70)
        parser.add_argument("--step", type=float, default=0.05)
        parser.add_argument("--verbose-errors", action="store_true", help="List misclassified questions.")

    def handle(self, *args, **options):
        with open(Path(options["path"]), encoding="utf-8") as handle:
            data = json.load(handle)
        codes = dict(FAQ.objects.values_list("reference_code", "id"))
        missing = {item["expected"] for item in data["in_scope"]} - set(codes)
        if missing:
            raise CommandError(f"Expected FAQs not in the database (run import_faqs first): {sorted(missing)}")

        try:
            in_scope = [self._rank(item["question"]) + (codes[item["expected"]], item["question"])
                        for item in data["in_scope"]]
            out_scope = [self._rank(question) + (None, question) for question in data["out_of_scope"]]
        except ModelUnavailableError as exc:
            raise CommandError(str(exc)) from exc

        top1 = sum(1 for hits, _, expected, _ in in_scope if hits and hits[0].key == expected)
        top3 = sum(1 for hits, _, expected, _ in in_scope if expected in [h.key for h in hits[:3]])
        in_scores = [hits[0].score for hits, *_ in in_scope]
        out_scores = [hits[0].score for hits, *_ in out_scope]
        self.stdout.write(f"In-scope questions: {len(in_scope)}, out-of-scope questions: {len(out_scope)}")
        self.stdout.write(f"Top-1 retrieval accuracy (no threshold): {top1}/{len(in_scope)} = {top1 / len(in_scope):.1%}")
        self.stdout.write(f"Top-3 retrieval accuracy (no threshold): {top3}/{len(in_scope)} = {top3 / len(in_scope):.1%}")
        self.stdout.write(f"Best-match score, in-scope:     mean {np.mean(in_scores):.3f}, min {np.min(in_scores):.3f}")
        self.stdout.write(f"Best-match score, out-of-scope: mean {np.mean(out_scores):.3f}, max {np.max(out_scores):.3f}")
        self.stdout.write("")
        header = f"{'threshold':>9} | {'correct':>7} {'wrong':>5} {'clarify':>7} {'fallback':>8} | {'rejected':>8} {'leaked':>6} | {'overall':>7}"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))

        best = None
        threshold = options["min"]
        while threshold <= options["max"] + 1e-9:
            row = self._evaluate(in_scope, out_scope, round(threshold, 3))
            overall = (row["correct"] + row["rejected"]) / (len(in_scope) + len(out_scope))
            self.stdout.write(
                f"{threshold:>9.2f} | {row['correct']:>7} {row['wrong']:>5} {row['clarification']:>7} "
                f"{row['fallback']:>8} | {row['rejected']:>8} {row['leaked']:>6} | {overall:>7.1%}"
            )
            # Prefer the threshold with the best overall score; on ties prefer fewer wrong answers.
            key = (overall, -row["wrong"] - row["leaked"])
            if best is None or key > best[0]:
                best = (key, threshold, row)
            threshold += options["step"]

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Recommended CHATBOT_SIMILARITY_THRESHOLD = {best[1]:.2f} "
            f"(current setting: {settings.CHATBOT_SIMILARITY_THRESHOLD:.2f})"
        ))
        if options["verbose_errors"]:
            self._print_errors(in_scope, out_scope, settings.CHATBOT_SIMILARITY_THRESHOLD)

    def _rank(self, question: str):
        vector = embeddings.encode_one(question)
        intent = get_intent_classifier().classify(vector)
        return knowledge.search_faqs(vector), intent

    def _decide(self, hits, intent, threshold):
        faqs = knowledge.load_faqs([hit.key for hit in hits])
        preferred = {key for key, faq in faqs.items()
                     if intent.intent != Intent.UNKNOWN and faq.category.intent == intent.intent}
        return decide(hits, threshold, settings.CHATBOT_CLARIFICATION_MARGIN, settings.CHATBOT_HIGH_CONFIDENCE,
                      preferred)

    def _evaluate(self, in_scope, out_scope, threshold):
        row = {"correct": 0, "wrong": 0, "clarification": 0, "fallback": 0, "rejected": 0, "leaked": 0}
        for hits, intent, expected, _ in in_scope:
            decision = self._decide(hits, intent, threshold)
            if decision.outcome == "answer":
                row["correct" if decision.best.key == expected else "wrong"] += 1
            elif decision.outcome == "clarification":
                row["clarification"] += 1
            else:
                row["fallback"] += 1
        for hits, intent, _, _ in out_scope:
            decision = self._decide(hits, intent, threshold)
            row["leaked" if decision.outcome == "answer" else "rejected"] += 1
        return row

    def _print_errors(self, in_scope, out_scope, threshold):
        self.stdout.write(f"\nErrors at threshold {threshold:.2f}:")
        questions = {faq.id: faq.reference_code for faq in FAQ.objects.only("id", "reference_code")}
        for hits, intent, expected, question in in_scope:
            decision = self._decide(hits, intent, threshold)
            if decision.outcome != "answer" or decision.best.key != expected:
                got = questions.get(decision.best.key) if decision.best else None
                self.stdout.write(f"  [{decision.outcome}] '{question}' expected {questions[expected]}, "
                                  f"best {got} ({decision.best.score:.3f})")
        for hits, intent, _, question in out_scope:
            decision = self._decide(hits, intent, threshold)
            if decision.outcome == "answer":
                self.stdout.write(f"  [leaked] '{question}' -> {questions.get(decision.best.key)} "
                                  f"({decision.best.score:.3f})")

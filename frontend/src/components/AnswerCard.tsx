import { useEffect, useMemo, useState } from "react";
import { ArrowRight, ChevronDown, Copy, LayoutGrid, ThumbsDown, ThumbsUp } from "lucide-react";
import { Link } from "react-router-dom";

import { api, ApiError, type Message } from "../api/client";
import { paragraphs } from "../lib/format";
import { Mark } from "./Brand";
import { useToast } from "./Toast";

/** The API appends "[Demonstration information] …" to answer text; the UI shows it as a badge instead. */
function answerBody(message: Message): string {
  if (!message.disclaimer) return message.content;
  const marker = message.content.lastIndexOf("\n\n[");
  return marker > 0 ? message.content.slice(0, marker) : message.content;
}

function matchStrength(score: number | null): { bars: 1 | 2 | 3; label: string } {
  if (score !== null && score >= 0.75) return { bars: 3, label: "Strong match" };
  if (score !== null && score >= 0.6) return { bars: 2, label: "Good match" };
  return { bars: 1, label: "Fair match" };
}

/** Reveals text word by word, like an answer being written. Skipped for reduced motion. */
function useTypewriter(text: string, enabled: boolean, onDone: () => void) {
  const tokens = useMemo(() => text.split(/(\s+)/), [text]);
  const reduced = useMemo(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches, []);
  const animate = enabled && !reduced;
  const [count, setCount] = useState(animate ? 0 : tokens.length);

  useEffect(() => {
    if (!animate) return;
    // About 1.6 seconds for a typical answer, never more than ~2.5 seconds.
    const step = Math.max(2, Math.ceil(tokens.length / 80));
    const timer = window.setInterval(() => {
      setCount((current) => {
        const next = Math.min(tokens.length, current + step);
        if (next >= tokens.length) window.clearInterval(timer);
        return next;
      });
    }, 30);
    return () => window.clearInterval(timer);
  }, [animate, tokens]);

  const done = count >= tokens.length;
  useEffect(() => {
    if (done && animate) onDone();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [done]);

  return { shown: done ? text : tokens.slice(0, count).join(""), done };
}

interface Props {
  message: Message;
  animate: boolean;
  onAnimated: () => void;
  onAsk: (question: string) => void;
  disabled: boolean;
}

export function AnswerCard({ message, animate, onAnimated, onAsk, disabled }: Props) {
  const toast = useToast();
  const body = answerBody(message);
  const { shown, done } = useTypewriter(body, animate, onAnimated);
  const source = message.sources[0];
  const kind = message.response_type || "answer";
  const isAnswer = kind === "answer";
  const strength = matchStrength(message.similarity_score);

  async function copy() {
    try {
      await navigator.clipboard.writeText(body);
      toast("Answer copied");
    } catch {
      toast("Couldn't copy. Select the text instead.");
    }
  }

  return (
    <article className={`answer answer--${kind}`} aria-label="Answer from Campus Desk">
      <div className="answer__avatar">
        <Mark size={34} />
      </div>
      <div className="answer__main">
        <div className="answer__card">
          <header className="answer__head">
            <span className="answer__who">Campus Desk</span>
            {source && <span className="chip chip--topic">{source.category}</span>}
            {kind === "fallback" && <span className="chip chip--muted">Not in the knowledge base</span>}
            {kind === "clarification" && <span className="chip chip--muted">Needs a little more detail</span>}
            {message.disclaimer && isAnswer && (
              <span className="chip chip--demo" title={message.disclaimer}>
                Demo information
              </span>
            )}
            {message.is_verified && <span className="chip chip--verified">Verified</span>}
          </header>

          <div className={`answer__body${done ? "" : " is-typing"}`}>
            {paragraphs(shown).map((text, index) => (
              <p key={index}>{text}</p>
            ))}
          </div>

          {done && message.suggestions.length > 0 && (
            <ul className="answer__options">
              {message.suggestions.map((suggestion) => (
                <li key={suggestion.faq_id}>
                  <button type="button" className="option" disabled={disabled} onClick={() => onAsk(suggestion.question)}>
                    <span>{suggestion.question}</span>
                    <ArrowRight aria-hidden="true" size={16} />
                  </button>
                </li>
              ))}
            </ul>
          )}

          {done && kind === "fallback" && (
            <p className="answer__next">
              Try different words, or{" "}
              <Link to="/topics" className="inline-link">
                <LayoutGrid aria-hidden="true" size={14} /> browse every topic
              </Link>{" "}
              I can answer.
            </p>
          )}

          {done && isAnswer && source && (
            <footer className="answer__foot">
              <span className="match" title={`Similarity ${message.similarity_score?.toFixed(2) ?? "n/a"} between your question and the stored one`}>
                <span className={`match__bars match__bars--${strength.bars}`} aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
                {strength.label}
              </span>
              <details className="source">
                <summary>
                  Source {source.reference_code}
                  <ChevronDown aria-hidden="true" size={14} />
                </summary>
                <div className="source__panel">
                  <p>
                    <strong>Matched question:</strong> {source.question}
                  </p>
                  {source.source_description && <p>{source.source_description}</p>}
                  {message.disclaimer && <p>{message.disclaimer}</p>}
                </div>
              </details>
            </footer>
          )}
        </div>

        {done && (isAnswer || kind === "fallback") && (
          <div className="answer__actions">
            {isAnswer && (
              <button type="button" className="iconbtn iconbtn--sm" aria-label="Copy answer" onClick={() => void copy()}>
                <Copy aria-hidden="true" size={16} />
              </button>
            )}
            <Feedback messageId={message.id} />
          </div>
        )}

        {done && isAnswer && message.related_questions.length > 0 && (
          <div className="related">
            <p className="related__label">Related questions</p>
            <ul>
              {message.related_questions.map((related) => (
                <li key={related.faq_id}>
                  <button type="button" className="chipbtn" disabled={disabled} onClick={() => onAsk(related.question)}>
                    {related.question}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </article>
  );
}

function Feedback({ messageId }: { messageId: number }) {
  const toast = useToast();
  const [state, setState] = useState<"idle" | "why" | "sending" | "sent">("idle");
  const [comment, setComment] = useState("");

  async function send(rating: number, text = "") {
    setState("sending");
    try {
      await api.sendFeedback(messageId, rating, text.trim());
      toast(rating >= 4 ? "Glad it helped" : "Thanks, this helps staff improve answers");
      setState("sent");
    } catch (error) {
      if (error instanceof ApiError && error.status === 400 && error.message.includes("already")) {
        setState("sent");
        return;
      }
      toast("Couldn't send feedback. Try again.");
      setState("idle");
    }
  }

  if (state === "sent") return <span className="feedback__done">Feedback sent</span>;

  if (state === "why" || (state === "sending" && comment)) {
    return (
      <form
        className="feedback__why"
        onSubmit={(event) => {
          event.preventDefault();
          void send(1, comment);
        }}
      >
        <label htmlFor={`why-${messageId}`}>What was missing or wrong? (optional)</label>
        <textarea id={`why-${messageId}`} rows={2} maxLength={1000} value={comment} autoFocus onChange={(event) => setComment(event.target.value)} />
        <span className="feedback__why-actions">
          <button type="submit" className="btn btn--primary btn--sm" disabled={state === "sending"}>
            Send feedback
          </button>
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setState("idle")}>
            Cancel
          </button>
        </span>
      </form>
    );
  }

  return (
    <span className="feedback" role="group" aria-label="Was this answer helpful?">
      <button type="button" className="iconbtn iconbtn--sm" disabled={state === "sending"} aria-label="Helpful" onClick={() => void send(5)}>
        <ThumbsUp aria-hidden="true" size={16} />
      </button>
      <button type="button" className="iconbtn iconbtn--sm" disabled={state === "sending"} aria-label="Not helpful" onClick={() => setState("why")}>
        <ThumbsDown aria-hidden="true" size={16} />
      </button>
    </span>
  );
}

import { useState } from "react";
import { BookOpenText, CircleHelp, ThumbsDown, ThumbsUp } from "lucide-react";

import { api, ApiError, type Message } from "../api/client";
import { paragraphs } from "../lib/format";

/** The API appends "[Demonstration information] <disclaimer>" to answer text; the UI shows it as a stamp instead. */
function answerBody(message: Message): string {
  if (!message.disclaimer) return message.content;
  const marker = message.content.lastIndexOf("\n\n[");
  return marker > 0 ? message.content.slice(0, marker) : message.content;
}

interface Props {
  message: Message;
  onAsk: (question: string) => void;
  onBrowseTopics: () => void;
  disabled: boolean;
}

export function BotEntry({ message, onAsk, onBrowseTopics, disabled }: Props) {
  const source = message.sources[0];
  const isAnswer = message.response_type === "answer";
  const isDemo = Boolean(message.disclaimer);

  return (
    <article className={`entry entry--${message.response_type || "answer"}`} aria-label="Answer from Campus Desk">
      {source ? (
        <p className="entry__topic">{source.category}</p>
      ) : message.response_type === "fallback" ? (
        <p className="entry__topic entry__topic--quiet">Not in the knowledge base</p>
      ) : null}

      <div className="entry__body">
        {paragraphs(answerBody(message)).map((text, index) => (
          <p key={index}>{text}</p>
        ))}
      </div>

      {message.suggestions.length > 0 && (
        <div className="entry__suggestions">
          <ul>
            {message.suggestions.map((suggestion) => (
              <li key={suggestion.faq_id}>
                <button type="button" className="suggestion" disabled={disabled} onClick={() => onAsk(suggestion.question)}>
                  <CircleHelp aria-hidden="true" size={16} />
                  <span>{suggestion.question}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {message.response_type === "fallback" && (
        <p className="entry__next">
          Try rephrasing, or{" "}
          <button type="button" className="link-button link-button--inline" onClick={onBrowseTopics}>
            see all topics
          </button>{" "}
          the knowledge base covers.
        </p>
      )}

      {isAnswer && source && (
        <footer className="entry__provenance">
          <BookOpenText aria-hidden="true" size={15} />
          <span>
            Source: <span className="entry__ref">{source.reference_code}</span> · {source.question}
          </span>
          {isDemo ? (
            <details className="stamp">
              <summary>Demonstration information</summary>
              <p>{message.disclaimer}</p>
            </details>
          ) : message.is_verified ? (
            <span className="stamp stamp--verified">Verified</span>
          ) : null}
        </footer>
      )}

      {(isAnswer || message.response_type === "fallback") && <Feedback messageId={message.id} />}
    </article>
  );
}

type FeedbackState = "idle" | "asking-why" | "sending" | "sent" | "error";

function Feedback({ messageId }: { messageId: number }) {
  const [state, setState] = useState<FeedbackState>("idle");
  const [comment, setComment] = useState("");
  const [thanks, setThanks] = useState("Thanks for the feedback.");

  async function send(rating: number, text = "") {
    setState("sending");
    try {
      await api.sendFeedback(messageId, rating, text.trim());
      setThanks(rating >= 4 ? "Glad it helped." : "Thanks. This helps staff improve the answers.");
      setState("sent");
    } catch (error) {
      if (error instanceof ApiError && error.status === 400 && error.message.includes("already")) {
        setState("sent");
        return;
      }
      setState("error");
    }
  }

  if (state === "sent") {
    return (
      <p className="feedback feedback--done" role="status">
        {thanks}
      </p>
    );
  }

  if (state === "asking-why" || (state === "sending" && comment)) {
    return (
      <form
        className="feedback-why"
        onSubmit={(event) => {
          event.preventDefault();
          void send(1, comment);
        }}
      >
        <label htmlFor={`why-${messageId}`}>What was missing or wrong? (optional)</label>
        <textarea
          id={`why-${messageId}`}
          rows={2}
          maxLength={1000}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
        />
        <div className="feedback-why__actions">
          <button type="submit" className="button button--small" disabled={state === "sending"}>
            Send feedback
          </button>
          <button type="button" className="link-button" onClick={() => setState("idle")}>
            Cancel
          </button>
        </div>
      </form>
    );
  }

  return (
    <div className="feedback" role="group" aria-label="Was this answer helpful?">
      <span className="feedback__label">Helpful?</span>
      <button type="button" className="icon-button" disabled={state === "sending"} onClick={() => void send(5)} aria-label="Yes, this was helpful">
        <ThumbsUp aria-hidden="true" size={17} />
      </button>
      <button type="button" className="icon-button" disabled={state === "sending"} onClick={() => setState("asking-why")} aria-label="No, this was not helpful">
        <ThumbsDown aria-hidden="true" size={17} />
      </button>
      {state === "error" && <span className="feedback__error">Couldn't send. Try again.</span>}
    </div>
  );
}

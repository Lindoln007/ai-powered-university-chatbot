import { forwardRef, useImperativeHandle, useRef, useState, type KeyboardEvent } from "react";
import { ArrowUp } from "lucide-react";

const MAX_LENGTH = 500;

export interface ComposerHandle {
  focus: () => void;
}

interface Props {
  onSend: (text: string) => void;
  busy: boolean;
  notice?: string;
  large?: boolean;
}

export const Composer = forwardRef<ComposerHandle, Props>(function Composer({ onSend, busy, notice, large }, ref) {
  const [text, setText] = useState("");
  const formRef = useRef<HTMLFormElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useImperativeHandle(ref, () => ({ focus: () => inputRef.current?.focus() }), []);

  const trimmed = text.trim();
  const tooLong = text.length > MAX_LENGTH;
  const canSend = trimmed.length > 0 && !tooLong && !busy;

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends, Shift+Enter adds a line. Never send while an IME is composing text.
    if (event.key !== "Enter" || event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) return;
    event.preventDefault();
    if (event.nativeEvent.isComposing || event.keyCode === 229 || event.repeat) return;
    formRef.current?.requestSubmit();
  }

  const hint =
    text.length > MAX_LENGTH - 100
      ? `${text.length} / ${MAX_LENGTH} characters${tooLong ? ". Please shorten your question." : ""}`
      : (notice ?? "Enter to send · Shift+Enter for a new line");

  return (
    <form
      ref={formRef}
      className={`composer${large ? " composer--large" : ""}`}
      onSubmit={(event) => {
        event.preventDefault();
        if (!canSend) return;
        onSend(trimmed);
        setText("");
      }}
    >
      <div className={`composer__field${tooLong ? " is-invalid" : ""}`}>
        <label htmlFor="question" className="sr-only">
          Your question
        </label>
        <textarea
          ref={inputRef}
          id="question"
          rows={1}
          placeholder="Ask about fees, exams, housing…"
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={onKeyDown}
          aria-describedby="composer-hint"
          aria-invalid={tooLong || undefined}
          enterKeyHint="send"
          autoComplete="off"
        />
        <button type="submit" className="composer__send" disabled={!canSend} aria-label="Send question">
          <ArrowUp aria-hidden="true" size={20} strokeWidth={2.6} />
        </button>
      </div>
      <p id="composer-hint" className={`composer__hint${tooLong ? " is-error" : ""}`}>
        {hint}
      </p>
    </form>
  );
});

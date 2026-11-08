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
}

export const Composer = forwardRef<ComposerHandle, Props>(function Composer({ onSend, busy, notice }, ref) {
  const [text, setText] = useState("");
  const formRef = useRef<HTMLFormElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useImperativeHandle(ref, () => ({ focus: () => inputRef.current?.focus() }), []);

  const trimmed = text.trim();
  const tooLong = text.length > MAX_LENGTH;
  const canSend = trimmed.length > 0 && !tooLong && !busy;

  function submit() {
    if (!canSend) return;
    onSend(trimmed);
    setText("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends, Shift+Enter adds a line. Never send while an IME is composing text.
    if (event.key !== "Enter" || event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) return;
    event.preventDefault();
    if (event.nativeEvent.isComposing || event.keyCode === 229 || event.repeat) return;
    formRef.current?.requestSubmit();
  }

  return (
    <form
      ref={formRef}
      className="composer"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <label htmlFor="question" className="visually-hidden">
        Your question
      </label>
      <textarea
        ref={inputRef}
        id="question"
        className="composer__input"
        rows={1}
        placeholder="Ask about admissions, fees, exams, the library…"
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={onKeyDown}
        aria-describedby="composer-hint"
        aria-invalid={tooLong || undefined}
        enterKeyHint="send"
        autoComplete="off"
      />
      <button type="submit" className="composer__send" disabled={!canSend} aria-label="Send question">
        <ArrowUp aria-hidden="true" size={20} strokeWidth={2.4} />
      </button>
      <p id="composer-hint" className={`composer__hint${tooLong ? " composer__hint--error" : ""}`}>
        {text.length > MAX_LENGTH - 100
          ? `${text.length} / ${MAX_LENGTH} characters${tooLong ? ". Please shorten your question." : ""}`
          : notice ?? "Answers come from the university knowledge base. Press Enter to send, Shift+Enter for a new line."}
      </p>
    </form>
  );
});

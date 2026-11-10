import { useEffect, useRef, useState } from "react";
import { CornerDownLeft, Search } from "lucide-react";

import { api, type SearchResult } from "../api/client";

interface Props {
  open: boolean;
  onClose: () => void;
  onAsk: (question: string) => void;
}

/** Quick search (Ctrl+K): find an answer by meaning, then open it in the chat. */
export function CommandPalette({ open, onClose, onAsk }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [state, setState] = useState<"idle" | "searching" | "done" | "error">("idle");
  const [active, setActive] = useState(0);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      setQuery("");
      setResults([]);
      setState("idle");
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  useEffect(() => {
    const text = query.trim();
    if (text.length < 3) {
      setResults([]);
      setState("idle");
      return;
    }
    setState("searching");
    let cancelled = false;
    const timer = window.setTimeout(() => {
      api
        .search(text)
        .then((response) => {
          if (cancelled) return;
          setResults(response.results);
          setActive(0);
          setState("done");
        })
        .catch(() => !cancelled && setState("error"));
    }, 220);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query]);

  function choose(question: string) {
    onClose();
    onAsk(question);
  }

  const typed = query.trim();

  return (
    <dialog
      ref={dialogRef}
      className="palette"
      aria-label="Search answers"
      onClose={onClose}
      onClick={(event) => event.target === dialogRef.current && onClose()}
    >
      <div className="palette__box">
        <div className="palette__field">
          <Search aria-hidden="true" size={20} />
          <input
            type="search"
            placeholder="Search answers, e.g. hostel fees"
            aria-label="Search the knowledge base"
            aria-controls="palette-results"
            aria-activedescendant={results[active] ? `palette-option-${results[active].id}` : undefined}
            value={query}
            maxLength={200}
            autoComplete="off"
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setActive((index) => Math.min(index + 1, results.length - 1));
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setActive((index) => Math.max(index - 1, 0));
              } else if (event.key === "Enter" && !event.nativeEvent.isComposing) {
                event.preventDefault();
                if (results[active]) choose(results[active].title);
                else if (typed) choose(typed);
              }
            }}
          />
          <kbd className="kbd">Esc</kbd>
        </div>

        <div className="palette__body" id="palette-results" role="listbox" aria-label="Matching answers">
          {state === "idle" && (
            <p className="palette__hint">Type at least three letters. Results are matched by meaning, not exact words.</p>
          )}
          {state === "searching" && results.length === 0 && <p className="palette__hint">Searching…</p>}
          {state === "error" && <p className="palette__hint">Search isn't available right now. Try asking in the chat.</p>}
          {state === "done" && results.length === 0 && (
            <div className="palette__empty">
              <p>No close match in the knowledge base.</p>
              <button type="button" className="btn btn--soft" onClick={() => choose(typed)}>
                Ask “{typed.slice(0, 60)}” in chat
              </button>
            </div>
          )}
          {results.map((result, index) => (
            <button
              key={result.id}
              id={`palette-option-${result.id}`}
              type="button"
              role="option"
              aria-selected={index === active}
              className={`palette__option${index === active ? " is-active" : ""}`}
              onMouseMove={() => index !== active && setActive(index)}
              onClick={() => choose(result.title)}
            >
              <span className="palette__topic">{result.category}</span>
              <span className="palette__title">{result.title}</span>
              <span className="palette__snippet">{result.content}</span>
            </button>
          ))}
        </div>

        <p className="palette__foot">
          <span>
            <kbd className="kbd">↑</kbd> <kbd className="kbd">↓</kbd> to move
          </span>
          <span>
            <kbd className="kbd">
              <CornerDownLeft aria-hidden="true" size={12} />
            </kbd>{" "}
            to open in chat
          </span>
        </p>
      </div>
    </dialog>
  );
}

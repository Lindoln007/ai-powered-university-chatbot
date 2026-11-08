import { useState } from "react";
import { Check, MessageSquarePlus, Pencil, Trash2, X } from "lucide-react";
import { NavLink } from "react-router-dom";

import type { Conversation } from "../api/client";
import { relativeDay } from "../lib/format";

interface Props {
  conversations: Conversation[];
  loading: boolean;
  activeId: number | null;
  onNew: () => void;
  onRename: (id: number, title: string) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
  onNavigate: () => void;
}

const GROUP_ORDER = ["Today", "Yesterday", "This week", "Earlier"];

export function ConversationRail({ conversations, loading, activeId, onNew, onRename, onDelete, onNavigate }: Props) {
  const groups = new Map<string, Conversation[]>();
  for (const conversation of conversations) {
    const group = relativeDay(conversation.updated_at);
    groups.set(group, [...(groups.get(group) ?? []), conversation]);
  }

  return (
    <nav className="rail" aria-label="Your conversations">
      <button type="button" className="button button--quiet rail__new" onClick={onNew}>
        <MessageSquarePlus aria-hidden="true" size={18} />
        New conversation
      </button>

      {loading && conversations.length === 0 ? (
        <div className="rail__skeleton" aria-hidden="true">
          <div className="skeleton-line" />
          <div className="skeleton-line" />
          <div className="skeleton-line skeleton-line--short" />
        </div>
      ) : conversations.length === 0 ? (
        <p className="rail__empty">Your conversations will appear here, so you can come back to an answer later.</p>
      ) : (
        GROUP_ORDER.filter((name) => groups.has(name)).map((name) => (
          <section key={name} className="rail__group" aria-label={name}>
            <h2 className="rail__heading">{name}</h2>
            <ul>
              {groups.get(name)!.map((conversation) => (
                <RailItem
                  key={conversation.id}
                  conversation={conversation}
                  active={conversation.id === activeId}
                  onRename={onRename}
                  onDelete={onDelete}
                  onNavigate={onNavigate}
                />
              ))}
            </ul>
          </section>
        ))
      )}
    </nav>
  );
}

function RailItem({
  conversation,
  active,
  onRename,
  onDelete,
  onNavigate,
}: {
  conversation: Conversation;
  active: boolean;
  onRename: Props["onRename"];
  onDelete: Props["onDelete"];
  onNavigate: () => void;
}) {
  const [mode, setMode] = useState<"view" | "rename" | "confirm-delete">("view");
  const [title, setTitle] = useState(conversation.title);
  const [busy, setBusy] = useState(false);
  const label = conversation.title || "Untitled conversation";

  if (mode === "rename") {
    return (
      <li className="rail__item rail__item--editing">
        <form
          className="rail__rename"
          onSubmit={async (event) => {
            event.preventDefault();
            setBusy(true);
            await onRename(conversation.id, title.trim()).finally(() => setBusy(false));
            setMode("view");
          }}
        >
          <label htmlFor={`rename-${conversation.id}`} className="visually-hidden">
            Conversation name
          </label>
          <input
            id={`rename-${conversation.id}`}
            value={title}
            maxLength={200}
            autoFocus
            onChange={(event) => setTitle(event.target.value)}
            onKeyDown={(event) => event.key === "Escape" && setMode("view")}
          />
          <button type="submit" className="icon-button" aria-label="Save name" disabled={busy}>
            <Check aria-hidden="true" size={16} />
          </button>
          <button type="button" className="icon-button" aria-label="Cancel renaming" onClick={() => setMode("view")}>
            <X aria-hidden="true" size={16} />
          </button>
        </form>
      </li>
    );
  }

  if (mode === "confirm-delete") {
    return (
      <li className="rail__item rail__item--confirm" role="group" aria-label={`Delete ${label}?`}>
        <span>Delete this conversation?</span>
        <div className="rail__confirm-actions">
          <button
            type="button"
            className="button button--danger button--small"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              await onDelete(conversation.id).finally(() => setBusy(false));
            }}
          >
            Delete
          </button>
          <button type="button" className="link-button" onClick={() => setMode("view")}>
            Keep
          </button>
        </div>
      </li>
    );
  }

  return (
    <li className={`rail__item${active ? " rail__item--active" : ""}`}>
      <NavLink to={`/c/${conversation.id}`} className="rail__link" aria-current={active ? "page" : undefined} onClick={onNavigate}>
        {label}
      </NavLink>
      <div className="rail__actions">
        <button type="button" className="icon-button icon-button--small" aria-label={`Rename ${label}`} onClick={() => setMode("rename")}>
          <Pencil aria-hidden="true" size={15} />
        </button>
        <button
          type="button"
          className="icon-button icon-button--small"
          aria-label={`Delete ${label}`}
          onClick={() => setMode("confirm-delete")}
        >
          <Trash2 aria-hidden="true" size={15} />
        </button>
      </div>
    </li>
  );
}

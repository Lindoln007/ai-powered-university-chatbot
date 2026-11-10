import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  BarChart3,
  Check,
  LayoutGrid,
  LogIn,
  LogOut,
  Menu,
  MessageCircle,
  Moon,
  Pencil,
  Plus,
  Search,
  Sun,
  Trash2,
  X,
} from "lucide-react";
import { Link, NavLink, useMatch, useNavigate } from "react-router-dom";

import { api, type Conversation } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../lib/theme";
import { useConversations } from "../state/conversations";
import { Mark } from "./Brand";
import { CommandPalette } from "./CommandPalette";

const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

/** Side panel, mobile top bar and quick search shared by every signed-in or guest page. */
export function AppShell({ children }: { children: ReactNode }) {
  const { user, isAdmin, signOut } = useAuth();
  const { theme, toggle } = useTheme();
  const { conversations, loading, rename, remove } = useConversations();
  const navigate = useNavigate();
  const activeMatch = useMatch("/c/:conversationId");
  const activeId = activeMatch ? Number(activeMatch.params.conversationId) : null;

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [demoMode, setDemoMode] = useState(false);

  useEffect(() => {
    api
      .health()
      .then((health) => setDemoMode(health.demo_mode))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const closeDrawer = useCallback(() => setDrawerOpen(false), []);
  const askInChat = useCallback(
    (question: string) => {
      closeDrawer();
      navigate("/", { state: { ask: question } });
    },
    [navigate, closeDrawer],
  );

  return (
    <div className={`shell${drawerOpen ? " shell--drawer-open" : ""}`}>
      <header className="mobilebar">
        <button
          type="button"
          className="iconbtn iconbtn--on-forest"
          aria-label={drawerOpen ? "Close menu" : "Open menu"}
          aria-expanded={drawerOpen}
          aria-controls="side"
          onClick={() => setDrawerOpen((open) => !open)}
        >
          {drawerOpen ? <X aria-hidden="true" size={22} /> : <Menu aria-hidden="true" size={22} />}
        </button>
        <Link to="/" className="brandlink" onClick={closeDrawer}>
          <Mark size={30} />
          <span className="brandlink__name">Campus Desk</span>
        </Link>
        <button type="button" className="iconbtn iconbtn--on-forest" aria-label="Search answers" onClick={() => setPaletteOpen(true)}>
          <Search aria-hidden="true" size={20} />
        </button>
      </header>

      <aside className="side" id="side" aria-label="Main menu">
        <Link to="/" className="brandlink side__brand" onClick={closeDrawer}>
          <Mark size={38} />
          <span>
            <span className="brandlink__name">Campus Desk</span>
            <span className="brandlink__sub">DMI St. John the Baptist University</span>
          </span>
        </Link>

        <Link to="/" className="btn btn--gold side__new" onClick={closeDrawer}>
          <Plus aria-hidden="true" size={18} strokeWidth={2.6} />
          New chat
        </Link>

        <button type="button" className="side__search" onClick={() => setPaletteOpen(true)}>
          <Search aria-hidden="true" size={17} />
          <span>Search answers</span>
          <kbd className="kbd kbd--forest">{isMac ? "⌘ K" : "Ctrl K"}</kbd>
        </button>

        <nav className="side__nav" aria-label="Sections">
          <NavLink
            to="/"
            end
            className={({ isActive }) => `side__link${isActive || activeId !== null ? " active" : ""}`}
            onClick={closeDrawer}
          >
            <MessageCircle aria-hidden="true" size={18} />
            Chat
          </NavLink>
          <NavLink to="/topics" className="side__link" onClick={closeDrawer}>
            <LayoutGrid aria-hidden="true" size={18} />
            Browse topics
          </NavLink>
          {isAdmin && (
            <NavLink to="/staff" className="side__link" onClick={closeDrawer}>
              <BarChart3 aria-hidden="true" size={18} />
              Staff dashboard
            </NavLink>
          )}
        </nav>

        <section className="side__recent" aria-label="Recent conversations">
          <h2 className="side__heading">Recent</h2>
          {loading && conversations.length === 0 ? (
            <div className="side__skeleton" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
          ) : conversations.length === 0 ? (
            <p className="side__empty">Your chats will be saved here so you can come back to an answer.</p>
          ) : (
            <ul>
              {conversations.map((conversation) => (
                <RecentItem
                  key={conversation.id}
                  conversation={conversation}
                  active={conversation.id === activeId}
                  onNavigate={closeDrawer}
                  onRename={rename}
                  onDelete={async (id) => {
                    await remove(id);
                    if (id === activeId) navigate("/");
                  }}
                />
              ))}
            </ul>
          )}
        </section>

        <div className="side__foot">
          {demoMode && (
            <details className="protonote">
              <summary>
                <span className="protonote__dot" aria-hidden="true" />
                Prototype with demo data
              </summary>
              <p>
                Most answers use hypothetical demonstration information, not official university information. Always
                confirm fees, dates and requirements with the relevant office.
              </p>
            </details>
          )}
          <div className="side__account">
            {user ? (
              <>
                <span className="avatar" aria-hidden="true">
                  {(user.first_name || user.username).slice(0, 1).toUpperCase()}
                </span>
                <span className="side__user">
                  <span className="side__username">{user.first_name || user.username}</span>
                  <span className="side__role">{user.role.replace("_", " ")}</span>
                </span>
                <button
                  type="button"
                  className="iconbtn iconbtn--on-forest"
                  aria-label={`Sign out ${user.username}`}
                  onClick={async () => {
                    await signOut();
                    closeDrawer();
                    navigate("/");
                  }}
                >
                  <LogOut aria-hidden="true" size={18} />
                </button>
              </>
            ) : (
              <Link to="/signin" className="side__signin" onClick={closeDrawer}>
                <LogIn aria-hidden="true" size={18} />
                <span>
                  <span className="side__username">Sign in</span>
                  <span className="side__role">Keep chats on any device</span>
                </span>
              </Link>
            )}
            <button
              type="button"
              className="iconbtn iconbtn--on-forest"
              onClick={toggle}
              aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            >
              {theme === "dark" ? <Sun aria-hidden="true" size={18} /> : <Moon aria-hidden="true" size={18} />}
            </button>
          </div>
        </div>
      </aside>

      {drawerOpen && <button type="button" className="scrim" aria-label="Close menu" onClick={closeDrawer} />}

      <main className="main" id="main">
        {children}
      </main>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} onAsk={askInChat} />
    </div>
  );
}

function RecentItem({
  conversation,
  active,
  onNavigate,
  onRename,
  onDelete,
}: {
  conversation: Conversation;
  active: boolean;
  onNavigate: () => void;
  onRename: (id: number, title: string) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}) {
  const [mode, setMode] = useState<"view" | "rename" | "confirm">("view");
  const [title, setTitle] = useState(conversation.title);
  const [busy, setBusy] = useState(false);
  const label = conversation.title || "Untitled chat";

  if (mode === "rename") {
    return (
      <li>
        <form
          className="recent__rename"
          onSubmit={async (event) => {
            event.preventDefault();
            setBusy(true);
            await onRename(conversation.id, title.trim()).finally(() => setBusy(false));
            setMode("view");
          }}
        >
          <label htmlFor={`rename-${conversation.id}`} className="sr-only">
            Chat name
          </label>
          <input
            id={`rename-${conversation.id}`}
            value={title}
            maxLength={200}
            autoFocus
            onChange={(event) => setTitle(event.target.value)}
            onKeyDown={(event) => event.key === "Escape" && setMode("view")}
          />
          <button type="submit" className="iconbtn iconbtn--on-forest iconbtn--sm" aria-label="Save name" disabled={busy}>
            <Check aria-hidden="true" size={16} />
          </button>
          <button type="button" className="iconbtn iconbtn--on-forest iconbtn--sm" aria-label="Cancel" onClick={() => setMode("view")}>
            <X aria-hidden="true" size={16} />
          </button>
        </form>
      </li>
    );
  }

  if (mode === "confirm") {
    return (
      <li className="recent__confirm" role="group" aria-label={`Delete ${label}?`}>
        <span>Delete this chat?</span>
        <span className="recent__confirm-actions">
          <button
            type="button"
            className="btn btn--danger btn--sm"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              await onDelete(conversation.id).finally(() => setBusy(false));
            }}
          >
            Delete
          </button>
          <button type="button" className="btn btn--ghost-forest btn--sm" onClick={() => setMode("view")}>
            Keep
          </button>
        </span>
      </li>
    );
  }

  return (
    <li className={`recent${active ? " is-active" : ""}`}>
      <NavLink to={`/c/${conversation.id}`} className="recent__link" onClick={onNavigate}>
        {label}
      </NavLink>
      <span className="recent__actions">
        <button type="button" className="iconbtn iconbtn--on-forest iconbtn--sm" aria-label={`Rename ${label}`} onClick={() => setMode("rename")}>
          <Pencil aria-hidden="true" size={14} />
        </button>
        <button type="button" className="iconbtn iconbtn--on-forest iconbtn--sm" aria-label={`Delete ${label}`} onClick={() => setMode("confirm")}>
          <Trash2 aria-hidden="true" size={14} />
        </button>
      </span>
    </li>
  );
}

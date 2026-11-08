import { useCallback, useEffect, useRef, useState } from "react";
import { RotateCcw } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, ApiError, session, type ChatResponse, type Conversation, type Message } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { BotEntry } from "../components/BotEntry";
import { Composer, type ComposerHandle } from "../components/Composer";
import { ConversationRail } from "../components/ConversationRail";
import { TopBar } from "../components/TopBar";
import { TopicIndex } from "../components/TopicIndex";

function toMessages(response: ChatResponse): [Message, Message] {
  const bot = response.bot_response;
  return [
    {
      id: response.user_message.id,
      conversation: response.conversation_id,
      sender_type: "user",
      content: response.user_message.content,
      intent: "",
      intent_confidence: null,
      similarity_score: null,
      response_type: "",
      answered: null,
      information_type: "",
      is_verified: null,
      disclaimer: null,
      retrieved_faq: null,
      sources: [],
      suggestions: [],
      used_context: false,
      timestamp: response.user_message.timestamp,
    },
    {
      id: bot.id,
      conversation: response.conversation_id,
      sender_type: "bot",
      content: bot.content,
      intent: bot.intent,
      intent_confidence: bot.intent_confidence,
      similarity_score: bot.similarity_score,
      response_type: bot.response_type,
      answered: bot.answered,
      information_type: bot.information_type ?? "",
      is_verified: bot.is_verified,
      disclaimer: bot.disclaimer,
      retrieved_faq: bot.sources[0]?.id ?? null,
      sources: bot.sources,
      suggestions: bot.suggestions,
      used_context: bot.used_context,
      timestamp: bot.timestamp,
    },
  ];
}

interface Pending {
  text: string;
  failed?: string;
}

export function ChatPage() {
  const { user, ready } = useAuth();
  const params = useParams();
  const navigate = useNavigate();
  const activeId = params.conversationId ? Number(params.conversationId) : null;

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [railLoading, setRailLoading] = useState(true);
  const [railOpen, setRailOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [threadState, setThreadState] = useState<"idle" | "loading" | "missing">("idle");
  const [pending, setPending] = useState<Pending | null>(null);
  const [announcement, setAnnouncement] = useState("");

  const [modelLoading, setModelLoading] = useState(false);

  // After a server restart the language model needs time to load; say so instead of leaving users guessing.
  useEffect(() => {
    let timer: number | undefined;
    let cancelled = false;
    const check = () =>
      api
        .health()
        .then((health) => {
          if (cancelled) return;
          const loading = health.nlp_model.status === "loading";
          setModelLoading(loading);
          if (loading) timer = window.setTimeout(check, 5000);
        })
        .catch(() => undefined);
    void check();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  const composerRef = useRef<ComposerHandle>(null);
  const threadEndRef = useRef<HTMLDivElement>(null);
  const justCreatedRef = useRef<number | null>(null);

  const loadConversations = useCallback(async () => {
    if (!session.authToken && !session.guestToken) {
      setConversations([]);
      setRailLoading(false);
      return;
    }
    try {
      const page = await api.conversations();
      setConversations(page.results);
    } catch {
      /* the rail is a convenience; the chat still works without it */
    } finally {
      setRailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (ready) void loadConversations();
  }, [ready, user, loadConversations]);

  // Load the selected conversation's history (skipped right after we created it ourselves).
  useEffect(() => {
    if (activeId !== null && justCreatedRef.current === activeId) {
      // The first question of this conversation is in flight; keep its pending state.
      justCreatedRef.current = null;
      return;
    }
    setPending(null);
    if (activeId === null) {
      setMessages([]);
      setThreadState("idle");
      return;
    }
    if (!ready) return;
    let cancelled = false;
    setThreadState("loading");
    api
      .messages(activeId)
      .then((page) => {
        if (cancelled) return;
        setMessages(page.results);
        setThreadState("idle");
      })
      .catch(() => !cancelled && setThreadState("missing"));
    return () => {
      cancelled = true;
    };
  }, [activeId, ready]);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, pending]);

  const ask = useCallback(
    async (text: string) => {
      setPending({ text });
      try {
        let conversationId = activeId;
        if (conversationId === null) {
          const conversation = await api.createConversation();
          if (conversation.guest_token) session.guestToken = conversation.guest_token;
          conversationId = conversation.id;
          justCreatedRef.current = conversation.id;
          setMessages([]);
          navigate(`/c/${conversation.id}`, { replace: activeId === null });
        }
        const response = await api.ask(conversationId, text);
        const [userMessage, botMessage] = toMessages(response);
        setMessages((current) => [...current, userMessage, botMessage]);
        setPending(null);
        setAnnouncement(`Campus Desk answered: ${botMessage.content.slice(0, 220)}`);
        void loadConversations();
      } catch (error) {
        const message =
          error instanceof ApiError
            ? error.status === 429
              ? `You're asking quickly. Please wait ${error.retryAfter ?? 30} seconds and try again.`
              : error.status === 503
                ? "The assistant is still starting up. Please try again in a moment."
                : error.message
            : "Something went wrong. Please try again.";
        setPending({ text, failed: message });
      } finally {
        composerRef.current?.focus();
      }
    },
    [activeId, navigate, loadConversations],
  );

  const startNew = useCallback(() => {
    setRailOpen(false);
    navigate("/");
    composerRef.current?.focus();
  }, [navigate]);

  const rename = useCallback(async (id: number, title: string) => {
    const updated = await api.renameConversation(id, title);
    setConversations((current) => current.map((item) => (item.id === id ? { ...item, title: updated.title } : item)));
  }, []);

  const remove = useCallback(
    async (id: number) => {
      await api.deleteConversation(id);
      setConversations((current) => current.filter((item) => item.id !== id));
      if (id === activeId) navigate("/");
    },
    [activeId, navigate],
  );

  const busy = pending !== null && !pending.failed;
  const showWelcome = activeId === null && messages.length === 0 && !pending;

  return (
    <div className={`app app--chat${railOpen ? " app--rail-open" : ""}`}>
      <TopBar onToggleRail={() => setRailOpen((open) => !open)} railOpen={railOpen} />

      <div className="chat-layout">
        <aside id="conversation-rail" className="chat-layout__rail">
          <ConversationRail
            conversations={conversations}
            loading={railLoading}
            activeId={activeId}
            onNew={startNew}
            onRename={rename}
            onDelete={remove}
            onNavigate={() => setRailOpen(false)}
          />
          {!user && (
            <p className="rail__account-hint">
              You're chatting as a guest. <Link to="/signin">Sign in</Link> to keep your conversations on any device.
            </p>
          )}
        </aside>
        {railOpen && <button type="button" className="scrim" aria-label="Close conversations" onClick={() => setRailOpen(false)} />}

        <main className="chat" id="main">
          <div className="thread" aria-busy={threadState === "loading" || busy}>
            {showWelcome && <TopicIndex onAsk={ask} disabled={busy} />}

            {threadState === "loading" && (
              <div className="thread__loading" aria-label="Loading conversation">
                <div className="skeleton-line skeleton-line--short" />
                <div className="skeleton-block" />
              </div>
            )}

            {threadState === "missing" && (
              <div className="thread__missing">
                <h1 className="thread__missing-title">This conversation isn't available</h1>
                <p>It may have been deleted, or it belongs to a different account or browser.</p>
                <button type="button" className="button" onClick={startNew}>
                  Start a new conversation
                </button>
              </div>
            )}

            {messages.map((message) =>
              message.sender_type === "user" ? (
                <p key={message.id} className="question">
                  <span className="visually-hidden">You asked: </span>
                  {message.content}
                </p>
              ) : (
                <BotEntry key={message.id} message={message} onAsk={ask} onBrowseTopics={startNew} disabled={busy} />
              ),
            )}

            {pending && (
              <>
                <p className="question question--pending">
                  <span className="visually-hidden">You asked: </span>
                  {pending.text}
                </p>
                {pending.failed ? (
                  <div className="thread__error" role="alert">
                    <p>{pending.failed}</p>
                    <button type="button" className="button button--quiet button--small" onClick={() => void ask(pending.text)}>
                      <RotateCcw aria-hidden="true" size={15} />
                      Try again
                    </button>
                  </div>
                ) : (
                  <div className="typing" aria-label="Campus Desk is looking for an answer">
                    <span />
                    <span />
                    <span />
                  </div>
                )}
              </>
            )}
            <div ref={threadEndRef} />
          </div>

          <div className="chat__composer">
            <Composer ref={composerRef} onSend={ask} busy={busy} notice={modelLoading ? "The assistant is starting up, so your first answer may take a minute." : undefined} />
          </div>
          <div className="visually-hidden" role="status" aria-live="polite">
            {announcement}
          </div>
        </main>
      </div>
    </div>
  );
}

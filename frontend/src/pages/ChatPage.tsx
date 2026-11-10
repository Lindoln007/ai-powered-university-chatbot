import { useCallback, useEffect, useRef, useState } from "react";
import { RotateCcw } from "lucide-react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { api, ApiError, session, type ChatResponse, type Message } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AnswerCard } from "../components/AnswerCard";
import { AppShell } from "../components/AppShell";
import { Mark } from "../components/Brand";
import { Composer, type ComposerHandle } from "../components/Composer";
import { Welcome } from "../components/Welcome";
import { useConversations } from "../state/conversations";

function toMessages(response: ChatResponse): [Message, Message] {
  const bot = response.bot_response;
  const base = {
    conversation: response.conversation_id,
    intent: "",
    intent_confidence: null,
    similarity_score: null,
    response_type: "" as const,
    answered: null,
    information_type: "",
    is_verified: null,
    disclaimer: null,
    retrieved_faq: null,
    sources: [],
    suggestions: [],
    related_questions: [],
    used_context: false,
  };
  return [
    {
      ...base,
      id: response.user_message.id,
      sender_type: "user",
      content: response.user_message.content,
      timestamp: response.user_message.timestamp,
    },
    {
      ...base,
      id: bot.id,
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
      related_questions: bot.related_questions ?? [],
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
  const { ready } = useAuth();
  const { refresh } = useConversations();
  const params = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const activeId = params.conversationId ? Number(params.conversationId) : null;

  const [messages, setMessages] = useState<Message[]>([]);
  const [threadState, setThreadState] = useState<"idle" | "loading" | "missing">("idle");
  const [pending, setPending] = useState<Pending | null>(null);
  const [freshId, setFreshId] = useState<number | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const [modelLoading, setModelLoading] = useState(false);

  const composerRef = useRef<ComposerHandle>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const justCreatedRef = useRef<number | null>(null);
  const handledAskRef = useRef<string | null>(null);

  // After a server restart the language model needs a moment to load; say so instead of leaving users guessing.
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
          if (loading) timer = window.setTimeout(check, 3000);
        })
        .catch(() => undefined);
    void check();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  // Load the selected conversation's history (skipped right after we created it ourselves).
  useEffect(() => {
    if (activeId !== null && justCreatedRef.current === activeId) {
      justCreatedRef.current = null;
      return;
    }
    setPending(null);
    setFreshId(null);
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

  const scrollToEnd = useCallback(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, []);

  useEffect(scrollToEnd, [messages, pending, scrollToEnd]);

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
          navigate(`/c/${conversation.id}`, { replace: true });
        }
        const response = await api.ask(conversationId, text);
        const [userMessage, botMessage] = toMessages(response);
        setFreshId(botMessage.id);
        setMessages((current) => [...current, userMessage, botMessage]);
        setPending(null);
        setAnnouncement(`Campus Desk answered: ${botMessage.content.slice(0, 220)}`);
        void refresh();
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
    [activeId, navigate, refresh],
  );

  // A question handed over from quick search or the topics page.
  useEffect(() => {
    const question = (location.state as { ask?: string } | null)?.ask;
    if (!question || handledAskRef.current === location.key) return;
    handledAskRef.current = location.key;
    navigate(location.pathname, { replace: true, state: null });
    void ask(question);
  }, [location, navigate, ask]);

  const busy = pending !== null && !pending.failed;
  const showWelcome = activeId === null && messages.length === 0 && !pending;
  const notice = modelLoading ? "The assistant is starting up, so your first answer may take a few seconds." : undefined;
  const composer = <Composer ref={composerRef} onSend={ask} busy={busy} notice={notice} large={showWelcome} />;

  return (
    <AppShell>
      {showWelcome ? (
        <div className="scrollarea">
          <Welcome composer={composer} onAsk={ask} disabled={busy} />
        </div>
      ) : (
        <div className="chat">
          <div className="scrollarea" aria-busy={threadState === "loading" || busy}>
            <div className="thread">
              {threadState === "loading" && (
                <div className="thread__loading" aria-label="Loading conversation">
                  <span className="skeleton skeleton--bubble" />
                  <span className="skeleton skeleton--card" />
                </div>
              )}

              {threadState === "missing" && (
                <div className="notice-card">
                  <h1>This chat isn't available</h1>
                  <p>It may have been deleted, or it belongs to a different account or browser.</p>
                  <button type="button" className="btn btn--primary" onClick={() => navigate("/")}>
                    Start a new chat
                  </button>
                </div>
              )}

              {messages.map((message) =>
                message.sender_type === "user" ? (
                  <p key={message.id} className="bubble">
                    <span className="sr-only">You asked: </span>
                    {message.content}
                  </p>
                ) : (
                  <AnswerCard
                    key={message.id}
                    message={message}
                    animate={message.id === freshId}
                    onAnimated={scrollToEnd}
                    onAsk={ask}
                    disabled={busy}
                  />
                ),
              )}

              {pending && (
                <>
                  <p className="bubble bubble--pending">
                    <span className="sr-only">You asked: </span>
                    {pending.text}
                  </p>
                  {pending.failed ? (
                    <div className="thread__error" role="alert">
                      <p>{pending.failed}</p>
                      <button type="button" className="btn btn--soft btn--sm" onClick={() => void ask(pending.text)}>
                        <RotateCcw aria-hidden="true" size={15} />
                        Try again
                      </button>
                    </div>
                  ) : (
                    <div className="thinking" aria-label="Campus Desk is searching the knowledge base">
                      <Mark size={34} />
                      <span className="thinking__text">
                        Searching the knowledge base
                        <span className="thinking__dots" aria-hidden="true">
                          <i />
                          <i />
                          <i />
                        </span>
                      </span>
                    </div>
                  )}
                </>
              )}
              <div ref={endRef} />
            </div>
          </div>
          <div className="chat__dock">{composer}</div>
        </div>
      )}
      <div className="sr-only" role="status" aria-live="polite">
        {announcement}
      </div>
    </AppShell>
  );
}

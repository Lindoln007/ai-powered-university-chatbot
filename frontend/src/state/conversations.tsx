import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, session, type Conversation } from "../api/client";
import { useAuth } from "../auth/AuthContext";

interface ConversationsState {
  conversations: Conversation[];
  loading: boolean;
  refresh: () => Promise<void>;
  rename: (id: number, title: string) => Promise<void>;
  remove: (id: number) => Promise<void>;
}

const ConversationsContext = createContext<ConversationsState | null>(null);

/** The signed-in user's (or guest's) conversations, shared by the side panel and the chat page. */
export function ConversationsProvider({ children }: { children: ReactNode }) {
  const { user, ready } = useAuth();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!session.authToken && !session.guestToken) {
      setConversations([]);
      setLoading(false);
      return;
    }
    try {
      setConversations((await api.conversations()).results);
    } catch {
      /* the list is a convenience; chatting still works without it */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (ready) void refresh();
  }, [ready, user, refresh]);

  const rename = useCallback(async (id: number, title: string) => {
    const updated = await api.renameConversation(id, title);
    setConversations((current) => current.map((item) => (item.id === id ? { ...item, title: updated.title } : item)));
  }, []);

  const remove = useCallback(async (id: number) => {
    await api.deleteConversation(id);
    setConversations((current) => current.filter((item) => item.id !== id));
  }, []);

  const value = useMemo(
    () => ({ conversations, loading, refresh, rename, remove }),
    [conversations, loading, refresh, rename, remove],
  );
  return <ConversationsContext.Provider value={value}>{children}</ConversationsContext.Provider>;
}

export function useConversations() {
  const context = useContext(ConversationsContext);
  if (!context) throw new Error("useConversations must be used inside <ConversationsProvider>");
  return context;
}

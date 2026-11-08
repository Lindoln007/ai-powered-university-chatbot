import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, session, type User } from "../api/client";

interface AuthState {
  user: User | null;
  ready: boolean;
  isAdmin: boolean;
  signIn: (username: string, password: string) => Promise<User>;
  register: (data: Parameters<typeof api.register>[0]) => Promise<User>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

/** Move any conversations started as a guest into the account that just signed in. */
async function adoptGuestConversations() {
  if (!session.guestToken) return;
  try {
    await api.claimGuestConversations();
  } finally {
    session.guestToken = null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!session.authToken) {
      setReady(true);
      return;
    }
    api
      .profile()
      .then(setUser)
      .catch(() => {
        session.authToken = null;
      })
      .finally(() => setReady(true));
  }, []);

  const signIn = useCallback(async (username: string, password: string) => {
    const response = await api.login(username, password);
    session.authToken = response.token;
    await adoptGuestConversations().catch(() => undefined);
    setUser(response.user);
    return response.user;
  }, []);

  const register = useCallback(async (data: Parameters<typeof api.register>[0]) => {
    const response = await api.register(data);
    session.authToken = response.token;
    await adoptGuestConversations().catch(() => undefined);
    setUser(response.user);
    return response.user;
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      /* token may already be invalid; sign out locally regardless */
    }
    session.authToken = null;
    setUser(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({ user, ready, isAdmin: user?.role === "administrator", signIn, register, signOut }),
    [user, ready, signIn, register, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}

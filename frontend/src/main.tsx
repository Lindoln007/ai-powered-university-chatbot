import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";

import "@fontsource-variable/bricolage-grotesque/wght.css";
import "@fontsource-variable/hanken-grotesk";
import "./styles/tokens.css";
import "./styles/app.css";

import { AuthProvider } from "./auth/AuthContext";
import { AppShell } from "./components/AppShell";
import { ToastProvider } from "./components/Toast";
import { ChatPage } from "./pages/ChatPage";
import { SignInPage } from "./pages/SignInPage";
import { StaffPage } from "./pages/StaffPage";
import { TopicsPage } from "./pages/TopicsPage";
import { ConversationsProvider } from "./state/conversations";

function NotFound() {
  return (
    <AppShell>
      <div className="scrollarea">
        <div className="page">
          <div className="notice-card">
            <h1>Page not found</h1>
            <p>The page you were looking for doesn't exist.</p>
            <Link to="/" className="btn btn--primary">
              Back to the chat
            </Link>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <ConversationsProvider>
          <ToastProvider>
            <a href="#main" className="skip-link">
              Skip to content
            </a>
            <Routes>
              <Route path="/" element={<ChatPage />} />
              <Route path="/c/:conversationId" element={<ChatPage />} />
              <Route path="/topics" element={<TopicsPage />} />
              <Route path="/signin" element={<SignInPage />} />
              <Route path="/staff" element={<StaffPage />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </ToastProvider>
        </ConversationsProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);

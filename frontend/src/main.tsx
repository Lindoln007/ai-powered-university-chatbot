import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";

import "@fontsource-variable/literata/wght.css";
import "@fontsource-variable/atkinson-hyperlegible-next";
import "./styles/tokens.css";
import "./styles/app.css";

import { AuthProvider } from "./auth/AuthContext";
import { TopBar } from "./components/TopBar";
import { ChatPage } from "./pages/ChatPage";
import { SignInPage } from "./pages/SignInPage";
import { StaffPage } from "./pages/StaffPage";

function NotFound() {
  return (
    <div className="app">
      <TopBar />
      <main className="staff staff--locked" id="main">
        <h1 className="staff__title">Page not found</h1>
        <p>The page you were looking for doesn't exist.</p>
        <Link to="/" className="button">
          Back to Campus Desk
        </Link>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/c/:conversationId" element={<ChatPage />} />
          <Route path="/signin" element={<SignInPage />} />
          <Route path="/staff" element={<StaffPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);

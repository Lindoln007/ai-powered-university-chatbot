import { useEffect, useState } from "react";
import { BarChart3, LogIn, LogOut, Menu, Moon, Sun } from "lucide-react";
import { Link, NavLink, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../lib/theme";

interface Props {
  onToggleRail?: () => void;
  railOpen?: boolean;
}

export function TopBar({ onToggleRail, railOpen }: Props) {
  const { user, isAdmin, signOut } = useAuth();
  const { theme, toggle } = useTheme();
  const navigate = useNavigate();
  const [demoMode, setDemoMode] = useState<boolean | null>(null);

  useEffect(() => {
    api
      .health()
      .then((health) => setDemoMode(health.demo_mode))
      .catch(() => setDemoMode(null));
  }, []);

  return (
    <header className="topbar">
      {onToggleRail && (
        <button
          type="button"
          className="icon-button topbar__rail-toggle"
          onClick={onToggleRail}
          aria-label={railOpen ? "Hide conversations" : "Show conversations"}
          aria-expanded={railOpen}
          aria-controls="conversation-rail"
        >
          <Menu aria-hidden="true" size={20} />
        </button>
      )}

      <Link to="/" className="wordmark" aria-label="Campus Desk, home">
        <span className="wordmark__name">Campus Desk</span>
        <span className="wordmark__institution">DMI St. John the Baptist University</span>
      </Link>

      {demoMode && (
        <details className="prototype-note">
          <summary>
            <span className="hide-narrow">Prototype</span>
            <span className="show-narrow">Demo</span>
          </summary>
          <div className="prototype-note__panel">
            <p>
              This is an academic prototype. Most answers use <strong>hypothetical demonstration information</strong>,
              not official university information. Each answer says which kind it is.
            </p>
            <p>Always confirm fees, dates and requirements with the relevant university office.</p>
          </div>
        </details>
      )}

      <div className="topbar__actions">
        {isAdmin && (
          <NavLink to="/staff" className="button button--quiet button--small">
            <BarChart3 aria-hidden="true" size={16} />
            <span className="hide-narrow">Staff</span>
          </NavLink>
        )}
        <button
          type="button"
          className="icon-button"
          onClick={toggle}
          aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
        >
          {theme === "dark" ? <Sun aria-hidden="true" size={18} /> : <Moon aria-hidden="true" size={18} />}
        </button>
        {user ? (
          <div className="account">
            <span className="account__name hide-narrow">{user.first_name || user.username}</span>
            <button
              type="button"
              className="icon-button"
              aria-label={`Sign out ${user.username}`}
              onClick={async () => {
                await signOut();
                navigate("/");
              }}
            >
              <LogOut aria-hidden="true" size={18} />
            </button>
          </div>
        ) : (
          <Link to="/signin" className="button button--quiet button--small">
            <LogIn aria-hidden="true" size={16} className="hide-narrow" />
            Sign in
          </Link>
        )}
      </div>
    </header>
  );
}

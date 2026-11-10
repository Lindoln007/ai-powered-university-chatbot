import { useState, type FormEvent, type ReactNode } from "react";
import { ArrowLeft, History, MonitorSmartphone, ShieldCheck } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Horizon, Mark } from "../components/Brand";

type Mode = "signin" | "register";

function Field({ id, label, error, hint, children }: { id: string; label: string; error?: string; hint?: string; children: ReactNode }) {
  return (
    <div className={`field${error ? " is-invalid" : ""}`}>
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && !error && (
        <p className="field__hint" id={`${id}-hint`}>
          {hint}
        </p>
      )}
      {error && (
        <p className="field__error" id={`${id}-error`}>
          {error}
        </p>
      )}
    </div>
  );
}

export function SignInPage() {
  const { signIn, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>("signin");
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const value = (name: string) => String(form.get(name) ?? "");
    setBusy(true);
    setError(null);
    try {
      if (mode === "signin") {
        await signIn(value("username"), value("password"));
      } else {
        await register({
          username: value("username"),
          email: value("email"),
          first_name: value("first_name"),
          last_name: value("last_name"),
          password: value("password"),
          password_confirm: value("password_confirm"),
          role: value("role") === "student" ? "student" : "prospective_student",
        });
      }
      navigate("/");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, "error", "Something went wrong. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  const fieldError = (name: string) => error?.field(name);
  const aria = (name: string, hint = false) => ({
    "aria-describedby": fieldError(name) ? `${name}-error` : hint ? `${name}-hint` : undefined,
    "aria-invalid": Boolean(fieldError(name)) || undefined,
  });
  const formError = error && !error.details ? error.message : error?.details?.non_field_errors?.[0];

  return (
    <div className="auth">
      <aside className="auth__art">
        <Horizon />
        <Link to="/" className="brandlink">
          <Mark size={38} />
          <span className="brandlink__name">Campus Desk</span>
        </Link>
        <div className="auth__pitch">
          <h2>Answers about university life, whenever you need them.</h2>
          <ul>
            <li>
              <History aria-hidden="true" size={20} />
              Your chats are saved, so you can return to an answer later.
            </li>
            <li>
              <MonitorSmartphone aria-hidden="true" size={20} />
              Pick up on any phone or computer.
            </li>
            <li>
              <ShieldCheck aria-hidden="true" size={20} />
              Every answer shows its source and whether it is verified.
            </li>
          </ul>
        </div>
      </aside>

      <main className="auth__main" id="main">
        <Link to="/" className="inline-link auth__back">
          <ArrowLeft aria-hidden="true" size={16} /> Keep chatting as a guest
        </Link>
        <h1>{mode === "signin" ? "Welcome back" : "Create your account"}</h1>

        <div className="segmented" role="tablist" aria-label="Account">
          {(["signin", "register"] as const).map((option) => (
            <button
              key={option}
              type="button"
              role="tab"
              aria-selected={mode === option}
              className={mode === option ? "is-active" : ""}
              onClick={() => {
                setMode(option);
                setError(null);
              }}
            >
              {option === "signin" ? "Sign in" : "Create account"}
            </button>
          ))}
        </div>

        <form className="form" onSubmit={onSubmit} noValidate key={mode}>
          {formError && (
            <div className="form__error" role="alert">
              {formError}
            </div>
          )}

          {mode === "signin" ? (
            <>
              <Field id="username" label="Username or email" error={fieldError("username")}>
                <input id="username" name="username" autoComplete="username" required autoFocus {...aria("username")} />
              </Field>
              <Field id="password" label="Password" error={fieldError("password")}>
                <input id="password" name="password" type="password" autoComplete="current-password" required {...aria("password")} />
              </Field>
            </>
          ) : (
            <>
              <div className="form__row">
                <Field id="first_name" label="First name" error={fieldError("first_name")}>
                  <input id="first_name" name="first_name" autoComplete="given-name" autoFocus />
                </Field>
                <Field id="last_name" label="Last name" error={fieldError("last_name")}>
                  <input id="last_name" name="last_name" autoComplete="family-name" />
                </Field>
              </div>
              <Field id="username" label="Username" error={fieldError("username")}>
                <input id="username" name="username" autoComplete="username" required {...aria("username")} />
              </Field>
              <Field id="email" label="Email" error={fieldError("email")}>
                <input id="email" name="email" type="email" autoComplete="email" required {...aria("email")} />
              </Field>
              <fieldset className="choices">
                <legend>I am a</legend>
                <label>
                  <input type="radio" name="role" value="prospective_student" defaultChecked />
                  Prospective student
                </label>
                <label>
                  <input type="radio" name="role" value="student" />
                  Current student
                </label>
              </fieldset>
              <Field id="password" label="Password" error={fieldError("password")} hint="At least 8 characters, not only numbers, and not a common password.">
                <input id="password" name="password" type="password" autoComplete="new-password" required {...aria("password", true)} />
              </Field>
              <Field id="password_confirm" label="Confirm password" error={fieldError("password_confirm")}>
                <input id="password_confirm" name="password_confirm" type="password" autoComplete="new-password" required {...aria("password_confirm")} />
              </Field>
            </>
          )}

          <button type="submit" className="btn btn--primary btn--block" disabled={busy}>
            {busy ? "Please wait…" : mode === "signin" ? "Sign in" : "Create account"}
          </button>
        </form>
      </main>
    </div>
  );
}

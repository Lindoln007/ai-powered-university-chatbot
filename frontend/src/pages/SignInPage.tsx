import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { TopBar } from "../components/TopBar";

type Mode = "signin" | "register";

function Field({
  id,
  label,
  error,
  hint,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className={`field${error ? " field--invalid" : ""}`}>
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
  const describedBy = (name: string, hint = false) =>
    fieldError(name) ? `${name}-error` : hint ? `${name}-hint` : undefined;
  const formLevelError = error && !error.details ? error.message : error?.details?.non_field_errors?.[0];

  return (
    <div className="app">
      <TopBar />
      <main className="auth" id="main">
        <div className="auth__intro">
          <h1 className="auth__title">{mode === "signin" ? "Sign in" : "Create an account"}</h1>
          <p className="auth__lede">
            An account keeps your conversations, so you can return to an answer on any device. You can also{" "}
            <Link to="/">keep chatting as a guest</Link>.
          </p>
        </div>

        <div className="auth__switch" role="tablist" aria-label="Account">
          {(["signin", "register"] as const).map((option) => (
            <button
              key={option}
              type="button"
              role="tab"
              aria-selected={mode === option}
              className={`auth__tab${mode === option ? " auth__tab--active" : ""}`}
              onClick={() => {
                setMode(option);
                setError(null);
              }}
            >
              {option === "signin" ? "Sign in" : "Create account"}
            </button>
          ))}
        </div>

        <form className="auth__form" onSubmit={onSubmit} noValidate key={mode}>
          {formLevelError && (
            <div className="form-error" role="alert">
              {formLevelError}
            </div>
          )}

          {mode === "signin" ? (
            <>
              <Field id="username" label="Username or email" error={fieldError("username")}>
                <input id="username" name="username" autoComplete="username" required autoFocus aria-describedby={describedBy("username")} aria-invalid={Boolean(fieldError("username")) || undefined} />
              </Field>
              <Field id="password" label="Password" error={fieldError("password")}>
                <input id="password" name="password" type="password" autoComplete="current-password" required aria-describedby={describedBy("password")} aria-invalid={Boolean(fieldError("password")) || undefined} />
              </Field>
            </>
          ) : (
            <>
              <div className="field-row">
                <Field id="first_name" label="First name" error={fieldError("first_name")}>
                  <input id="first_name" name="first_name" autoComplete="given-name" autoFocus />
                </Field>
                <Field id="last_name" label="Last name" error={fieldError("last_name")}>
                  <input id="last_name" name="last_name" autoComplete="family-name" />
                </Field>
              </div>
              <Field id="username" label="Username" error={fieldError("username")}>
                <input id="username" name="username" autoComplete="username" required aria-describedby={describedBy("username")} aria-invalid={Boolean(fieldError("username")) || undefined} />
              </Field>
              <Field id="email" label="Email" error={fieldError("email")}>
                <input id="email" name="email" type="email" autoComplete="email" required aria-describedby={describedBy("email")} aria-invalid={Boolean(fieldError("email")) || undefined} />
              </Field>
              <fieldset className="field field--choices">
                <legend>I am a</legend>
                <label className="choice">
                  <input type="radio" name="role" value="prospective_student" defaultChecked />
                  Prospective student
                </label>
                <label className="choice">
                  <input type="radio" name="role" value="student" />
                  Current student
                </label>
              </fieldset>
              <Field id="password" label="Password" error={fieldError("password")} hint="At least 8 characters, not only numbers, and not a common password.">
                <input id="password" name="password" type="password" autoComplete="new-password" required aria-describedby={describedBy("password", true)} aria-invalid={Boolean(fieldError("password")) || undefined} />
              </Field>
              <Field id="password_confirm" label="Confirm password" error={fieldError("password_confirm")}>
                <input id="password_confirm" name="password_confirm" type="password" autoComplete="new-password" required aria-describedby={describedBy("password_confirm")} aria-invalid={Boolean(fieldError("password_confirm")) || undefined} />
              </Field>
            </>
          )}

          <button type="submit" className="button auth__submit" disabled={busy}>
            {busy ? "Please wait…" : mode === "signin" ? "Sign in" : "Create account"}
          </button>
        </form>
      </main>
    </div>
  );
}

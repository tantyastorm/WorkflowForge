import { useEffect, useState, type SyntheticEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";

import { PageContainer } from "../../components/layout/PageContainer";
import { useAuth } from "./auth-context";
import { destinationFromState } from "./navigation";

export function LoginPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitted, setSubmitted] = useState(false);

  useEffect(
    () => () => {
      setPassword("");
    },
    [],
  );

  if (auth.status === "authenticated") {
    return <Navigate to={auth.selectedOrganizationId === null ? "/select-organization" : "/app"} />;
  }

  async function handleSubmit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
    try {
      await auth.login(email, password);
      void navigate(destinationFromState(location.state), { replace: true });
    } catch {
      setSubmitted(false);
    } finally {
      setPassword("");
    }
  }

  const busy = submitted || auth.status === "authenticating";

  return (
    <PageContainer>
      <div className="auth-page">
        <section className="auth-panel" aria-labelledby="login-heading">
          <div>
            <p className="auth-eyebrow">Secure operator access</p>
            <h1 id="login-heading">Sign in</h1>
          </div>
          {auth.error !== null ? (
            <div className="auth-alert" role="alert">
              <strong>{auth.error.title}</strong>
              <span>{auth.error.message}</span>
            </div>
          ) : null}
          <form className="auth-form" onSubmit={(event) => void handleSubmit(event)}>
            <label>
              Email
              <input
                autoComplete="email"
                inputMode="email"
                name="email"
                required
                type="email"
                value={email}
                onChange={(event) => {
                  setEmail(event.target.value);
                }}
              />
            </label>
            <label>
              Password
              <input
                autoComplete="current-password"
                name="password"
                required
                type="password"
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                }}
              />
            </label>
            <button className="button" type="submit" disabled={busy}>
              {busy ? "Signing in" : "Sign in"}
            </button>
          </form>
        </section>
      </div>
    </PageContainer>
  );
}

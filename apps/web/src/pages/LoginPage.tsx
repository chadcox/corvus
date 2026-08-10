import { FormEvent, useState } from "react";
import { Navigate } from "react-router-dom";
import { api, setAuthToken, AuthUser } from "../api/client";

type Props = {
  user: AuthUser | null;
  onLogin: (user: AuthUser) => void;
};

export default function LoginPage({ user, onLogin }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (user) return <Navigate to="/" replace />;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.login(username.trim(), password);
      setAuthToken(result.access_token);
      onLogin(result.user);
    } catch (err) {
      setError(String(err));
      setLoading(false);
    }
  };

  return (
    <div className="login-wrap">
      <div className="panel login-panel">
        <h1 className="page-title">Sign in</h1>
        <p className="panel-desc">Use your local Corvus username and password.</p>
        <form onSubmit={onSubmit} className="create-case-form">
          <div className="field">
            <label className="field-label" htmlFor="username">Username</label>
            <input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Username"
              autoComplete="username"
              required
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="password">Password</label>
            <div className="password-field">
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password"
                autoComplete="current-password"
                required
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPassword((s) => !s)}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? "🙈" : "👁"}
              </button>
            </div>
          </div>
          <button type="submit" disabled={loading || !username.trim() || !password}>
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
        {error && <div className="alert alert-error" style={{ marginTop: "0.85rem" }}>{error}</div>}
      </div>
    </div>
  );
}

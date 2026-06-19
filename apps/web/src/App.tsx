import { useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import CasesPage from "./pages/CasesPage";
import CaseDetailPage from "./pages/CaseDetailPage";
import LoginPage from "./pages/LoginPage";
import AdminUsersPage from "./pages/AdminUsersPage";
import ControlPanelPage from "./pages/ControlPanelPage";
import { api, ApiAuthError, AuthUser, setAuthToken } from "./api/client";

function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 28 28" fill="none" aria-hidden="true">
      <rect x="1" y="1" width="26" height="26" rx="4" stroke="currentColor" strokeWidth="1.5" opacity="0.3" />
      <path
        d="M7 19 L14 7 L21 19 M9.5 15 H18.5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="14" cy="7" r="2" fill="currentColor" />
    </svg>
  );
}

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const isCaseView = location.pathname.startsWith("/cases/");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loadingUser, setLoadingUser] = useState(true);

  useEffect(() => {
    api
      .me()
      .then((u) => setUser(u))
      .catch((err) => {
        if (err instanceof ApiAuthError) setUser(null);
      })
      .finally(() => setLoadingUser(false));
  }, []);

  const onLogout = async () => {
    try {
      await api.logout();
    } catch {
      // no-op
    }
    setAuthToken(null);
    setUser(null);
    navigate("/login");
  };

  if (loadingUser) return <main className="app-main">Loading…</main>;
  const authed = !!user;

  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/" className="brand">
          <BrandMark />
          Corvus
        </Link>
        <span className="header-divider" aria-hidden="true" />
        <span className="tagline">
          {isCaseView ? "Investigation workspace" : "Forensic evidence review"}
        </span>
        <span className="header-spacer" />
        {user?.role === "administrator" && <Link to="/admin/control-panel">Control Panel</Link>}
        {user && (
          <>
            <span className="header-badge">{user.username}</span>
            <button className="secondary" onClick={onLogout}>Logout</button>
          </>
        )}
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/login" element={<LoginPage user={user} onLogin={setUser} />} />
          <Route path="/" element={authed ? <CasesPage /> : <Navigate to="/login" replace />} />
          <Route path="/cases/:caseId" element={authed ? <CaseDetailPage /> : <Navigate to="/login" replace />} />
          <Route
            path="/admin/users"
            element={authed && user ? <AdminUsersPage me={user} /> : <Navigate to="/login" replace />}
          />
          <Route
            path="/admin/control-panel"
            element={authed && user ? <ControlPanelPage me={user} /> : <Navigate to="/login" replace />}
          />
        </Routes>
      </main>
    </div>
  );
}

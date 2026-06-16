import { FormEvent, useEffect, useState } from "react";
import { api, AuthUser } from "../api/client";

type Props = {
  me: AuthUser;
};

export default function AdminUsersPage({ me }: Props) {
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"administrator" | "analyst">("analyst");
  const [error, setError] = useState<string | null>(null);
  const activeAdminCount = users.filter((u) => u.role === "administrator" && u.is_active).length;

  const load = () => {
    api.listUsers().then(setUsers).catch((e) => setError(String(e)));
  };

  useEffect(() => {
    load();
  }, []);

  const onCreate = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    await api.createUser({ username: username.trim(), password, role });
    setUsername("");
    setPassword("");
    setRole("analyst");
    load();
  };

  if (me.role !== "administrator") {
    return <div className="alert alert-error">Forbidden (403): administrator role required.</div>;
  }

  return (
    <div className="panel" style={{ marginTop: "1rem" }}>
      <h2>User management</h2>
      <form onSubmit={onCreate} className="create-case-form" style={{ marginBottom: "1rem" }}>
        <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Username" required />
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" required />
        <select value={role} onChange={(e) => setRole(e.target.value as "administrator" | "analyst")}>
          <option value="analyst">analyst</option>
          <option value="administrator">administrator</option>
        </select>
        <button type="submit" disabled={!username.trim() || password.length < 8}>Create user</button>
      </form>
      {error && <div className="alert alert-error" style={{ marginBottom: "1rem" }}>{error}</div>}
      <div className="stack">
        {users.map((u) => (
          <div key={u.id} className="status-item" style={{ display: "grid", gap: "0.55rem" }}>
            <div><strong>{u.username}</strong> ({u.role}) {u.is_active ? "active" : "disabled"}</div>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <button
                className="secondary"
                disabled={u.role === "administrator" && u.is_active && activeAdminCount <= 1}
                title={u.role === "administrator" && u.is_active && activeAdminCount <= 1 ? "Cannot demote the last active administrator" : ""}
                onClick={() => api.updateUserRole(u.id, u.role === "administrator" ? "analyst" : "administrator").then(load)}
              >
                Set role: {u.role === "administrator" ? "analyst" : "administrator"}
              </button>
              <button
                className="secondary"
                disabled={u.role === "administrator" && u.is_active && activeAdminCount <= 1}
                title={u.role === "administrator" && u.is_active && activeAdminCount <= 1 ? "Cannot disable the last active administrator" : ""}
                onClick={() => api.updateUserActive(u.id, !u.is_active).then(load)}
              >
                {u.is_active ? "Disable" : "Enable"}
              </button>
              <button
                className="secondary"
                onClick={() => {
                  const next = window.prompt(`Set new password for ${u.username} (min 8 chars):`);
                  if (!next || next.length < 8) return;
                  api.resetUserPassword(u.id, next).then(load);
                }}
              >
                Reset password
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

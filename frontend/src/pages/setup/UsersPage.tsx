import { useState } from "react";
import { api } from "../../api";
import { useSession } from "../../session";
import type { PermissionInfo, User, UserDetail } from "../../types";
import { ActionButton, ConfirmModal, ErrorBox, FormModal, Loading } from "../../ui";
import { useLoad } from "../../useLoad";

type Dialog =
  | { kind: "add" }
  | { kind: "deactivate"; user: User }
  | { kind: "reactivate"; user: User }
  | { kind: "permissions"; user: User };

export function UsersPage() {
  const { me } = useSession();
  const { data, error, reload } = useLoad(() => api.get<User[]>("/users"));
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const close = () => { setDialog(null); reload(); };

  if (!data) return error ? <ErrorBox error={error} /> : <Loading />;
  return (
    <div className="stack">
      <div className="row between">
        <h1>Users</h1>
        <ActionButton className="primary" onClick={() => setDialog({ kind: "add" })}>Add user</ActionButton>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th /></tr></thead>
          <tbody>
            {data.map((u) => {
              const editable = u.role_code !== "tenant_admin" && u.id !== me?.id;
              return (
                <tr key={u.id}>
                  <td>{u.name}</td>
                  <td>{u.email}</td>
                  <td>{u.role_code.replace("_", " ")}</td>
                  <td>{u.is_active ? "Active" : "Deactivated"}</td>
                  <td className="num">
                    {editable && (
                      <>
                        <ActionButton className="link" onClick={() => setDialog({ kind: "permissions", user: u })}>Permissions</ActionButton>
                        {u.is_active
                          ? <ActionButton className="link" onClick={() => setDialog({ kind: "deactivate", user: u })}>Deactivate</ActionButton>
                          : <ActionButton className="link" onClick={() => setDialog({ kind: "reactivate", user: u })}>Reactivate</ActionButton>}
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {dialog?.kind === "add" && <AddUserDialog onClose={close} />}
      {dialog?.kind === "deactivate" && (
        <ConfirmModal title={`Deactivate ${dialog.user.name}?`} danger confirmLabel="Deactivate"
                      message="They are logged out immediately and can't log in until reactivated."
                      onConfirm={() => api.post(`/users/${dialog.user.id}/deactivate`)} onClose={close} />
      )}
      {dialog?.kind === "reactivate" && (
        <ConfirmModal title={`Reactivate ${dialog.user.name}?`} confirmLabel="Reactivate"
                      message="They can log in again with their existing password."
                      onConfirm={() => api.post(`/users/${dialog.user.id}/reactivate`)} onClose={close} />
      )}
      {dialog?.kind === "permissions" && <PermissionsDialog user={dialog.user} onClose={close} />}
    </div>
  );
}

function AddUserDialog({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("receptionist");
  return (
    <FormModal title="Add user" submitLabel="Create user" onClose={onClose}
               onSubmit={() => api.post("/users", { name, email, password, role_code: role })}>
      <label>Name<input value={name} onChange={(e) => setName(e.target.value)} required autoFocus /></label>
      <label>Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
      <label>Password (at least 8 characters)<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} autoComplete="new-password" /></label>
      <label>Role
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="receptionist">Receptionist</option>
          <option value="manager">Manager</option>
        </select>
      </label>
    </FormModal>
  );
}

// Per-user permission overrides (DL-R05): the role gives defaults; grant adds, deny removes.
function PermissionsDialog({ user, onClose }: { user: User; onClose: () => void }) {
  const { data: detail } = useLoad(() => api.get<UserDetail>(`/users/${user.id}`), [user.id]);
  const { data: catalogue } = useLoad(() => api.get<PermissionInfo[]>("/users/permission-catalogue"));
  const [choices, setChoices] = useState<Record<string, "default" | "grant" | "deny"> | null>(null);
  const [reason, setReason] = useState("");

  if (!detail || !catalogue) return null;
  const current = choices ?? Object.fromEntries(detail.overrides.map((o) => [o.permission_code, o.effect]));
  const set = (code: string, value: "default" | "grant" | "deny") => setChoices({ ...current, [code]: value });

  const save = () => api.put(`/users/${user.id}/overrides`, {
    overrides: Object.entries(current)
      .filter(([, effect]) => effect !== "default")
      .map(([permission_code, effect]) => ({ permission_code, effect, reason: reason || null })),
  });

  return (
    <FormModal title={`Permissions · ${user.name} (${user.role_code})`} submitLabel="Save" onClose={onClose} onSubmit={save}>
      <div className="table-wrap" style={{ maxHeight: "50vh", overflow: "auto" }}>
        <table>
          <thead><tr><th>Permission</th><th>Role gives</th><th>Setting</th></tr></thead>
          <tbody>
            {catalogue.map((p) => {
              const fromRole = p.roles.includes(user.role_code);
              const value = current[p.code] ?? "default";
              return (
                <tr key={p.code}>
                  <td>{p.description}<div className="muted">{p.code}</div></td>
                  <td>{fromRole ? "Yes" : "No"}</td>
                  <td>
                    <select value={value} onChange={(e) => set(p.code, e.target.value as "default" | "grant" | "deny")}>
                      <option value="default">Default ({fromRole ? "yes" : "no"})</option>
                      {!fromRole && <option value="grant">Grant</option>}
                      {fromRole && <option value="deny">Deny</option>}
                    </select>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <label>Reason (optional)<input value={reason} onChange={(e) => setReason(e.target.value)} /></label>
    </FormModal>
  );
}

import { useState } from "react";
import { api } from "../api";
import { dateTime } from "../format";
import type { AuditEvent } from "../types";
import { ErrorBox, Loading } from "../ui";
import { useLoad } from "../useLoad";

const PAGE = 50;

// "system" = the posting engine / CLI; "anonymous" = e.g. a failed login.
function who(e: AuditEvent): string {
  return e.actor_name ?? (e.actor_type === "system" ? "System" : e.actor_type === "anonymous" ? "Unknown (not logged in)" : e.actor_type);
}

export function AuditPage() {
  const [action, setAction] = useState("");
  const [page, setPage] = useState(0);
  const { data, error } = useLoad(
    () => api.get<AuditEvent[]>("/audit", { action: action || undefined, limit: PAGE, offset: page * PAGE }),
    [action, page],
  );

  return (
    <div className="stack">
      <h1>Audit trail</h1>
      <label style={{ maxWidth: 280 }}>
        Action (exact, e.g. stay.checked_in)
        <input value={action} onChange={(e) => { setAction(e.target.value.trim()); setPage(0); }} />
      </label>
      {!data ? (error ? <ErrorBox error={error} /> : <Loading />) : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>When</th><th>Who</th><th>Action</th><th>What</th><th>Reason</th></tr></thead>
            <tbody>
              {data.map((e) => (
                <tr key={e.id}>
                  <td>{dateTime(e.created_at)}</td>
                  <td>{who(e)}</td>
                  <td>{e.action}</td>
                  <td>{e.summary}</td>
                  <td>{e.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="row end">
        <button className="secondary small" disabled={page === 0} onClick={() => setPage(page - 1)}>Newer</button>
        <button className="secondary small" disabled={(data?.length ?? 0) < PAGE} onClick={() => setPage(page + 1)}>Older</button>
      </div>
    </div>
  );
}

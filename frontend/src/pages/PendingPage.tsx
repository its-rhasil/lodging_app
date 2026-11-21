import { Link } from "react-router";
import { api } from "../api";
import { dateTime, money } from "../format";
import type { StaySummary } from "../types";
import { ErrorBox, Loading } from "../ui";
import { useLoad } from "../useLoad";

// Checked-out guests who still owe (DL-P08). Open a row to take the payment.
export function PendingPage() {
  const { data, error } = useLoad(() => api.get<StaySummary[]>("/stays/pending-balances", { limit: 200 }));

  if (!data) return error ? <ErrorBox error={error} /> : <Loading />;
  return (
    <div className="stack">
      <h1>Pending balances</h1>
      {data.length === 0 ? (
        <p className="muted">Nobody owes anything. 🎉</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Guest</th><th>Room</th><th>Checked out</th><th>Reason</th><th className="num">Owes</th><th />
              </tr>
            </thead>
            <tbody>
              {data.map((s) => (
                <tr key={s.id}>
                  <td>{s.guest_name}<div className="muted">{s.guest_phone}</div></td>
                  <td>{s.room_number}</td>
                  <td>{dateTime(s.actual_checkout_at)}</td>
                  <td>{s.forced_checkout_reason}</td>
                  <td className="num owes">{money(s.balance)}</td>
                  <td><Link to={`/stays/${s.id}`}>Take payment</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

import { useState } from "react";
import { api } from "../../api";
import { money } from "../../format";
import type { RoomType, StayPlan } from "../../types";
import { ActionButton, ErrorBox, FormModal, Loading } from "../../ui";
import { useLoad } from "../../useLoad";

export function RoomTypesPage() {
  const { data: types, error, reload } = useLoad(() => api.get<RoomType[]>("/room-types"));
  const { data: plans } = useLoad(() => api.get<StayPlan[]>("/stay-plans"));
  const [editing, setEditing] = useState<RoomType | "new" | null>(null);

  if (!types || !plans) return error ? <ErrorBox error={error} /> : <Loading />;
  const planName = (id: number) => plans.find((p) => p.id === id)?.name ?? `Plan ${id}`;

  return (
    <div className="stack">
      <div className="row between">
        <h1>Room types &amp; rates</h1>
        <ActionButton className="primary" onClick={() => setEditing("new")}>Add room type</ActionButton>
      </div>
      {types.map((t) => (
        <div key={t.id} className="card stack">
          <div className="row between">
            <h2>{t.name} <span className="muted">· up to {t.capacity} · {t.is_active ? "active" : "inactive"}</span></h2>
            <button className="link" onClick={() => setEditing(t)}>Edit</button>
          </div>
          <div className="row">
            {t.rates.map((r) => (
              <span key={`${r.stay_plan_id}-${r.occupancy}`} className="pill">
                {planName(r.stay_plan_id)} · {r.occupancy} guest(s) · {money(r.price)}
              </span>
            ))}
          </div>
        </div>
      ))}
      {editing && <RoomTypeDialog type={editing === "new" ? null : editing} plans={plans}
                                  onClose={() => { setEditing(null); reload(); }} />}
    </div>
  );
}

// The rate grid: one price box per (plan, occupancy). Full day must be filled for every occupancy.
function RoomTypeDialog({ type, plans, onClose }: { type: RoomType | null; plans: StayPlan[]; onClose: () => void }) {
  const [name, setName] = useState(type?.name ?? "");
  const [capacity, setCapacity] = useState(type?.capacity ?? 2);
  const [active, setActive] = useState(type?.is_active ?? true);
  const [prices, setPrices] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const r of type?.rates ?? []) initial[`${r.stay_plan_id}:${r.occupancy}`] = r.price;
    return initial;
  });
  const visiblePlans = plans.filter((p) => p.is_active || type?.rates.some((r) => r.stay_plan_id === p.id));

  const rates = () => Object.entries(prices)
    .filter(([key, price]) => price !== "" && Number(key.split(":")[1]) <= capacity)
    .map(([key, price]) => {
      const [planId, occupancy] = key.split(":").map(Number);
      return { stay_plan_id: planId, occupancy, price };
    });

  return (
    <FormModal title={type ? `Edit ${type.name}` : "New room type"} submitLabel="Save" onClose={onClose}
               onSubmit={() => type
                 ? api.patch(`/room-types/${type.id}`, { name, capacity, is_active: active, rates: rates() })
                 : api.post("/room-types", { name, capacity, rates: rates() })}>
      <label>Name<input value={name} onChange={(e) => setName(e.target.value)} required autoFocus /></label>
      <label>Max guests<input type="number" min={1} max={50} value={capacity} onChange={(e) => setCapacity(Number(e.target.value))} required /></label>
      {type && <label className="check"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />Active</label>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Plan</th>{Array.from({ length: capacity }, (_, i) => <th key={i}>{i + 1} guest{i ? "s" : ""}</th>)}</tr>
          </thead>
          <tbody>
            {visiblePlans.map((p) => (
              <tr key={p.id}>
                <td>{p.name}{p.is_daily && " *"}</td>
                {Array.from({ length: capacity }, (_, i) => {
                  const key = `${p.id}:${i + 1}`;
                  return (
                    <td key={key}>
                      <input type="number" min="0.01" step="0.01" style={{ width: 90 }} value={prices[key] ?? ""}
                             required={p.is_daily}
                             onChange={(e) => setPrices({ ...prices, [key]: e.target.value })} />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <span className="muted">* Full day needs a price for every number of guests. Leave other plans blank if the room doesn't offer them.</span>
    </FormModal>
  );
}

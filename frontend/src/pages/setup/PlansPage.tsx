import { useState } from "react";
import { api } from "../../api";
import type { StayPlan } from "../../types";
import { ActionButton, ConfirmModal, ErrorBox, FormModal, Loading } from "../../ui";
import { useLoad } from "../../useLoad";

type Dialog = { kind: "edit"; plan: StayPlan | null } | { kind: "toggle"; plan: StayPlan } | { kind: "delete"; plan: StayPlan };

export function PlansPage() {
  const { data, error, reload } = useLoad(() => api.get<StayPlan[]>("/stay-plans"));
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const close = () => { setDialog(null); reload(); };

  if (!data) return error ? <ErrorBox error={error} /> : <Loading />;
  return (
    <div className="stack">
      <div className="row between">
        <h1>Stay plans</h1>
        <ActionButton className="primary" onClick={() => setDialog({ kind: "edit", plan: null })}>Add plan</ActionButton>
      </div>
      <p className="muted">What the lodge sells: Full day (always present), Fresh-up, Hourly… Each period is charged once its time plus the grace has passed.</p>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Name</th><th>Period</th><th>Grace</th><th>Status</th><th /></tr></thead>
          <tbody>
            {data.map((p) => (
              <tr key={p.id}>
                <td>{p.name}{p.is_daily && <span className="muted"> · daily</span>}</td>
                <td>{p.period_hours} h</td>
                <td>{p.grace_minutes} min</td>
                <td>{p.is_active ? "Active" : "Inactive"}</td>
                <td className="num">
                  <button className="link" onClick={() => setDialog({ kind: "edit", plan: p })}>Edit</button>
                  {!p.is_daily && (
                    <>
                      <ActionButton className="link" onClick={() => setDialog({ kind: "toggle", plan: p })}>
                        {p.is_active ? "Deactivate" : "Activate"}
                      </ActionButton>
                      <ActionButton className="link" onClick={() => setDialog({ kind: "delete", plan: p })}>Delete</ActionButton>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {dialog?.kind === "edit" && <PlanDialog plan={dialog.plan} onClose={close} />}
      {dialog?.kind === "toggle" && (
        <ConfirmModal
          title={`${dialog.plan.is_active ? "Deactivate" : "Activate"} ${dialog.plan.name}?`}
          message={dialog.plan.is_active
            ? "It won't be offered at check-in. Guests already on it are not affected."
            : "It will be offered again at check-in for rooms that have a price for it."}
          confirmLabel={dialog.plan.is_active ? "Deactivate" : "Activate"}
          onConfirm={() => api.patch(`/stay-plans/${dialog.plan.id}`, { is_active: !dialog.plan.is_active })}
          onClose={close} />
      )}
      {dialog?.kind === "delete" && (
        <ConfirmModal
          title={`Delete ${dialog.plan.name}?`} danger confirmLabel="Delete"
          message="Its prices are removed from every room type. A plan guests have already stayed on can't be deleted; deactivate it instead."
          onConfirm={() => api.delete(`/stay-plans/${dialog.plan.id}`)}
          onClose={close} />
      )}
    </div>
  );
}

function PlanDialog({ plan, onClose }: { plan: StayPlan | null; onClose: () => void }) {
  const [name, setName] = useState(plan?.name ?? "");
  const [hours, setHours] = useState(String(plan?.period_hours ?? 2));
  const [grace, setGrace] = useState(String(plan?.grace_minutes ?? 15));
  const body = { name, period_hours: Number(hours), grace_minutes: Number(grace) };
  return (
    <FormModal title={plan ? `Edit ${plan.name}` : "New stay plan"} submitLabel="Save" onClose={onClose}
               onSubmit={() => plan ? api.patch(`/stay-plans/${plan.id}`, body) : api.post("/stay-plans", body)}>
      <label>Name<input value={name} onChange={(e) => setName(e.target.value)} required autoFocus /></label>
      <label>Period (hours)<input type="number" min={1} max={24} value={hours} onChange={(e) => setHours(e.target.value)} required disabled={plan?.is_daily} /></label>
      <label>Grace (minutes)<input type="number" min={0} max={240} value={grace} onChange={(e) => setGrace(e.target.value)} required /></label>
      <span className="muted">Changes apply to new check-ins only; guests already in keep their plan's times.</span>
    </FormModal>
  );
}

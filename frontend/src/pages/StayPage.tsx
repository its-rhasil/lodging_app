import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router";
import { ApiError, api } from "../api";
import { TXN_LABELS, balanceClass, dateTime, localInputToIso, money } from "../format";
import { useSession } from "../session";
import { PAYMENT_METHODS, type Offer, type Room, type StayDetail, type StayPlan, type Transaction } from "../types";
import { ActionButton, DateTimeInput, ErrorBox, FormModal, Loading, Modal, ReasonModal } from "../ui";
import { useLoad } from "../useLoad";

type Dialog =
  | { kind: "payment" } | { kind: "charge" } | { kind: "refund" } | { kind: "extend" }
  | { kind: "change-room" } | { kind: "convert" } | { kind: "checkout" } | { kind: "correct-price" }
  | { kind: "cancel" }
  | { kind: "waive"; txn: Transaction } | { kind: "reverse"; txn: Transaction };

export function StayPage() {
  const { stayId } = useParams();
  const navigate = useNavigate();
  const { can } = useSession();
  const { data: stay, error, reload } = useLoad(() => api.get<StayDetail>(`/stays/${stayId}`), [stayId]);
  const { data: plans } = useLoad(() => api.get<StayPlan[]>("/stay-plans"));
  const [dialog, setDialog] = useState<Dialog | null>(null);

  if (!stay) return error ? <ErrorBox error={error} /> : <Loading />;

  const folio = stay.folio;
  const balance = Number(folio.balance);
  const active = stay.status === "active";
  const open = folio.status === "open";
  const isDaily = plans?.find((p) => p.id === stay.stay_plan_id)?.is_daily ?? true;
  // While staying: any payment. After checkout: only towards what is still owed (DL-R22).
  const canPay = can("payment.record") && open && (active || balance > 0);
  const close = () => { setDialog(null); reload(); };

  return (
    <div className="stack">
      <div className="row between">
        <div>
          <h1>Room {stay.room_number} · {stay.guest.full_name}</h1>
          <span className="muted">
            {stay.guest.phone} · {stay.stay_plan_name} · {stay.occupancy} guest(s) · in {dateTime(stay.actual_check_in_at)}
            {stay.actual_checkout_at && ` · out ${dateTime(stay.actual_checkout_at)}`}
          </span>
          {active && (
            <div>
              <strong>Expected checkout: </strong>
              {stay.expected_checkout_at ? dateTime(stay.expected_checkout_at) : <span className="muted">not set</span>}
            </div>
          )}
        </div>
        <div className="stack" style={{ alignItems: "flex-end", gap: 0 }}>
          <span className="muted">{balance > 0 ? "Guest owes" : balance < 0 ? "Guest is owed" : "Balance"}</span>
          <span className={`big-balance ${balanceClass(folio.balance)}`}>{money(Math.abs(balance))}</span>
          <span className="muted">Folio {folio.status}{!active && ` · stay ${stay.status.replace("_", " ")}`}</span>
        </div>
      </div>

      <div className="card row">
        <span>Price {money(stay.agreed_price)} / {stay.period_hours === 24 ? "day" : `${stay.period_hours}h`}</span>
        {Number(stay.discount_percent) > 0 && (
          <span className="muted">listed {money(stay.listed_price)} · {stay.discount_percent}% off</span>
        )}
        <span className="muted">grace {stay.grace_minutes} min</span>
        {active && can("folio.reverse") && (
          <ActionButton className="link" onClick={() => setDialog({ kind: "correct-price" })}>Correct price</ActionButton>
        )}
      </div>

      <div className="row">
        {canPay && <ActionButton className="primary" onClick={() => setDialog({ kind: "payment" })}>Take payment</ActionButton>}
        {active && can("folio.post_charge") && <ActionButton onClick={() => setDialog({ kind: "charge" })}>Add charge</ActionButton>}
        {active && balance < 0 && can("payment.refund") && <ActionButton onClick={() => setDialog({ kind: "refund" })}>Refund</ActionButton>}
        {active && can("stay.change_room") && <ActionButton onClick={() => setDialog({ kind: "change-room" })}>Change room</ActionButton>}
        {active && !isDaily && can("stay.convert_to_daily") && <ActionButton onClick={() => setDialog({ kind: "convert" })}>Convert to full day</ActionButton>}
        {active && can("stay.extend") && <ActionButton onClick={() => setDialog({ kind: "extend" })}>Extend</ActionButton>}
        {active && can("stay.check_out") && (
          <ActionButton className="danger" onClick={() => setDialog({ kind: "checkout" })}>Check out</ActionButton>
        )}
        {active && can("stay.check_in") && (
          <ActionButton className="secondary" onClick={() => setDialog({ kind: "cancel" })}>Cancel check-in</ActionButton>
        )}
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>When</th><th>Type</th><th>Details</th><th className="num">Amount</th><th /></tr>
          </thead>
          <tbody>
            {folio.transactions.map((t) => (
              <tr key={t.id} className={t.is_reversed ? "reversed" : ""}>
                <td>{dateTime(t.period_start_at ?? t.created_at)}</td>
                <td>{TXN_LABELS[t.txn_type]}</td>
                <td>
                  {t.description}
                  {t.payment_method && ` ${t.payment_method.replace("_", " ")}`}
                  {t.reference && <span className="muted"> · {t.reference}</span>}
                  {t.related_txn_id && <span className="muted"> · for #{t.related_txn_id}</span>}
                  {t.reason && <div className="muted">{t.reason}</div>}
                </td>
                <td className="num">{t.direction === "credit" ? "−" : ""}{money(t.amount)}</td>
                <td className="num">
                  {open && !t.is_reversed && t.waivable_amount !== null && Number(t.waivable_amount) > 0 && can("folio.waive") && (
                    <ActionButton className="link" onClick={() => setDialog({ kind: "waive", txn: t })}>Waive</ActionButton>
                  )}
                  {open && !t.is_reversed && t.txn_type !== "reversal" && can("folio.reverse") && (
                    <ActionButton className="link" onClick={() => setDialog({ kind: "reverse", txn: t })}>Reverse</ActionButton>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {dialog?.kind === "payment" && <PaymentDialog stayId={stay.id} owed={balance} onClose={close} />}
      {dialog?.kind === "charge" && <ChargeDialog stayId={stay.id} onClose={close} />}
      {dialog?.kind === "refund" && <RefundDialog stayId={stay.id} credit={-balance} onClose={close} />}
      {dialog?.kind === "extend" && <ExtendDialog stayId={stay.id} onClose={close} />}
      {dialog?.kind === "change-room" && <ChangeRoomDialog stay={stay} onClose={close} />}
      {dialog?.kind === "convert" && <ConvertDialog stay={stay} onClose={close} />}
      {dialog?.kind === "correct-price" && <CorrectPriceDialog stay={stay} onClose={close} />}
      {dialog?.kind === "cancel" && (
        <ReasonModal title="Cancel this check-in?" submitLabel="Cancel check-in" onClose={close}
                     label="All charges are reversed and the room becomes available. Why is it being cancelled?"
                     onSubmit={async (reason) => {
                       await api.post(`/stays/${stay.id}/cancel`, { reason });
                       navigate("/");
                     }} />
      )}
      {dialog?.kind === "waive" && <WaiveDialog stayId={stay.id} txn={dialog.txn} onClose={close} />}
      {dialog?.kind === "reverse" && (
        <ReasonModal title={`Reverse ${TXN_LABELS[dialog.txn.txn_type].toLowerCase()} ${money(dialog.txn.amount)}`}
                     label="Why is this being reversed?" submitLabel="Reverse" onClose={close}
                     onSubmit={(reason) => api.post(`/stays/${stay.id}/folio/transactions/${dialog.txn.id}/reverse`, { reason })} />
      )}
      {dialog?.kind === "checkout" && <CheckoutDialog stay={stay} balance={balance} onClose={close} />}
    </div>
  );
}

// ---- How this works ----
// Check out opens this dialog instead of checking out at once (owner, 2026-11-23).
// - Default: the checkout time is now (the moment the button in the dialog is pressed).
// - "The guest left earlier": a date + time, sent as checkout_at. The API saves it as the
//   checkout time and stops room charges there. Further back than the lodge's backdate window
//   (Setup → Settings) a reason box appears; the API also requires a manager for that.
// - Leaving with money owed: the API answers reason_required (for the balance). If this user
//   may check out with a balance, the dialog adds "Why is the guest leaving without paying?"
//   and sends the same time again with force_reason. Without that permission the API's own
//   message is shown ("Take the payment, or ask a manager...").
// - charges_after_checkout: a room charge for time after the guest left is already on the
//   bill. The API's message names it; a manager reverses it on this page, then try again.
// - The balance shown is the bill as it stands now; with an earlier time it can only stay the
//   same (later charges block the checkout instead of being dropped silently).
// ---- end ----
function CheckoutDialog({ stay, balance, onClose }: { stay: StayDetail; balance: number; onClose: () => void }) {
  const { can, settings } = useSession();
  const [earlier, setEarlier] = useState(false);
  const [leftLocal, setLeftLocal] = useState("");
  const [backdateReason, setBackdateReason] = useState("");
  const [askBackdateReason, setAskBackdateReason] = useState(false); // the API asked for it
  const [owing, setOwing] = useState<string | null>(null);           // balance owed, once the API says so
  const [forceReason, setForceReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const backdateWindow = settings?.max_backdate_minutes ?? 120;
  const minutesBack = earlier && leftLocal ? (Date.now() - new Date(leftLocal).getTime()) / 60000 : 0;
  const showBackdateReason = earlier && (minutesBack > backdateWindow || askBackdateReason);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post(`/stays/${stay.id}/checkout`, {
        checkout_at: earlier && leftLocal ? localInputToIso(leftLocal) : null,
        backdate_reason: showBackdateReason ? backdateReason.trim() || null : null,
        force_reason: owing !== null ? forceReason.trim() || null : null,
      });
      onClose();
    } catch (err) {
      const field = err instanceof ApiError ? (err.details as { field?: string } | null)?.field : undefined;
      const owed = err instanceof ApiError ? (err.details as { balance?: string } | null)?.balance : undefined;
      if (err instanceof ApiError && err.code === "reason_required" && field === "backdate_reason") {
        setAskBackdateReason(true);
        setError(err);
      } else if (err instanceof ApiError && err.code === "reason_required" && owed && can("folio.close_with_balance")) {
        setOwing(owed);
      } else {
        setError(err);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Check out" onClose={onClose}>
      <form onSubmit={submit} className="stack">
        <div>
          <strong>Room {stay.room_number} · {stay.guest.full_name}</strong>
          <div className="muted">
            {balance > 0 ? `Guest owes ${money(balance)}` : balance < 0 ? `Guest is owed ${money(-balance)}` : "Bill settled"}
          </div>
        </div>

        <label className="check">
          <input type="checkbox" checked={earlier} onChange={(e) => setEarlier(e.target.checked)} />
          The guest left earlier
        </label>
        {earlier ? (
          <label>Left at<DateTimeInput onChange={setLeftLocal} required /></label>
        ) : (
          <span className="muted">Checkout time: now</span>
        )}
        {showBackdateReason && (
          <label>Reason (needed beyond {backdateWindow} min)
            <input value={backdateReason} onChange={(e) => setBackdateReason(e.target.value)} required />
          </label>
        )}

        {owing !== null && (
          <label>
            The guest owes {money(owing)}. The stay moves to Pending balances. Why is the guest leaving without paying?
            <textarea value={forceReason} onChange={(e) => setForceReason(e.target.value)} required rows={3} autoFocus />
          </label>
        )}

        <ErrorBox error={error} />
        <div className="row end">
          <button type="button" className="secondary" onClick={onClose}>Cancel</button>
          <ActionButton type="submit" className="danger" disabled={busy}>
            {busy ? "Saving…" : owing !== null ? "Check out with balance" : "Check out"}
          </ActionButton>
        </div>
      </form>
    </Modal>
  );
}

function MethodSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <label>Method
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {PAYMENT_METHODS.map((m) => <option key={m} value={m}>{m.replace("_", " ")}</option>)}
      </select>
    </label>
  );
}

function PaymentDialog({ stayId, owed, onClose }: { stayId: number; owed: number; onClose: () => void }) {
  const [amount, setAmount] = useState(owed > 0 ? owed.toFixed(2) : "");
  const [method, setMethod] = useState("cash");
  const [reference, setReference] = useState("");
  // One key per submission: a double tap or a retry after a network error records the payment once.
  const [key] = useState(() => crypto.randomUUID());
  return (
    <FormModal title="Take payment" submitLabel="Record payment" onClose={onClose}
               onSubmit={() => api.post(`/stays/${stayId}/folio/payments`,
                 { amount, method, reference: reference || null, idempotency_key: key })}>
      <label>Amount<input type="number" min="0.01" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} required autoFocus /></label>
      <MethodSelect value={method} onChange={setMethod} />
      <label>Reference (optional, e.g. UPI id)<input value={reference} onChange={(e) => setReference(e.target.value)} /></label>
    </FormModal>
  );
}

function ChargeDialog({ stayId, onClose }: { stayId: number; onClose: () => void }) {
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  return (
    <FormModal title="Add charge" submitLabel="Add charge" onClose={onClose}
               onSubmit={() => api.post(`/stays/${stayId}/folio/charges`, { amount, description })}>
      <label>What for<input value={description} onChange={(e) => setDescription(e.target.value)} required autoFocus placeholder="e.g. Dinner, laundry" /></label>
      <label>Amount<input type="number" min="0.01" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} required /></label>
    </FormModal>
  );
}

function RefundDialog({ stayId, credit, onClose }: { stayId: number; credit: number; onClose: () => void }) {
  const [amount, setAmount] = useState(credit.toFixed(2));
  const [method, setMethod] = useState("cash");
  const [reason, setReason] = useState("");
  return (
    <FormModal title="Refund" submitLabel="Record refund" danger onClose={onClose}
               onSubmit={() => api.post(`/stays/${stayId}/folio/refunds`, { amount, method, reason })}>
      <label>Amount (up to {money(credit)})<input type="number" min="0.01" step="0.01" max={credit} value={amount} onChange={(e) => setAmount(e.target.value)} required /></label>
      <MethodSelect value={method} onChange={setMethod} />
      <label>Reason<input value={reason} onChange={(e) => setReason(e.target.value)} required /></label>
    </FormModal>
  );
}

function WaiveDialog({ stayId, txn, onClose }: { stayId: number; txn: Transaction; onClose: () => void }) {
  const [amount, setAmount] = useState(txn.waivable_amount ?? "");
  const [reason, setReason] = useState("");
  return (
    <FormModal title={`Waive part of ${txn.description ?? "charge"}`} submitLabel="Waive" danger onClose={onClose}
               onSubmit={() => api.post(`/stays/${stayId}/folio/transactions/${txn.id}/waive`, { amount, reason })}>
      <label>Amount (up to {money(txn.waivable_amount)})<input type="number" min="0.01" step="0.01" max={txn.waivable_amount ?? undefined} value={amount} onChange={(e) => setAmount(e.target.value)} required /></label>
      <label>Reason<input value={reason} onChange={(e) => setReason(e.target.value)} required placeholder="e.g. late bus, regular guest" /></label>
    </FormModal>
  );
}

function ExtendDialog({ stayId, onClose }: { stayId: number; onClose: () => void }) {
  const [when, setWhen] = useState("");
  return (
    <FormModal title="Extend stay" submitLabel="Save" onClose={onClose}
               onSubmit={() => api.patch(`/stays/${stayId}/extend`, { expected_checkout_at: localInputToIso(when) })}>
      <label>Expected checkout<DateTimeInput onChange={setWhen} required /></label>
      <span className="muted">Charges keep posting while the guest stays; this is only a note for the desk.</span>
    </FormModal>
  );
}

function ChangeRoomDialog({ stay, onClose }: { stay: StayDetail; onClose: () => void }) {
  const { can } = useSession();
  const { data: rooms } = useLoad(() => api.get<Room[]>("/rooms"));
  const free = (rooms ?? []).filter((r) => r.status === "available" && r.is_active && r.id !== stay.room_id);
  const [roomId, setRoomId] = useState("");
  const [price, setPrice] = useState("");
  const [reason, setReason] = useState("");
  return (
    <FormModal title="Change room" submitLabel="Move guest" onClose={onClose}
               onSubmit={() => api.post(`/stays/${stay.id}/change-room`, {
                 new_room_id: Number(roomId), agreed_price: price || null, reason: reason || null })}>
      <label>New room
        <select value={roomId} onChange={(e) => setRoomId(e.target.value)} required>
          <option value="">Choose…</option>
          {free.map((r) => <option key={r.id} value={r.id}>{r.room_number} · {r.room_type_name}</option>)}
        </select>
      </label>
      <label>Price (optional; blank = the new room's listed price)
        <input type="number" min="0.01" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} disabled={!can("stay.override_rate")} />
      </label>
      <label>Why (optional)<input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. AC broken" /></label>
      <span className="muted">Anything already due is charged at the current price first.</span>
    </FormModal>
  );
}

// Warns when a typed price is far below the listed one: usually a typo (e.g. 8 for 800).
function LowPriceWarning({ price, listed }: { price: string; listed: number }) {
  if (!price || !listed) return null;
  const off = ((listed - Number(price)) / listed) * 100;
  if (off <= 50) return null;
  return <div className="error">{money(price)} is {off.toFixed(0)}% below the listed {money(listed)}. Check the amount.</div>;
}

function ConvertDialog({ stay, onClose }: { stay: StayDetail; onClose: () => void }) {
  const { can } = useSession();
  const [price, setPrice] = useState("");
  const { data: offers } = useLoad(
    () => api.get<Offer[]>(`/rooms/${stay.room_id}/offers`, { occupancy: stay.occupancy }), [stay.room_id]);
  const listed = Number(offers?.find((o) => o.is_daily)?.listed_price ?? 0);
  return (
    <FormModal title="Convert to full day" submitLabel="Convert" onClose={onClose}
               onSubmit={() => api.post(`/stays/${stay.id}/convert-to-daily`, { agreed_price: price || null })}>
      <p className="muted">The short-stay charges are reversed and the full-day charge is posted from the original check-in time.</p>
      <label>Price per day (blank = listed {listed ? money(listed) : ""})
        <input type="number" min="0.01" step="0.01" max={listed || undefined} value={price}
               onChange={(e) => setPrice(e.target.value)} disabled={!can("stay.override_rate")} />
      </label>
      <LowPriceWarning price={price} listed={listed} />
    </FormModal>
  );
}

// Fix a wrongly entered price (manager). Charges already posted at the wrong price are re-posted.
function CorrectPriceDialog({ stay, onClose }: { stay: StayDetail; onClose: () => void }) {
  const [price, setPrice] = useState(stay.listed_price);
  const [reason, setReason] = useState("");
  const listed = Number(stay.listed_price);
  return (
    <FormModal title="Correct the price" submitLabel="Correct price" danger onClose={onClose}
               onSubmit={() => api.post(`/stays/${stay.id}/correct-price`, { agreed_price: price, reason })}>
      <p className="muted">
        Now {money(stay.agreed_price)} per {stay.period_hours === 24 ? "day" : "period"} (listed {money(listed)}).
        Room charges already posted at {money(stay.agreed_price)} are reversed and posted again at the new price.
      </p>
      <label>Correct price<input type="number" min="0.01" step="0.01" max={listed} value={price}
                                 onChange={(e) => setPrice(e.target.value)} required autoFocus /></label>
      <LowPriceWarning price={price} listed={listed} />
      <label>Reason<input value={reason} onChange={(e) => setReason(e.target.value)} required placeholder="e.g. typed 8 instead of 800" /></label>
    </FormModal>
  );
}

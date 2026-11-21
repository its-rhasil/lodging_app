import { useEffect, useState, type ButtonHTMLAttributes, type FormEvent, type ReactNode } from "react";
import { errorText } from "./api";
import { useOnline } from "./online";
import { useTheme } from "./theme";

// An action button: disabled while offline or while its action runs.
export function ActionButton({ disabled, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  const online = useOnline();
  return <button {...props} disabled={disabled || !online} title={online ? props.title : "You're offline"} />;
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return <div className="error">{errorText(error)}</div>;
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="link" onClick={onClose} aria-label="Close">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

// A form inside a modal: runs `onSubmit`, shows its error, closes on success.
export function FormModal({ title, submitLabel, onSubmit, onClose, children, danger }: {
  title: string;
  submitLabel: string;
  onSubmit: () => Promise<unknown>;
  onClose: () => void;
  children: ReactNode;
  danger?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit();
      onClose();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title={title} onClose={onClose}>
      <form onSubmit={submit} className="stack">
        {children}
        <ErrorBox error={error} />
        <div className="row end">
          <button type="button" className="secondary" onClick={onClose}>Cancel</button>
          <ActionButton type="submit" className={danger ? "danger" : "primary"} disabled={busy}>
            {busy ? "Saving…" : submitLabel}
          </ActionButton>
        </div>
      </form>
    </Modal>
  );
}

// Reason dialog for forced and override actions (plan.md Day 4).
export function ReasonModal({ title, label, submitLabel, onSubmit, onClose, required = true }: {
  title: string;
  label: string;
  submitLabel: string;
  onSubmit: (reason: string) => Promise<unknown>;
  onClose: () => void;
  required?: boolean;
}) {
  const [reason, setReason] = useState("");
  return (
    <FormModal title={title} submitLabel={submitLabel} danger onClose={onClose} onSubmit={() => onSubmit(reason.trim())}>
      <label>
        {label}
        <textarea value={reason} onChange={(e) => setReason(e.target.value)} required={required} rows={3} autoFocus />
      </label>
    </FormModal>
  );
}

// Date + time with AM/PM (owner, 2026-11-18). The browser's own datetime box follows the OS clock
// format, so this builds the 12-hour picker itself. It reports "YYYY-MM-DDTHH:mm" (local, 24-hour)
// or "" while incomplete; format.localInputToIso turns that into the exact moment the API stores.
// dateOnly: the box starts empty and the time may be left out; then it reports just "YYYY-MM-DD"
// and the page decides the time (expected checkout uses the check-in time, owner 2026-11-18).
export function DateTimeInput({ onChange, required, dateOnly }: {
  onChange: (value: string) => void; required?: boolean; dateOnly?: boolean;
}) {
  const today = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  const todayText = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;
  const [date, setDate] = useState(dateOnly ? "" : todayText);
  const [hour, setHour] = useState("");
  const [minute, setMinute] = useState("");
  const [ampm, setAmpm] = useState(today.getHours() >= 12 ? "PM" : "AM");

  // Typed hour 1-12 and minute 0-59 (owner, 2026-11-18). Blank minute means :00.
  const h = Number(hour);
  const m = minute === "" ? 0 : Number(minute);
  const hourOk = hour !== "" && Number.isInteger(h) && h >= 1 && h <= 12;
  const minuteOk = Number.isInteger(m) && m >= 0 && m <= 59;
  const timeLeftOut = hour === "" && minute === "";

  // A half-filled box must never be dropped silently: the browser blocks the form instead.
  const timeTyped = !timeLeftOut;
  const dateRequired = required || timeTyped;
  const hourRequired = required || minute !== "" || (!dateOnly && date !== "");

  useEffect(() => {
    if (dateOnly && date && timeLeftOut) {
      onChange(date);
      return;
    }
    if (!date || !hourOk || !minuteOk) {
      onChange("");
      return;
    }
    const h24 = (h % 12) + (ampm === "PM" ? 12 : 0); // 12 AM -> 00, 12 PM -> 12
    onChange(`${date}T${pad(h24)}:${pad(m)}`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date, hour, minute, ampm]);

  return (
    <div className="row">
      <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required={dateRequired} />
      <input type="number" inputMode="numeric" min={1} max={12} step={1} placeholder="hh" style={{ width: 70 }}
             value={hour} onChange={(e) => setHour(e.target.value)} required={hourRequired} aria-label="Hour (1-12)" />
      <span>:</span>
      <input type="number" inputMode="numeric" min={0} max={59} step={1} placeholder="mm" style={{ width: 70 }}
             value={minute} onChange={(e) => setMinute(e.target.value)} aria-label="Minute (0-59)" />
      <select value={ampm} onChange={(e) => setAmpm(e.target.value)} aria-label="AM or PM">
        <option value="AM">AM</option>
        <option value="PM">PM</option>
      </select>
    </div>
  );
}

// In-app confirmation (instead of the browser's own pop-up).
export function ConfirmModal({ title, message, confirmLabel, onConfirm, onClose, danger }: {
  title: string;
  message: ReactNode;
  confirmLabel: string;
  onConfirm: () => Promise<unknown> | void;
  onClose: () => void;
  danger?: boolean;
}) {
  return (
    <FormModal title={title} submitLabel={confirmLabel} danger={danger} onClose={onClose}
               onSubmit={async () => { await onConfirm(); }}>
      <div>{message}</div>
    </FormModal>
  );
}

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button type="button" className="secondary theme-toggle" onClick={toggle}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
      {theme === "dark" ? "☀ Light" : "☾ Dark"}
    </button>
  );
}

export function Loading() {
  return <div className="muted pad">Loading…</div>;
}

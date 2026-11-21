import { useState, type FormEvent } from "react";
import { api } from "../../api";
import { useSession } from "../../session";
import { ActionButton, ErrorBox, Loading } from "../../ui";

export function SettingsPage() {
  const { settings, reloadSettings } = useSession();
  const [timezone, setTimezone] = useState(settings?.timezone ?? "");
  const [currency, setCurrency] = useState(settings?.currency ?? "");
  const [backdateWindow, setBackdateWindow] = useState(String(settings?.max_backdate_minutes ?? 120));
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<unknown>(null);

  if (!settings) return <Loading />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await api.patch("/settings", { timezone, currency, max_backdate_minutes: Number(backdateWindow) });
      await reloadSettings();
      setSaved(true);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="stack card" onSubmit={submit} style={{ maxWidth: 480 }}>
      <h1>Settings</h1>
      <label>Timezone<input value={timezone} onChange={(e) => setTimezone(e.target.value)} required placeholder="Asia/Kolkata" /></label>
      <label>Currency<input value={currency} onChange={(e) => setCurrency(e.target.value)} required maxLength={3} placeholder="INR" /></label>
      <label>Backdating allowed without a manager (minutes)
        <input type="number" min={0} max={1440} value={backdateWindow} onChange={(e) => setBackdateWindow(e.target.value)} required />
      </label>
      <span className="muted">Billing: rolling 24 hours from check-in (the only mode in the beta).</span>
      <ErrorBox error={error} />
      {saved && <span className="notice">Saved.</span>}
      <div className="row end"><ActionButton type="submit" className="primary" disabled={busy}>Save</ActionButton></div>
    </form>
  );
}

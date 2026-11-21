import { useState, type FormEvent } from "react";
import { useSession } from "../session";
import { ActionButton, ErrorBox, ThemeToggle } from "../ui";

export function LoginPage() {
  const { login } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="center-screen">
      <form className="card stack login" onSubmit={submit}>
        <div className="row between">
          <h1>Front Desk</h1>
          <ThemeToggle />
        </div>
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus autoComplete="username" />
        </label>
        <label>
          Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
        </label>
        <ErrorBox error={error} />
        <ActionButton type="submit" className="primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</ActionButton>
      </form>
    </div>
  );
}

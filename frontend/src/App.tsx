import { useEffect, useRef, useState } from "react";
import { NavLink, Navigate, Outlet, Route, Routes, useLocation } from "react-router";
import { useOnline } from "./online";
import { AuditPage } from "./pages/AuditPage";
import { CheckInPage } from "./pages/CheckInPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { PendingPage } from "./pages/PendingPage";
import { PlansPage } from "./pages/setup/PlansPage";
import { RoomTypesPage } from "./pages/setup/RoomTypesPage";
import { RoomsPage } from "./pages/setup/RoomsPage";
import { SettingsPage } from "./pages/setup/SettingsPage";
import { UsersPage } from "./pages/setup/UsersPage";
import { StayPage } from "./pages/StayPage";
import { useSession } from "./session";
import { Loading, ThemeToggle } from "./ui";

export function App() {
  const { me, loading } = useSession();
  if (loading) return <Loading />;
  if (!me) return <LoginPage />;

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="check-in/:roomId" element={<CheckInPage />} />
        <Route path="stays/:stayId" element={<StayPage />} />
        <Route path="pending" element={<PendingPage />} />
        <Route path="setup/plans" element={<PlansPage />} />
        <Route path="setup/room-types" element={<RoomTypesPage />} />
        <Route path="setup/rooms" element={<RoomsPage />} />
        <Route path="setup/users" element={<UsersPage />} />
        <Route path="setup/settings" element={<SettingsPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

function Layout() {
  const { me, can, logout } = useSession();
  const online = useOnline();
  const { pathname } = useLocation();
  const isSetup = can("inventory.manage") || can("user.manage") || can("settings.manage");

  return (
    <div className="app">
      {!online && <div className="offline-banner">You're offline. Actions are disabled until the connection is back.</div>}
      <header className="topbar">
        <nav className="row">
          <NavLink to="/" end>Rooms</NavLink>
          {can("folio.view") && <NavLink to="/pending">Pending balances</NavLink>}
          {isSetup && <SetupMenu />}
          {can("audit.view") && <NavLink to="/audit">Audit</NavLink>}
        </nav>
        <div className="row">
          <ThemeToggle />
          <span className="muted">{me?.name} · {me?.role_code.replace("_", " ")}</span>
          <button className="secondary small" onClick={logout}>Log out</button>
        </div>
      </header>
      {/* The Rooms page uses the full width; every other page keeps the 1100px column. */}
      <main className={pathname === "/" ? "wide" : undefined}>
        <Outlet />
      </main>
    </div>
  );
}

// Closes on a click outside, on choosing an item, or on Escape (owner, 2026-11-18).
function SetupMenu() {
  const { can } = useSession();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const item = (to: string, label: string) => <NavLink to={to} onClick={() => setOpen(false)}>{label}</NavLink>;
  return (
    <div className="menu" ref={ref}>
      <button className="link menu-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>Setup ▾</button>
      {open && (
        <div className="menu-items">
          {can("inventory.manage") && item("/setup/plans", "Stay plans")}
          {can("inventory.manage") && item("/setup/room-types", "Room types & rates")}
          {can("inventory.manage") && item("/setup/rooms", "Rooms")}
          {can("user.manage") && item("/setup/users", "Users")}
          {can("settings.manage") && item("/setup/settings", "Settings")}
        </div>
      )}
    </div>
  );
}

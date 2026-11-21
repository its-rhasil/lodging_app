import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { api, errorText } from "../api";
import { balanceClass, dateTime, money } from "../format";
import { useSession } from "../session";
import type { Dashboard, RoomCard } from "../types";
import { ActionButton, ErrorBox, Loading } from "../ui";
import { useLoad } from "../useLoad";

type Filter = "all" | RoomCard["status"];

// Grouping (owner, 2026-11-18). The choice is remembered on this device.
type GroupBy = "none" | "type" | "floor";
const GROUP_OPTIONS: [GroupBy, string][] = [["none", "None"], ["type", "Room type"], ["floor", "Floor"]];
const GROUP_KEY = "roomsGroupBy";

function savedGroupBy(): GroupBy {
  try {
    const value = localStorage.getItem(GROUP_KEY);
    if (GROUP_OPTIONS.some(([key]) => key === value)) return value as GroupBy;
  } catch {
    // storage unavailable: no grouping
  }
  return "none";
}

// The floor comes from the room number (no floor field in the beta): the number without its
// last two digits, so 201 -> 2, 305 -> 3, 1205 -> 12, 005 -> 0 (ground). Numbers that don't
// follow this (letters such as "A-12", or fewer than 3 digits) have no floor.
function floorOf(roomNumber: string): number | null {
  const digits = roomNumber.trim();
  if (!/^\d{3,}$/.test(digits)) return null;
  return Number(digits.slice(0, -2));
}

type Group = { key: string; label: string; rooms: RoomCard[] };

function groupRooms(rooms: RoomCard[], by: GroupBy): Group[] {
  if (by === "none") return [{ key: "all", label: "", rooms }];

  const groups = new Map<string, Group>();
  const add = (key: string, label: string, room: RoomCard) => {
    const group = groups.get(key) ?? { key, label, rooms: [] };
    group.rooms.push(room);
    groups.set(key, group);
  };
  for (const room of rooms) {
    if (by === "type") {
      add(room.room_type_name, room.room_type_name, room);
    } else {
      const floor = floorOf(room.room_number);
      if (floor === null) add("none", "No floor", room);
      else add(String(floor), floor === 0 ? "Ground floor" : `Floor ${floor}`, room);
    }
  }

  const list = [...groups.values()];
  if (by === "type") list.sort((a, b) => a.label.localeCompare(b.label));
  if (by === "floor") {
    const rank = (g: Group) => (g.key === "none" ? Infinity : Number(g.key));  // "No floor" last
    list.sort((a, b) => rank(a) - rank(b));
  }
  return list;
}

export function DashboardPage() {
  const { data, error, reload } = useLoad(() => api.get<Dashboard>("/dashboard"));
  const [filter, setFilter] = useState<Filter>("all");
  const [groupBy, setGroupByState] = useState<GroupBy>(savedGroupBy);

  const setGroupBy = (value: GroupBy) => {
    setGroupByState(value);
    try {
      localStorage.setItem(GROUP_KEY, value);
    } catch {
      // not saved: still applies for this visit
    }
  };

  if (!data) return error ? <ErrorBox error={error} /> : <Loading />;
  const s = data.summary;
  const shown = filter === "all" ? data.rooms : data.rooms.filter((r) => r.status === filter);
  const groups = groupRooms(shown, groupBy);
  const pills: [Filter, string, number][] = [
    ["all", "total rooms", s.total_rooms],
    ["available", "available", s.available],
    ["occupied", "occupied", s.occupied],
    ["cleaning", "cleaning", s.cleaning],
    ["maintenance", "maintenance", s.maintenance],
  ];

  return (
    <div className="stack">
      <div className="row between">
        <h1>Rooms</h1>
        <div className="row">
          <span className="muted">Group by:</span>
          {GROUP_OPTIONS.map(([key, label]) => (
            <button key={key} className={`pill ${groupBy === key ? "pill-active" : ""}`}
                    aria-pressed={groupBy === key} onClick={() => setGroupBy(key)}>
              {label}
            </button>
          ))}
          <button className="secondary small" onClick={reload}>Refresh</button>
        </div>
      </div>
      <div className="summary">
        {pills.map(([key, label, count]) => (
          <button key={key} className={`pill ${filter === key ? "pill-active" : ""} ${key}`}
                  onClick={() => setFilter(key)} aria-pressed={filter === key}>
            {count} {label}
          </button>
        ))}
        {s.pending_balances_count > 0 && (
          <Link className="pill owes" to="/pending">
            {s.pending_balances_count} pending · {money(s.pending_balances_total)}
          </Link>
        )}
      </div>
      <ErrorBox error={error} />
      {groups.map((group) => (
        <section key={`${groupBy}:${group.key}`} className="room-group">
          {groupBy !== "none" && <h2 className="group-head">{group.label}</h2>}
          <div className="rooms">
            {group.rooms.map((room) => <RoomTile key={room.room_id} room={room} onChanged={reload} />)}
          </div>
        </section>
      ))}
      {data.rooms.length === 0 && <p className="muted">No rooms yet. Add them under Setup → Rooms.</p>}
      {data.rooms.length > 0 && shown.length === 0 && <p className="muted">No rooms are {filter}.</p>}
    </div>
  );
}

// Room card (owner, 2026-11-18):
//   top:      room number (left), status badge (right)
//   below:    room type, full width, wraps instead of being cut off
//   occupied: guest name + plan in the centre, check-in time (left) and balance (right) at the bottom
//   otherwise: one full-width main button (Check in on an available room, Ready on a cleaning or
//             blocked one), and below it one row of smaller, equal-width tinted buttons
//             (Cleaning / Block, whichever the room isn't already)
// An occupied card opens its stay when clicked. All cards are the same size.
function RoomTile({ room, onChanged }: { room: RoomCard; onChanged: () => void }) {
  const { can } = useSession();
  const navigate = useNavigate();
  const [error, setError] = useState<unknown>(null);

  const setStatus = async (status: string) => {
    setError(null);
    try {
      await api.patch(`/rooms/${room.room_id}/status`, { operational_status: status });
      onChanged();
    } catch (err) {
      setError(err);
    }
  };

  const stay = room.stay;
  const canSetStatus = can("room.status.update");
  const otherStatuses = (["cleaning", "maintenance"] as const).filter((s) => s !== room.status);
  const label = (status: string) => (status === "cleaning" ? "Cleaning" : "Block");
  const primaryAction =
    room.status === "available"
      ? (can("stay.check_in") ? { text: "Check in", run: () => navigate(`/check-in/${room.room_id}`) } : null)
      : (canSetStatus ? { text: "Ready", run: () => setStatus("available") } : null);

  return (
    <div className={`room ${stay ? "clickable" : ""}`}
         onClick={stay ? () => navigate(`/stays/${stay.stay_id}`) : undefined}
         role={stay ? "link" : undefined}
         title={stay ? `Open ${stay.guest_name}'s stay` : undefined}>
      <div className="room-top">
        <span className="number">{room.room_number}</span>
        <span className={`badge ${room.status}`}>{room.status}</span>
      </div>
      {/* Not truncated: it wraps onto a second line if it is long. */}
      <span className="room-type muted">{room.room_type_name}</span>

      <div className="room-body">
        {stay ? (
          <>
            <div className="room-guest">
              <strong className="guest" title={stay.guest_name}>{stay.guest_name}</strong>
              <span className="muted ellipsis" title={stay.stay_plan_name}>{stay.stay_plan_name}</span>
            </div>
            <div className="room-bottom">
              <span className="muted ellipsis" title={`Checked in ${dateTime(stay.actual_check_in_at)}`}>
                {dateTime(stay.actual_check_in_at)}
              </span>
              <span className={balanceClass(stay.balance)} title="Balance">{money(stay.balance)}</span>
            </div>
          </>
        ) : (
          <div className="room-actions">
            {primaryAction && (
              <ActionButton className="primary room-primary" onClick={primaryAction.run}>
                {primaryAction.text}
              </ActionButton>
            )}
            {error ? (
              <span className="card-error" title={errorText(error)}>{errorText(error)}</span>
            ) : (
              canSetStatus && (
                <div className="secondary-pair">
                  {otherStatuses.map((status) => (
                    <ActionButton key={status} onClick={() => setStatus(status)}
                                  className={`secondary-btn ${status === "cleaning" ? "btn-clean" : "btn-block"}`}>
                      {label(status)}
                    </ActionButton>
                  ))}
                </div>
              )
            )}
          </div>
        )}
      </div>
    </div>
  );
}

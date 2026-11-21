import { useState } from "react";
import { api } from "../../api";
import type { Room, RoomType } from "../../types";
import { ActionButton, ErrorBox, FormModal, Loading } from "../../ui";
import { useLoad } from "../../useLoad";

export function RoomsPage() {
  const { data: rooms, error, reload } = useLoad(() => api.get<Room[]>("/rooms"));
  const { data: types } = useLoad(() => api.get<RoomType[]>("/room-types"));
  const [editing, setEditing] = useState<Room | "new" | null>(null);

  if (!rooms || !types) return error ? <ErrorBox error={error} /> : <Loading />;
  return (
    <div className="stack">
      <div className="row between">
        <h1>Rooms</h1>
        <ActionButton className="primary" onClick={() => setEditing("new")} disabled={types.length === 0}>Add room</ActionButton>
      </div>
      {types.length === 0 && <p className="notice">Add a room type first.</p>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Number</th><th>Type</th><th>Status</th><th>Active</th><th /></tr></thead>
          <tbody>
            {rooms.map((r) => (
              <tr key={r.id}>
                <td>{r.room_number}</td>
                <td>{r.room_type_name}</td>
                <td>{r.status}</td>
                <td>{r.is_active ? "Yes" : "No"}</td>
                <td className="num"><button className="link" onClick={() => setEditing(r)}>Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editing && <RoomDialog room={editing === "new" ? null : editing} types={types}
                              onClose={() => { setEditing(null); reload(); }} />}
    </div>
  );
}

function RoomDialog({ room, types, onClose }: { room: Room | null; types: RoomType[]; onClose: () => void }) {
  const [number, setNumber] = useState(room?.room_number ?? "");
  const [typeId, setTypeId] = useState(String(room?.room_type_id ?? types.find((t) => t.is_active)?.id ?? ""));
  const [active, setActive] = useState(room?.is_active ?? true);
  return (
    <FormModal title={room ? `Edit room ${room.room_number}` : "New room"} submitLabel="Save" onClose={onClose}
               onSubmit={() => room
                 ? api.patch(`/rooms/${room.id}`, { room_number: number, room_type_id: Number(typeId), is_active: active })
                 : api.post("/rooms", { room_number: number, room_type_id: Number(typeId) })}>
      <label>Room number<input value={number} onChange={(e) => setNumber(e.target.value)} required autoFocus maxLength={20} /></label>
      <label>Type
        <select value={typeId} onChange={(e) => setTypeId(e.target.value)} required>
          {types.filter((t) => t.is_active || t.id === room?.room_type_id).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
      </label>
      {room && <label className="check"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />Active (shown on the room grid)</label>}
    </FormModal>
  );
}

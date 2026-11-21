import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router";
import { api } from "../api";
import { dateTime, localInputToIso, money } from "../format";
import { useSession } from "../session";
import type { Guest, Offer, Room, RoomType, Stay } from "../types";
import { ActionButton, ConfirmModal, DateTimeInput, ErrorBox, Loading } from "../ui";
import { useLoad } from "../useLoad";

// Expected checkout as the API wants it. A date with no time gets the check-in time of day
// (owner, 2026-11-18): the backdated arrival time, else now.
function expectedCheckoutIso(expected: string, arrivedLocal: string): string | null {
  if (!expected) return null;
  if (expected.includes("T")) return localInputToIso(expected);
  const moment = arrivedLocal ? new Date(arrivedLocal) : new Date();
  const [year, month, day] = expected.split("-").map(Number);
  moment.setFullYear(year, month - 1, day);
  return moment.toISOString();
}

export function CheckInPage() {
  const { roomId } = useParams();
  const navigate = useNavigate();
  const { can, settings } = useSession();

  const { data: room, error: roomError } = useLoad(() => api.get<Room>(`/rooms/${roomId}`), [roomId]);
  const { data: types } = useLoad(() => api.get<RoomType[]>("/room-types"));
  const capacity = types?.find((t) => t.id === room?.room_type_id)?.capacity ?? 1;

  const [occupancy, setOccupancy] = useState(1);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [planId, setPlanId] = useState<number | null>(null);

  const [phone, setPhone] = useState("");
  const [matches, setMatches] = useState<Guest[] | null>(null);
  const [guestId, setGuestId] = useState<number | null>(null);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [address, setAddress] = useState("");

  const [price, setPrice] = useState("");
  const [rateReason, setRateReason] = useState("");
  const [backdate, setBackdate] = useState(false);
  const [checkInLocal, setCheckInLocal] = useState("");
  const [backdateReason, setBackdateReason] = useState("");
  const [expectedLocal, setExpectedLocal] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [confirmPrice, setConfirmPrice] = useState(false);

  // Plan picker: only plans this room offers at this occupancy (DL-R17).
  useEffect(() => {
    if (!roomId) return;
    api.get<Offer[]>(`/rooms/${roomId}/offers`, { occupancy }).then((list) => {
      setOffers(list);
      setPlanId((current) => (list.some((o) => o.stay_plan_id === current) ? current : list[0]?.stay_plan_id ?? null));
    }).catch(setError);
  }, [roomId, occupancy]);

  const offer = offers.find((o) => o.stay_plan_id === planId) ?? null;
  const listed = offer ? Number(offer.listed_price) : 0;
  const agreed = price === "" ? listed : Number(price);
  const discount = listed > 0 && agreed < listed ? ((listed - agreed) / listed) * 100 : 0;

  const backdateMinutes = useMemo(() => {
    if (!backdate || !checkInLocal) return 0;
    return (Date.now() - new Date(checkInLocal).getTime()) / 60000;
  }, [backdate, checkInLocal]);
  const beyondWindow = backdateMinutes > (settings?.max_backdate_minutes ?? 120);

  // Returning guest: fill their saved details and show them (owner, 2026-11-18).
  // "New guest": clear the fields for typing.
  const pickGuest = (guest: Guest | null) => {
    setGuestId(guest?.id ?? null);
    setFullName(guest?.full_name ?? "");
    setEmail(guest?.email ?? "");
    setAddress(guest?.address ?? "");
  };

  const lookUp = async () => {
    setError(null);
    try {
      const found = await api.get<Guest[]>("/guests", { phone });
      setMatches(found);
      pickGuest(null);
    } catch (err) {
      setError(err);
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!planId) return;
    // A very low price is usually a typo (e.g. 8 for 800): ask before saving.
    if (discount > 50) {
      setConfirmPrice(true);
      return;
    }
    checkIn();
  };

  const checkIn = async () => {
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        room_id: Number(roomId), stay_plan_id: planId, occupancy,
        agreed_price: price === "" ? null : price, rate_reason: rateReason || null,
        check_in_at: backdate && checkInLocal ? localInputToIso(checkInLocal) : null,
        backdate_reason: backdateReason || null,
        expected_checkout_at: expectedCheckoutIso(expectedLocal, backdate ? checkInLocal : ""),
      };
      if (guestId) body.guest_id = guestId;
      else body.guest = { full_name: fullName, phone, email: email || null, address: address || null };
      const stay = await api.post<Stay>("/stays", body);
      navigate(`/stays/${stay.id}`, { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  if (!room) return roomError ? <ErrorBox error={roomError} /> : <Loading />;

  return (
    <form className="stack" onSubmit={submit}>
      <h1>Check in · Room {room.room_number}</h1>
      <p className="muted">{room.room_type_name} · up to {capacity} guest(s)</p>

      <section className="card stack">
        <h2>Guests and plan</h2>
        <label style={{ maxWidth: 160 }}>
          Number of guests
          <select value={occupancy} onChange={(e) => setOccupancy(Number(e.target.value))}>
            {Array.from({ length: capacity }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        {offers.length === 0 ? (
          <p className="error">This room has no price for {occupancy} guest(s).</p>
        ) : (
          <div className="offers">
            {offers.map((o) => (
              <button type="button" key={o.stay_plan_id}
                      className={`offer ${o.stay_plan_id === planId ? "selected" : ""}`}
                      onClick={() => setPlanId(o.stay_plan_id)}>
                <strong>{o.name}</strong>
                <div>{money(o.listed_price)} / {o.period_hours === 24 ? "day" : `${o.period_hours}h`}</div>
                <div className="muted">grace {o.grace_minutes} min</div>
              </button>
            ))}
          </div>
        )}
      </section>

      <section className="card stack">
        <h2>Guest</h2>
        <div className="row">
          <label style={{ flex: 1, minWidth: 200 }}>
            Phone
            <input value={phone} onChange={(e) => { setPhone(e.target.value); setMatches(null); pickGuest(null); }}
                   required inputMode="tel" placeholder="98765 43210" />
          </label>
          <button type="button" className="secondary" onClick={lookUp} disabled={phone.trim().length < 7}
                  style={{ alignSelf: "flex-end" }}>Find guest</button>
        </div>
        {matches && matches.length > 0 && (
          <div className="stack">
            <span className="muted">Returning guest? Pick them, or fill in a new guest below.</span>
            {matches.map((g) => (
              <label key={g.id} className="check">
                <input type="radio" name="guest" checked={guestId === g.id} onChange={() => pickGuest(g)} />
                {g.full_name} <span className="muted">· first seen {dateTime(g.created_at)}</span>
              </label>
            ))}
            <label className="check">
              <input type="radio" name="guest" checked={guestId === null} onChange={() => pickGuest(null)} />
              New guest
            </label>
          </div>
        )}
        {matches && matches.length === 0 && <span className="muted">No guest with this phone yet.</span>}
        <div className="grid2">
          <label>Full name
            <input value={fullName} onChange={(e) => setFullName(e.target.value)} required readOnly={guestId !== null} />
          </label>
          <label>Email (optional)
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} readOnly={guestId !== null} />
          </label>
          <label>Address (optional)
            <input value={address} onChange={(e) => setAddress(e.target.value)} readOnly={guestId !== null} />
          </label>
        </div>
      </section>

      <section className="card stack">
        <h2>Price</h2>
        <div className="grid2">
          <label>
            Price per {offer?.period_hours === 24 ? "day" : "period"} (listed {money(listed)})
            <input type="number" min="0.01" step="0.01" max={listed || undefined} value={price}
                   onChange={(e) => setPrice(e.target.value)} placeholder={offer?.listed_price ?? ""}
                   disabled={!can("stay.override_rate")} />
          </label>
          {discount > 0 && (
            <label>Reason for discount (optional)
              <input value={rateReason} onChange={(e) => setRateReason(e.target.value)} placeholder="e.g. regular guest" />
            </label>
          )}
        </div>
        {discount > 0 && <span className="notice">Discount {discount.toFixed(2)}%</span>}
      </section>

      <section className="card stack">
        <h2>Times</h2>
        <label className="check">
          <input type="checkbox" checked={backdate} onChange={(e) => setBackdate(e.target.checked)} />
          The guest arrived earlier (backdate the check-in)
        </label>
        {backdate && (
          <div className="grid2">
            <label>Arrived at<DateTimeInput onChange={setCheckInLocal} required /></label>
            {beyondWindow && (
              <label>Reason (needed beyond {settings?.max_backdate_minutes} min)
                <input value={backdateReason} onChange={(e) => setBackdateReason(e.target.value)} required />
              </label>
            )}
          </div>
        )}
        <label>
          Expected checkout (optional; no time = same time as check-in)
          <DateTimeInput onChange={setExpectedLocal} dateOnly />
        </label>
      </section>

      <ErrorBox error={error} />
      {confirmPrice && (
        <ConfirmModal title="Check the price" confirmLabel={`Yes, ${money(agreed)}`} danger
                      message={`${money(agreed)} is ${discount.toFixed(0)}% below the listed ${money(listed)}. Is that right?`}
                      onConfirm={checkIn} onClose={() => setConfirmPrice(false)} />
      )}
      <div className="row end">
        <button type="button" className="secondary" onClick={() => navigate(-1)}>Cancel</button>
        <ActionButton type="submit" className="primary" disabled={busy || !planId}>
          {busy ? "Checking in…" : `Check in · ${money(agreed)}`}
        </ActionButton>
      </div>
    </form>
  );
}

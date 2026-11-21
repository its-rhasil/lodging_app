// Display helpers. Times are shown in the tenant's timezone (tenant settings), money in its currency.

let timezone = "Asia/Kolkata";
let currency = "INR";

export function setLocaleSettings(tz: string, cur: string) {
  timezone = tz;
  currency = cur;
}

export function money(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency }).format(Number(value));
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: timezone, day: "2-digit", month: "short", hour: "numeric", minute: "2-digit", hour12: true,
  }).format(new Date(value));
}

// For <input type="datetime-local">: the value is local wall-clock time without an offset.
// The API needs an aware datetime, so convert with the browser's offset (the desk's own clock).
export function localInputToIso(value: string): string {
  return new Date(value).toISOString();
}

export function balanceClass(value: string): string {
  const n = Number(value);
  if (n > 0) return "owes";
  if (n < 0) return "credit";
  return "settled";
}

export const TXN_LABELS: Record<string, string> = {
  room_charge: "Room",
  charge: "Charge",
  payment: "Payment",
  refund: "Refund",
  waiver: "Waiver",
  reversal: "Reversal",
};

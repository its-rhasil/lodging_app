// Shapes returned by the API (see app/schemas). Money and prices arrive as strings ("1000.00").

export type Me = {
  id: number;
  tenant_id: number;
  name: string;
  email: string;
  role_code: string;
  permissions: string[];
};

export type Settings = {
  timezone: string;
  currency: string;
  billing_mode: string;
  max_backdate_minutes: number;
  updated_at: string;
};

export type StayPlan = {
  id: number;
  name: string;
  period_hours: number;
  grace_minutes: number;
  is_daily: boolean;
  is_active: boolean;
  sort_order: number;
};

export type Rate = { stay_plan_id: number; occupancy: number; price: string };

export type RoomType = {
  id: number;
  name: string;
  description: string | null;
  capacity: number;
  is_active: boolean;
  rates: Rate[];
};

export type Room = {
  id: number;
  room_number: string;
  room_type_id: number;
  room_type_name: string;
  operational_status: string;
  status: string;
  active_stay_id: number | null;
  is_active: boolean;
};

export type StayCard = {
  stay_id: number;
  guest_name: string;
  guest_phone: string;
  stay_plan_name: string;
  actual_check_in_at: string;
  expected_checkout_at: string | null;
  agreed_price: string;
  balance: string;
  next_charge_at: string;
};

export type RoomCard = {
  room_id: number;
  room_number: string;
  room_type_name: string;
  status: "available" | "cleaning" | "maintenance" | "occupied";
  stay: StayCard | null;
};

export type Dashboard = {
  summary: {
    total_rooms: number;
    available: number;
    occupied: number;
    cleaning: number;
    maintenance: number;
    pending_balances_count: number;
    pending_balances_total: string;
  };
  rooms: RoomCard[];
};

export type Offer = {
  stay_plan_id: number;
  name: string;
  period_hours: number;
  grace_minutes: number;
  is_daily: boolean;
  listed_price: string;
};

export type Guest = {
  id: number;
  full_name: string;
  phone: string;
  email: string | null;
  address: string | null;
  created_at: string;
};

export type Transaction = {
  id: number;
  txn_type: "room_charge" | "charge" | "payment" | "refund" | "waiver" | "reversal";
  direction: "debit" | "credit";
  amount: string;
  description: string | null;
  period_no: number | null;
  period_start_at: string | null;
  payment_method: string | null;
  reference: string | null;
  related_txn_id: number | null;
  reason: string | null;
  created_by_user_id: number | null;
  created_at: string;
  is_reversed: boolean;
  waivable_amount: string | null;
};

export type Folio = {
  id: number;
  stay_id: number;
  status: "open" | "closed";
  balance: string;
  transactions: Transaction[];
};

export type Stay = {
  id: number;
  status: "active" | "checked_out" | "cancelled";
  room_id: number;
  room_number: string;
  guest: Guest;
  stay_plan_id: number;
  stay_plan_name: string;
  occupancy: number;
  period_hours: number;
  grace_minutes: number;
  actual_check_in_at: string;
  expected_checkout_at: string | null;
  actual_checkout_at: string | null;
  listed_price: string;
  agreed_price: string;
  discount_percent: string;
  folio: { id: number; status: string; balance: string };
};

export type StayDetail = Omit<Stay, "folio"> & { folio: Folio };

export type StaySummary = {
  id: number;
  status: string;
  room_id: number;
  room_number: string;
  guest_id: number;
  guest_name: string;
  guest_phone: string;
  stay_plan_name: string;
  occupancy: number;
  actual_check_in_at: string;
  expected_checkout_at: string | null;
  actual_checkout_at: string | null;
  agreed_price: string;
  folio_id: number;
  folio_status: string;
  balance: string;
  forced_checkout_reason: string | null;
};

export type User = {
  id: number;
  email: string;
  name: string;
  role_code: string;
  is_active: boolean;
  created_at: string;
};

export type Override = { permission_code: string; effect: "grant" | "deny"; reason: string | null };

export type UserDetail = User & { overrides: Override[]; permissions: string[] };

export type PermissionInfo = { code: string; description: string; roles: string[] };

export type AuditEvent = {
  id: number;
  created_at: string;
  actor_type: string;
  actor_user_id: number | null;
  actor_name: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  summary: string | null;
  changes: Record<string, unknown> | null;
  reason: string | null;
};

export const PAYMENT_METHODS = ["cash", "upi", "card", "bank_transfer", "other"] as const;

export interface CheckInPreview {
  room_id: number;
  room_type_name: string;
  occupancy: number;
  capacity: number;
  suggested_price: string | null;
}

export interface CheckInRequest {
  room_id: number;
  guest_full_name: string;
  guest_phone: string;
  guest_email?: string | null;
  guest_address?: string | null;
  occupancy: number;
  stay_hours: number;
  agreed_price: string;
  actual_check_in_at?: string | null;
}
export interface StayOut {
  id: number;
  room_id: number;
  guest_id: number;
  status: string;
  actual_check_in_at: string;
  agreed_price: string;
}
export interface Billing {
  occupancy: number;
  nightly_rate: string;
  nights: number;
  total: string;
  paid: string;
  balance: string;
  status: string;
}

export interface CheckoutResponse {
  stay: StayOut;
  billing: Billing;
}

export interface ChangeRoomPreview {
  mode: "updated" | "split";
  suggested_price: string | null;
  old_balance_due_if_split: string | null;
}

export interface ConfirmRoomChangeRequest {
  new_room_id: number;
  final_price: string;
}

export interface ChangeRoomResult {
  mode: "updated" | "split";
  stay?: StayOut;
  old_stay?: StayOut;
  new_stay?: StayOut;
}

export interface ExtendStayRequest {
  new_expected_checkout_at: string;
}
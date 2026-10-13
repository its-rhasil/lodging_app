export interface Guest {
  full_name: string;
  phone: string;
  email: string | null;
  address: string | null;
}

export interface BillingSummary {
  occupancy: number;
  nightly_rate: string;
  nights: number;
  total: string;
  paid: string;
  balance: string;
  status: string;
}

export interface RoomDetail {
  room_id: number;
  stay_id: number | null;
  room_number: string;
  room_type_name: string;
  status: string;
  guest: Guest | null;
  actual_check_in_at: string | null;
  expected_checkout_at: string | null;
  billing: BillingSummary | null;
}

export interface CreateRoomRequest {
  room_type_id: number;
  room_number: number;
}
export interface RoomListItem {
  id: number;
  room_number: string;
  room_type_id: number;
  room_type_name: string;
  operational_status: string;
}

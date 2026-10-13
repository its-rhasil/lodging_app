export interface DashboardSummary {
  total_rooms: number;
  available: number;
  occupied: number;
  cleaning: number;
  maintenance: number;
  reserved: number;
}

export interface RoomCard {
  room_id: number;
  room_number: string;
  room_type_name: string;
  status: string;
  guest_name: string | null;
  nightly_rate: string | null;
  min_price: string | null;
  max_price: string | null;
}

export interface DashboardResponse {
  summary: DashboardSummary;
  rooms: RoomCard[];
}
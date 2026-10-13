import { apiFetch } from "@/lib/api";

export interface RoomTypeOption {
  id: number;
  name: string;
  capacity: number;
}

export async function getRoomTypeOptions(): Promise<RoomTypeOption[]> {
  return apiFetch<RoomTypeOption[]>("/room-type/room_type");
}
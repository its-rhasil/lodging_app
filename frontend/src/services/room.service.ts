import { apiFetch } from "@/lib/api";
import { RoomDetail, CreateRoomRequest, RoomListItem} from "@/types/room";

export async function getRoomDetail(
  roomId: number
): Promise<RoomDetail> {
  return apiFetch<RoomDetail>(`/rooms/${roomId}`);
}

export async function updateRoomStatus(
  roomId: number,
  operationalStatus: string
): Promise<void> {
  await apiFetch(`/rooms/${roomId}/status`, {
    method: "PATCH",
    body: JSON.stringify({
      operational_status: operationalStatus,
    }),
  });
}
export async function createRoom(
  data: CreateRoomRequest
) {
  return apiFetch("/rooms/", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getRooms(): Promise<RoomListItem[]> {
  return apiFetch<RoomListItem[]>("/rooms/");
}
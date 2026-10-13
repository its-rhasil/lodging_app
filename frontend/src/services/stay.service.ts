import { apiFetch } from "@/lib/api";
import {
  CheckInPreview,
  CheckInRequest,
  CheckoutResponse,
  ChangeRoomPreview,
  ConfirmRoomChangeRequest,
  ChangeRoomResult,
} from "@/types/stay";

export async function previewCheckIn(
  roomId: number,
  occupancy: number
): Promise<CheckInPreview> {
  return apiFetch<CheckInPreview>(
    `/stay/check-in/preview?room_id=${roomId}&occupancy=${occupancy}`
  );
}

export async function checkIn(
  data: CheckInRequest
): Promise<void> {
  await apiFetch("/stay/", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function checkOut(
  stayId: number,
  force = false
): Promise<CheckoutResponse> {
  return apiFetch<CheckoutResponse>(
    `/stay/${stayId}/checkout?force=${force}`,
    {
      method: "PATCH",
    }
  );
}

export async function previewRoomChange(
  stayId: number,
  newRoomId: number
): Promise<ChangeRoomPreview> {
  return apiFetch<ChangeRoomPreview>(
    `/stay/${stayId}/change-room/preview?new_room_id=${newRoomId}`
  );
}

export async function confirmRoomChange(
  stayId: number,
  data: ConfirmRoomChangeRequest,
  force = false
): Promise<ChangeRoomResult> {
  return apiFetch<ChangeRoomResult>(
    `/stay/${stayId}/change-room/confirm?force=${force}`,
    {
      method: "PATCH",
      body: JSON.stringify(data),
    }
  );
}
import { apiFetch } from "@/lib/api";
import { BillingSummary } from "@/types/room";

export interface PaymentCreate {
  amount: string;
  method: string;
}

export async function recordPayment(
  stayId: number,
  data: PaymentCreate
): Promise<BillingSummary> {
  return apiFetch<BillingSummary>(`/stays/${stayId}/payments`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}
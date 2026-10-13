import { apiFetch } from "@/lib/api";
import { User } from "@/types/auth";

export interface LoginRequest {
  email: string;
  password: string;
}

export async function login(data: LoginRequest): Promise<void> {
  await apiFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getCurrentUser(): Promise<User> {
  return apiFetch<User>("/auth/me");
}

export async function logout(): Promise<void> {
  await apiFetch("/auth/logout", {
    method: "POST",
  });
}
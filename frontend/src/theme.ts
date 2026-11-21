import { useEffect, useState } from "react";

// Light / dark theme (owner, 2026-11-18). The choice is remembered on this device; the first
// visit follows the device's own setting. index.html applies it before React loads (no flash).
export type Theme = "light" | "dark";
const KEY = "theme";

function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    // storage unavailable (private mode): fall through to the device setting
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#0e1116" : "#f4efe6");
    try {
      localStorage.setItem(KEY, theme);
    } catch {
      // not saved: still works for this visit
    }
  }, [theme]);

  return { theme, toggle: () => setTheme(theme === "dark" ? "light" : "dark") };
}

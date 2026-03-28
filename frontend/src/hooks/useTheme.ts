/**
 * Dark mode hook — detekce, přepínání, persistence a synchronizace mezi doménami.
 */
import { useState, useEffect } from "react";

type Theme = "light" | "dark";
const STORAGE_KEY = "upravapp_theme";
const ATTR = "data-theme";

function getSystemTheme(): Theme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme: Theme) {
  document.documentElement.setAttribute(ATTR, theme);
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    const stored = localStorage.getItem(STORAGE_KEY) as Theme | null;
    return stored ?? getSystemTheme();
  });

  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem(STORAGE_KEY, theme);
    const channel = new BroadcastChannel("theme-sync");
    channel.postMessage({ theme });
    return () => channel.close();
  }, [theme]);

  useEffect(() => {
    const channel = new BroadcastChannel("theme-sync");
    channel.onmessage = (e) => {
      if (e.data?.theme && e.data.theme !== theme) setTheme(e.data.theme);
    };
    return () => channel.close();
  }, [theme]);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent) => setTheme(e.matches ? "dark" : "light");
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  const toggle = () => setTheme((t) => (t === "light" ? "dark" : "light"));
  return { theme, toggle, setTheme };
}

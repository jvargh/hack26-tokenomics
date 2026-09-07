/**
 * Light/dark theme toggle.
 *
 * The palette already supports both modes via `data-theme` on <html>
 * (see styles/tokens.css). Dark stays the product default so the surface never
 * changes with the operating system setting; this control lets a person choose
 * the other one and remembers it.
 */

import { useCallback, useEffect, useState } from "react";

export type Theme = "dark" | "light";

const STORAGE_KEY = "tokenos.theme";

function readStoredTheme(): Theme {
  try {
    return localStorage.getItem(STORAGE_KEY) === "light" ? "light" : "dark";
  } catch {
    // Private browsing can refuse storage; the default theme still applies.
    return "dark";
  }
}

function applyTheme(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(readStoredTheme);

  useEffect(() => {
    applyTheme(theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* Remembering the choice is optional. */
    }
  }, [theme]);

  const toggle = useCallback(() => setTheme((current) => (current === "dark" ? "light" : "dark")), []);
  const next = theme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggle}
      aria-pressed={theme === "light"}
      aria-label={`Switch to ${next} mode`}
      title={`Switch to ${next} mode`}
    >
      {/* One bulb: filled when the lights are on, outlined when they are off. */}
      <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
        <path
          d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.5.4.8 1 .8 1.6v.5h5.4v-.5c0-.6.3-1.2.8-1.6A6 6 0 0 0 12 3Z"
          fill={theme === "light" ? "currentColor" : "none"}
          fillOpacity={theme === "light" ? 0.22 : 0}
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  );
}

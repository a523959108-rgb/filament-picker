export type ThemeMode = "auto" | "light" | "dark";
export type ThemeName = "light" | "dark";

export const THEME_STORAGE_KEY = "fp-theme";
const LIGHT_START = 7 * 60;
const LIGHT_END = 19 * 60;

export function resolveTheme(mode: ThemeMode, now: Date): ThemeName {
  if (mode === "light" || mode === "dark") return mode;
  const minutes = now.getHours() * 60 + now.getMinutes();
  return minutes >= LIGHT_START && minutes < LIGHT_END ? "light" : "dark";
}

export function nextThemeBoundary(now: Date): Date {
  const year = now.getFullYear();
  const month = now.getMonth();
  const day = now.getDate();
  const morning = new Date(year, month, day, 7, 0, 0, 0);
  const evening = new Date(year, month, day, 19, 0, 0, 0);
  if (now < morning) return morning;
  if (now < evening) return evening;
  return new Date(year, month, day + 1, 7, 0, 0, 0);
}

export function readThemeMode(): ThemeMode {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "light" || stored === "dark" || stored === "auto") return stored;
  } catch {
    /* storage unavailable */
  }
  return "auto";
}

export function writeThemeMode(mode: ThemeMode): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, mode);
  } catch {
    /* storage unavailable */
  }
}

export function applyTheme(mode: ThemeMode, now: Date = new Date()): ThemeName {
  const theme = resolveTheme(mode, now);
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.themeMode = mode;
  return theme;
}

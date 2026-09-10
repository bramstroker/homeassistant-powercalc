export const THEME_STORAGE_KEY = "powercalc-measure-theme";
export const THEME_CHANGE_EVENT = "measure-theme-change";

export type ThemePreference = "system" | "light" | "dark";

const THEMES: readonly ThemePreference[] = ["system", "light", "dark"];

export function readThemePreference(storage: Pick<Storage, "getItem"> = localStorage): ThemePreference {
  try {
    const value = storage.getItem(THEME_STORAGE_KEY);
    return isThemePreference(value) ? value : "system";
  } catch {
    return "system";
  }
}

export function saveThemePreference(
  preference: ThemePreference,
  storage: Pick<Storage, "setItem"> = localStorage,
): void {
  try {
    storage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // A blocked storage area should not prevent an in-memory theme change.
  }
}

export function nextThemePreference(preference: ThemePreference): ThemePreference {
  return THEMES[(THEMES.indexOf(preference) + 1) % THEMES.length]!;
}

export function resolvedTheme(preference: ThemePreference, systemPrefersDark: boolean): "light" | "dark" {
  return preference === "system" ? (systemPrefersDark ? "dark" : "light") : preference;
}

export function applyDocumentTheme(preference: ThemePreference, systemPrefersDark: boolean): void {
  document.documentElement.dataset.theme = preference;
  const themeColor = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (themeColor) {
    themeColor.content = resolvedTheme(preference, systemPrefersDark) === "dark" ? "#0d1119" : "#f4f7fb";
  }
}

function isThemePreference(value: string | null): value is ThemePreference {
  return value === "system" || value === "light" || value === "dark";
}

import {
  THEME_STORAGE_KEY,
  applyDocumentTheme,
  nextThemePreference,
  readThemePreference,
  resolvedTheme,
  saveThemePreference,
} from "./theme";

afterEach(() => {
  document.documentElement.removeAttribute("data-theme");
  document.querySelector('meta[data-theme-test]')?.remove();
});

describe("theme preference", () => {
  it("reads only supported stored preferences", () => {
    expect(readThemePreference({ getItem: () => "light" })).toBe("light");
    expect(readThemePreference({ getItem: () => "sepia" })).toBe("system");
    expect(readThemePreference({ getItem: () => { throw new Error("blocked"); } })).toBe("system");
  });

  it("cycles through system, light and dark", () => {
    expect(nextThemePreference("system")).toBe("light");
    expect(nextThemePreference("light")).toBe("dark");
    expect(nextThemePreference("dark")).toBe("system");
  });

  it("resolves system preferences and applies document chrome colors", () => {
    const themeColor = document.createElement("meta");
    themeColor.name = "theme-color";
    themeColor.content = "#000000";
    themeColor.dataset.themeTest = "";
    document.head.append(themeColor);
    applyDocumentTheme("system", false);
    expect(document.documentElement.dataset.theme).toBe("system");
    expect(themeColor.content).toBe("#f4f7fb");
    expect(resolvedTheme("system", true)).toBe("dark");
    applyDocumentTheme("dark", false);
    expect(themeColor.content).toBe("#0d1119");
  });

  it("persists the selected preference without requiring writable storage", () => {
    const setItem = vi.fn();
    saveThemePreference("dark", { setItem });
    expect(setItem).toHaveBeenCalledWith(THEME_STORAGE_KEY, "dark");
    expect(() => saveThemePreference("light", { setItem: () => { throw new Error("blocked"); } })).not.toThrow();
  });
});

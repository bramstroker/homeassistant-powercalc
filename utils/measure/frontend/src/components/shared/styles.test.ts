import { sharedStyles, themeStyles } from "../../styles";

it("inherits the selected native control color scheme through shadow roots", () => {
  expect(sharedStyles.cssText).toContain("color-scheme: var(--measure-color-scheme, dark)");
  expect(themeStyles.cssText).toContain(':host([data-theme="light"])');
  expect(themeStyles.cssText).toContain("@media (prefers-color-scheme: light)");
});

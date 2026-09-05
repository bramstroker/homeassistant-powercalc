import { sharedStyles } from "../../styles";

it("uses dark native form controls so iOS select indicators remain visible", () => {
  expect(sharedStyles.cssText).toContain("color-scheme: dark");
});

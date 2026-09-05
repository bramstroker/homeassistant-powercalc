import { validateMetadata } from "./validation";

const valid = {
  manufacturer_name: "Signify", model_id: "LCT010", product_name: "Hue lamp", contributor: "Tester",
  contributor_github: "tester", measure_device: "Test meter", mains_voltage: 230, notes: "",
};

describe("metadata validation", () => {
  it("accepts optional blanks and valid metadata", () => {
    expect(validateMetadata(valid)).toEqual({});
    expect(validateMetadata({ ...valid, product_url: "https://example.com", gtins: ["12345678", "1234567890123"] })).toEqual({});
  });

  it("reports all missing required fields, including whitespace", () => {
    const errors = validateMetadata({ manufacturer_name: "", model_id: " ", product_name: "", contributor: "", notes: "" });
    expect(Object.keys(errors)).toEqual(["manufacturer_name", "model_id", "product_name", "contributor", "contributor_github", "measure_device", "mains_voltage"]);
  });

  it.each([110, 240])("rejects unsupported mains voltage %s", (mains_voltage) => {
    expect(validateMetadata({ ...valid, mains_voltage }).mains_voltage).toBe("Select either 120 V or 230 V.");
  });

  it("explains invalid formats and length limits", () => {
    expect(validateMetadata({ ...valid, model_id: "../model", product_url: "http://example.com", gtins: ["123"], notes: "a".repeat(2001) })).toMatchObject({
      model_id: expect.stringContaining("Start with a letter"), product_url: expect.stringContaining("https://"),
      gtins: expect.stringContaining("digits"), notes: "Use 2000 characters or fewer.",
    });
  });

  it.each(["invalid", "a@", "a@b", "a@@example.com", "a b@example.com"])("rejects invalid email %s", (contributor_email) => {
    expect(validateMetadata({ ...valid, contributor_email }).contributor_email).toContain("valid email address");
  });

  it.each(["", "name@example.com", "name+measurements@sub.example.com"])("accepts optional email %s", (contributor_email) => {
    expect(validateMetadata({ ...valid, contributor_email }).contributor_email).toBeUndefined();
  });

  it.each(["Anko Bladiebla", "anko: Bladiebla", "ANKO", "  Anko-Bulb"])("rejects a repeated manufacturer in %s", (product_name) => {
    expect(validateMetadata({ ...valid, manufacturer_name: "Anko", product_name }).product_name).toContain("Leave out the manufacturer");
  });

  it("does not reject partial matches or a manufacturer mentioned later in the name", () => {
    for (const product_name of ["Ankora bulb", "Lamp compatible with Anko"]) {
      expect(validateMetadata({ ...valid, manufacturer_name: "Anko", product_name }).product_name).toBeUndefined();
    }
  });
});

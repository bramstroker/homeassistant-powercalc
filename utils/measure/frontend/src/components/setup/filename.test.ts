import { recorderExportFilename } from "./options";

describe("recorderExportFilename", () => {
  it("follows the recorder purpose rather than the name a duplicated session left behind", () => {
    expect(recorderExportFilename("complex_profile", "kitchen.csv")).toBe("kitchen.jsonl");
    expect(recorderExportFilename("playbook", "kitchen.jsonl")).toBe("kitchen.csv");
  });

  it("shows the name the server will actually write for the default", () => {
    expect(recorderExportFilename("complex_profile", "record.csv")).toBe("record.jsonl");
    expect(recorderExportFilename("playbook", "record.csv")).toBe("record.csv");
    expect(recorderExportFilename("complex_profile", "")).toBe("record.jsonl");
  });

  it("leaves an extension it does not manage alone", () => {
    expect(recorderExportFilename("complex_profile", "kitchen.txt")).toBe("kitchen.txt");
    expect(recorderExportFilename("playbook", "kitchen")).toBe("kitchen");
  });
});

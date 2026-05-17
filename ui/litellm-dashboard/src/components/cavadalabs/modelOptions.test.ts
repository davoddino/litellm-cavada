import { describe, expect, it } from "vitest";
import { extractModelNamesFromResponse, extractModelNamesFromValue, modelNamesToOptions } from "./modelOptions";

describe("CavadaLabs model options", () => {
  it("should extract model names from LiteLLM model responses", () => {
    expect(
      extractModelNamesFromResponse({
        data: [
          { id: "Qwen3.6-35B-A3B" },
          { model_name: "whisper-small" },
          { model_group: "fallback-group" },
          { model: "openai/gpt-4.1" },
          { id: "Qwen3.6-35B-A3B" },
          {},
        ],
      }),
    ).toEqual(["Qwen3.6-35B-A3B", "whisper-small", "fallback-group", "openai/gpt-4.1"]);
  });

  it("should normalize saved Project allowed model values into select options", () => {
    expect(modelNamesToOptions(extractModelNamesFromValue([" qwen ", "qwen", "whisper-small"]))).toEqual([
      { label: "qwen", value: "qwen" },
      { label: "whisper-small", value: "whisper-small" },
    ]);
  });
});

import { describe, expect, it } from "vitest";
import { cavadaLabsUsageBreakdownRows } from "./CavadaLabsUsageBreakdown";

describe("cavadaLabsUsageBreakdownRows", () => {
  it("should build Company and Project usage breakdown rows without Organization or Team labels", () => {
    const rows = cavadaLabsUsageBreakdownRows(
      {
        entities: {
          "company-1": {
            metrics: {
              api_requests: 3,
              spend: 0.75,
              total_tokens: 90,
            },
          },
        },
        models: {
          "cavadalabs/qwen3-32b": {
            metrics: {
              api_requests: 2,
              spend: 0.5,
              total_tokens: 60,
            },
          },
        },
        providers: {
          cavadalabs: {
            metrics: {
              api_requests: 3,
              spend: 0.75,
              total_tokens: 90,
            },
          },
        },
        api_keys: {
          "hashed-key": {
            metrics: {
              api_requests: 1,
              spend: 0.25,
              total_tokens: 30,
            },
          },
        },
      },
      "Company",
    );

    expect(rows).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ category: "Company", name: "company-1", requests: 3, spend: 0.75, tokens: 90 }),
        expect.objectContaining({ category: "Model", name: "cavadalabs/qwen3-32b", requests: 2 }),
        expect.objectContaining({ category: "Provider", name: "cavadalabs", requests: 3 }),
        expect.objectContaining({ category: "API key", name: "hashed-key", requests: 1 }),
      ]),
    );
    expect(rows.map((row) => row.category)).not.toContain("Organization");
    expect(rows.map((row) => row.category)).not.toContain("Team");
  });
});

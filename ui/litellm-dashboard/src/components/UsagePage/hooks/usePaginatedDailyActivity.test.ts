import { describe, expect, it } from "vitest";
import { mergeDailyActivityMetadata } from "./usePaginatedDailyActivity";

describe("mergeDailyActivityMetadata", () => {
  it("should sum page metadata for standard daily activity endpoints", () => {
    const merged = mergeDailyActivityMetadata(
      {
        total_spend: 1,
        total_prompt_tokens: 10,
        total_completion_tokens: 20,
        total_tokens: 30,
        total_api_requests: 2,
        total_successful_requests: 2,
        total_failed_requests: 0,
        total_cache_read_input_tokens: 3,
        total_cache_creation_input_tokens: 4,
        page: 1,
        total_pages: 2,
        has_more: true,
      },
      {
        total_spend: 2,
        total_prompt_tokens: 40,
        total_completion_tokens: 50,
        total_tokens: 90,
        total_api_requests: 3,
        total_successful_requests: 2,
        total_failed_requests: 1,
        total_cache_read_input_tokens: 5,
        total_cache_creation_input_tokens: 6,
        page: 2,
        total_pages: 2,
        has_more: false,
      },
      "sum_pages",
    );

    expect(merged.total_spend).toBe(3);
    expect(merged.total_prompt_tokens).toBe(50);
    expect(merged.total_completion_tokens).toBe(70);
    expect(merged.total_tokens).toBe(120);
    expect(merged.total_api_requests).toBe(5);
    expect(merged.total_successful_requests).toBe(4);
    expect(merged.total_failed_requests).toBe(1);
    expect(merged.total_cache_read_input_tokens).toBe(8);
    expect(merged.total_cache_creation_input_tokens).toBe(10);
  });

  it("should preserve full-range metadata for CavadaLabs Company and Project daily activity", () => {
    const merged = mergeDailyActivityMetadata(
      {
        total_spend: 12.5,
        total_prompt_tokens: 100,
        total_completion_tokens: 200,
        total_tokens: 300,
        total_api_requests: 10,
        total_successful_requests: 9,
        total_failed_requests: 1,
        page: 1,
        total_pages: 2,
        has_more: true,
      },
      {
        total_spend: 12.5,
        total_prompt_tokens: 100,
        total_completion_tokens: 200,
        total_tokens: 300,
        total_api_requests: 10,
        total_successful_requests: 9,
        total_failed_requests: 1,
        page: 2,
        total_pages: 2,
        has_more: false,
      },
      "full_range",
    );

    expect(merged.total_spend).toBe(12.5);
    expect(merged.total_prompt_tokens).toBe(100);
    expect(merged.total_completion_tokens).toBe(200);
    expect(merged.total_tokens).toBe(300);
    expect(merged.total_api_requests).toBe(10);
    expect(merged.total_successful_requests).toBe(9);
    expect(merged.total_failed_requests).toBe(1);
    expect(merged.page).toBe(2);
    expect(merged.total_pages).toBe(2);
    expect(merged.has_more).toBe(false);
  });
});

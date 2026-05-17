import { describe, expect, it } from "vitest";
import { resolveCavadaLabsProductContext } from "./productContext";

describe("CavadaLabs product context", () => {
  it("should keep LiteLLM compatibility fields hidden while CavadaLabs context is loading", () => {
    expect(
      resolveCavadaLabsProductContext({
        companies: [],
        projects: [],
        isLoading: true,
        errorDetail: null,
      }),
    ).toEqual({
      contextKnown: false,
      isLoading: true,
      isCavadaLabsProductContext: false,
      showLiteLLMCompatibilityFields: false,
    });
  });

  it("should treat explicit CavadaLabs product context as active even without tenant options", () => {
    expect(
      resolveCavadaLabsProductContext({
        companies: [],
        projects: [],
        isLoading: false,
        errorDetail: null,
        contextKnown: true,
        isCavadaLabsProductContext: true,
      }),
    ).toEqual({
      contextKnown: true,
      isLoading: false,
      isCavadaLabsProductContext: true,
      showLiteLLMCompatibilityFields: false,
    });
  });

  it("should preserve legacy LiteLLM fields when context is known non-CavadaLabs", () => {
    expect(
      resolveCavadaLabsProductContext({
        companies: [],
        projects: [],
        isLoading: false,
        errorDetail: null,
        contextKnown: true,
        isCavadaLabsProductContext: false,
      }),
    ).toEqual({
      contextKnown: true,
      isLoading: false,
      isCavadaLabsProductContext: false,
      showLiteLLMCompatibilityFields: true,
    });
  });
});

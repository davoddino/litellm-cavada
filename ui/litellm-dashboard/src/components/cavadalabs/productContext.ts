import type { CavadaLabsKeyContextOptions } from "./keyContext";

export interface CavadaLabsProductContextState {
  contextKnown: boolean;
  isLoading: boolean;
  isCavadaLabsProductContext: boolean;
  showLiteLLMCompatibilityFields: boolean;
}

export const resolveCavadaLabsProductContext = (
  options: Partial<CavadaLabsKeyContextOptions>,
): CavadaLabsProductContextState => {
  const companies = options.companies ?? [];
  const projects = options.projects ?? [];
  const isLoading = options.isLoading === true;
  const hasTenantOptions = companies.length > 0 || projects.length > 0;
  const hasExplicitContextFlag = typeof options.isCavadaLabsProductContext === "boolean";
  const inferredContextKnown = hasExplicitContextFlag || hasTenantOptions || (!isLoading && options.errorDetail == null);
  const contextKnown = options.contextKnown ?? inferredContextKnown;
  const isCavadaLabsProductContext = options.isCavadaLabsProductContext ?? hasTenantOptions;

  return {
    contextKnown,
    isLoading,
    isCavadaLabsProductContext,
    showLiteLLMCompatibilityFields: contextKnown ? !isCavadaLabsProductContext : false,
  };
};

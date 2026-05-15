import { afterEach, describe, expect, it } from "vitest";
import { buildUiPath, getUiBasePath } from "./uiRoutes";

describe("uiRoutes", () => {
  const originalUrl = window.location.href;

  afterEach(() => {
    window.history.replaceState(null, "", originalUrl);
  });

  it("should preserve the proxy-served /ui base path at runtime", () => {
    window.history.replaceState(null, "", "/ui/cavadalabs");

    expect(getUiBasePath()).toBe("/ui/");
    expect(buildUiPath("cavadalabs/projects")).toBe("/ui/cavadalabs/projects");
  });

  it("should preserve server root path plus /ui at runtime", () => {
    window.history.replaceState(null, "", "/gateway/ui/cavadalabs");

    expect(getUiBasePath("/gateway")).toBe("/gateway/ui/");
    expect(buildUiPath("cavadalabs/companies", "/gateway")).toBe("/gateway/ui/cavadalabs/companies");
  });
});

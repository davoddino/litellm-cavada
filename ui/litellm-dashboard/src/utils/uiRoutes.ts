const UI_ROUTE_PREFIX = "ui";

export function normalizeBasePrefix(raw: string | undefined | null): string {
  const trimmed = (raw ?? "").trim();
  if (!trimmed) return "";
  const core = trimmed.replace(/^\/+/, "").replace(/\/+$/, "");
  return core ? `/${core}/` : "/";
}

function normalizeServerRootPath(serverRootPath?: string | null): string {
  if (!serverRootPath || serverRootPath === "/") return "";
  const clean = serverRootPath.replace(/^\/+/, "").replace(/\/+$/, "");
  return clean ? `/${clean}` : "";
}

function detectRuntimeUiBasePath(serverRootPath?: string | null): string | null {
  if (typeof window === "undefined") return null;

  const pathname = window.location.pathname || "/";
  const rootPath = normalizeServerRootPath(serverRootPath);
  const candidates = rootPath ? [`${rootPath}/${UI_ROUTE_PREFIX}`, `/${UI_ROUTE_PREFIX}`] : [`/${UI_ROUTE_PREFIX}`];

  for (const candidate of candidates) {
    if (pathname === candidate || pathname.startsWith(`${candidate}/`)) {
      return `${candidate}/`;
    }
  }

  return null;
}

export function getUiBasePath(serverRootPath?: string | null): string {
  const runtimeBasePath = detectRuntimeUiBasePath(serverRootPath);
  if (runtimeBasePath) return runtimeBasePath;

  const configuredBasePath = normalizeBasePrefix(process.env.NEXT_PUBLIC_BASE_URL);
  const rootPath = normalizeServerRootPath(serverRootPath);
  if (configuredBasePath && configuredBasePath !== "/") {
    return `${rootPath}${configuredBasePath}`;
  }

  return rootPath ? `${rootPath}/` : "/";
}

export function buildUiPath(routeSegment: string, serverRootPath?: string | null): string {
  const base = getUiBasePath(serverRootPath);
  const body = routeSegment.startsWith("/") ? routeSegment.slice(1) : routeSegment;
  return `${base}${body}`;
}

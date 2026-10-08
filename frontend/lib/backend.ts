const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";

export function backendUrl(path: string): string {
  const base = (process.env.VIKATHIRE_API_BASE_URL ?? DEFAULT_BACKEND_URL).replace(/\/$/, "");
  return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function proxyBackend(request: Request, path: string): Promise<Response> {
  try {
    const upstream = await fetch(backendUrl(path), {
      method: request.method,
      body: request.method === "GET" ? undefined : await request.formData(),
      cache: "no-store",
      signal: AbortSignal.timeout(180_000),
    });
    const body = await upstream.arrayBuffer();
    return new Response(body, {
      status: upstream.status,
      headers: {
        "content-type": upstream.headers.get("content-type") ?? "application/json",
        "cache-control": "no-store",
      },
    });
  } catch {
    return Response.json({ detail: "screening backend is unavailable" }, { status: 502 });
  }
}

import { proxyBackend } from "@/lib/backend";

type RouteContext = { params: Promise<{ screeningId: string }> };

export async function GET(_request: Request, context: RouteContext): Promise<Response> {
  const { screeningId } = await context.params;
  return proxyBackend(_request, `/screenings/${encodeURIComponent(screeningId)}`);
}

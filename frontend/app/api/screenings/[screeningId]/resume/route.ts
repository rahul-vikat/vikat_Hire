import { proxyBackend } from "@/lib/backend";

export const runtime = "nodejs";

type RouteContext = { params: Promise<{ screeningId: string }> };

export async function POST(request: Request, context: RouteContext): Promise<Response> {
  const { screeningId } = await context.params;
  return proxyBackend(request, `/screenings/${encodeURIComponent(screeningId)}/resume-upload`);
}

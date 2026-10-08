import { proxyBackend } from "@/lib/backend";

export const runtime = "nodejs";

export async function POST(request: Request): Promise<Response> {
  return proxyBackend(request, "/screenings/upload");
}

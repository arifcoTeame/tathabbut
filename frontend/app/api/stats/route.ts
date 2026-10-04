const API = process.env.TATHABBUT_API_URL ?? "http://localhost:8000";

// Also used to wake a sleeping free-tier backend (up to about a minute).
export const maxDuration = 60;

export async function GET(req: Request) {
  try {
    const res = await fetch(`${API}/index/stats`, {
      cache: "no-store",
      signal: AbortSignal.any([req.signal, AbortSignal.timeout(55_000)]),
    });
    const data: unknown = await res.json();
    return Response.json(data, {
      status: res.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json({ detail: "offline" }, { status: 502, headers: { "Cache-Control": "no-store" } });
  }
}

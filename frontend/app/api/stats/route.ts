const API = process.env.TATHABBUT_API_URL ?? "http://localhost:8000";

// Also used to wake a sleeping free-tier backend (up to about a minute).
export const maxDuration = 60;

export async function GET() {
  try {
    const res = await fetch(`${API}/index/stats`, { cache: "no-store", signal: AbortSignal.timeout(55_000) });
    return new Response(await res.text(), {
      status: res.status,
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  } catch {
    return Response.json({ detail: "offline" }, { status: 502 });
  }
}

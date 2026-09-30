const API = process.env.TATHABBUT_API_URL ?? "http://localhost:8000";

export async function GET() {
  try {
    const res = await fetch(`${API}/index/stats`, { cache: "no-store", signal: AbortSignal.timeout(8_000) });
    return new Response(await res.text(), {
      status: res.status,
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  } catch {
    return Response.json({ detail: "offline" }, { status: 502 });
  }
}

// Server-side proxy to the FastAPI engine: the browser never talks to the backend
// directly (no CORS setup, backend URL stays private). Request text is not logged.

const API = process.env.TATHABBUT_API_URL ?? "http://localhost:8000";

// A free-tier backend may be asleep; waking it can take up to about a minute.
export const maxDuration = 60;

export async function POST(req: Request) {
  const body = await req.text();
  try {
    const res = await fetch(`${API}/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(55_000),
    });
    return new Response(await res.text(), {
      status: res.status,
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  } catch {
    return Response.json(
      { detail: "تعذّر الوصول إلى محرّك التحقق. قد يكون في طور الاستيقاظ؛ أعد المحاولة بعد لحظات." },
      { status: 502 },
    );
  }
}

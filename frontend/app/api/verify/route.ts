// Server-side proxy to the FastAPI engine: the browser never talks to the backend
// directly (no CORS setup, backend URL stays private). Request text is not logged.
import { MAX_INPUT_CHARS, MAX_REQUEST_BYTES } from "@/lib/limits";

const API = process.env.TATHABBUT_API_URL ?? "http://localhost:8000";

// A free-tier backend may be asleep; waking it can take up to about a minute.
export const maxDuration = 60;

export async function POST(req: Request) {
  const headers = { "Cache-Control": "no-store" };
  const contentLength = Number(req.headers.get("content-length"));
  if (contentLength > MAX_REQUEST_BYTES) {
    return Response.json({ detail: "حجم الطلب أكبر من المسموح." }, { status: 413, headers });
  }

  let input: unknown;
  const reader = req.body?.getReader();
  if (!reader) return Response.json({ detail: "أدخل نصاً للتحقق." }, { status: 400, headers });
  try {
    const decoder = new TextDecoder();
    let body = "";
    let bytes = 0;
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      bytes += chunk.value.byteLength;
      if (bytes > MAX_REQUEST_BYTES) {
        await reader.cancel();
        return Response.json({ detail: "حجم الطلب أكبر من المسموح." }, { status: 413, headers });
      }
      body += decoder.decode(chunk.value, { stream: true });
    }
    input = JSON.parse(body + decoder.decode());
  } catch {
    return Response.json({ detail: "صيغة الطلب غير صالحة." }, { status: 400, headers });
  } finally {
    reader.releaseLock();
  }

  if (!input || typeof input !== "object" || !("text" in input) || typeof input.text !== "string") {
    return Response.json({ detail: "أدخل نصاً للتحقق." }, { status: 422, headers });
  }
  const text = input.text.trim();
  if (text.length < 2 || text.length > MAX_INPUT_CHARS) {
    return Response.json(
      { detail: `يجب أن يكون طول النص بين حرفين و${MAX_INPUT_CHARS} حرف.` },
      { status: 422, headers },
    );
  }

  try {
    const res = await fetch(`${API}/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      cache: "no-store",
      signal: AbortSignal.any([req.signal, AbortSignal.timeout(55_000)]),
    });
    const data: unknown = await res.json();
    return Response.json(data, {
      status: res.status,
      headers,
    });
  } catch (error) {
    const timedOut = error instanceof Error && error.name === "TimeoutError";
    return Response.json(
      { detail: timedOut
        ? "استغرق المحرك وقتاً أطول من المتوقع. أعد المحاولة بعد لحظات."
        : "تعذّر الوصول إلى محرّك التحقق. قد يكون في طور الاستيقاظ؛ أعد المحاولة بعد لحظات." },
      { status: timedOut ? 504 : 502, headers },
    );
  }
}

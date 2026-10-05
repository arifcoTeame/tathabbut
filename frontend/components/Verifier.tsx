"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import type { IndexStats, VerifyResponse } from "@/lib/types";
import { MAX_INPUT_CHARS } from "@/lib/limits";
import { VERDICT_META, VERDICT_ORDER } from "@/lib/verdicts";
import ClaimCard from "./ClaimCard";

const REQUEST_TIMEOUT_MS = 60_000;

function claimsCount(n: number): string {
  if (n === 1) return "ادعاء واحد";
  if (n === 2) return "ادعاءان";
  if (n >= 3 && n <= 10) return `${n} ادعاءات`;
  return `${n} ادعاءً`;
}

const EXAMPLES: { label: string; text: string }[] = [
  {
    label: "منشور بثلاثة ادعاءات",
    text:
      "قال رسول الله ﷺ: «اطلبوا العلم ولو بالصين». وقال تعالى: ﴿ومن يتوكل على الله فهو حسبه ونعم الوكيل﴾، " +
      "فلا تخف من المستقبل. وسألني أحد المتابعين: «أنا مقيم في بلد غير مسلم وزوجتي تطلب الطلاق، هل يجوز لي رفض طلبها؟» " +
      "فأجبته بأن ذلك لا يجوز.",
  },
  { label: "حديث منتشر", text: "حب الوطن من الإيمان" },
  { label: "آية دون همزات", text: "قل هو الله احد" },
  { label: "حديث غير موجود في القاعدة", text: "قال رسول الله ﷺ: «تفاءلوا بالخير تجدوه»" },
  { label: "آية بكلمة مستبدلة", text: "قال تعالى: ﴿لا يكلف الله نفسا إلا طاقتها﴾" },
  { label: "آية منسوبة للنبي ﷺ", text: "قال النبي ﷺ: «قل هو الله أحد الله الصمد»" },
  { label: "حديث صحيح", text: "قال رسول الله ﷺ: «لا يؤمن أحدكم حتى يحب لأخيه ما يحب لنفسه»" },
  { label: "حديث اختلف فيه المحدّثون", text: "قال رسول الله ﷺ: «خير الناس أنفعهم للناس»" },
  { label: "لفظ متداول يحتاج تحققاً", text: "قال رسول الله ﷺ: «إنما بعثت لأتمم مكارم الأخلاق»" },
];

type Status =
  | { state: "checking"; waking: boolean }
  | { state: "up"; stats: IndexStats }
  | { state: "down" };

function IndexStatus({ status, onRetry }: { status: Status; onRetry: () => void }) {
  if (status.state === "checking")
    return (
      <span className="status" role="status">
        <span className="dot pulse" />
        {status.waking ? "المحرك يستيقظ… قد يستغرق ذلك دقيقة" : "جارٍ الاتصال بالمحرك…"}
      </span>
    );
  if (status.state === "down")
    return (
      <span className="status" role="status">
        <span className="dot down" />المحرك غير متصل
        <button className="btn-ghost" onClick={onRetry}>إعادة المحاولة</button>
      </span>
    );
  const s = status.stats;
  return (
    <span className="status" role="status" title={`نموذج التضمين: ${s.embedder}`}>
      <span className="dot ok" />
      {s.quran_complete ? `المصحف كاملاً (${s.quran.toLocaleString("ar")} آية)` : `عينة قرآنية (${s.quran} آية)`}
      {" · "}
      {s.hadith} حديثاً مفهرساً
    </span>
  );
}

export default function Verifier() {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VerifyResponse | null>(null);
  const [status, setStatus] = useState<Status>({ state: "checking", waking: false });
  const resultsRef = useRef<HTMLDivElement>(null);
  const requestRef = useRef<AbortController | null>(null);
  const connectionRef = useRef<AbortController | null>(null);
  const requestId = useRef(0);

  function changeText(value: string) {
    requestId.current += 1;
    requestRef.current?.abort();
    requestRef.current = null;
    setText(value);
    setLoading(false);
    setResult(null);
    setError(null);
  }

  // Doubles as a wake-up call for a sleeping free-tier backend.
  const connect = useCallback(() => {
    connectionRef.current?.abort();
    const controller = new AbortController();
    connectionRef.current = controller;
    setStatus({ state: "checking", waking: false });
    const slow = setTimeout(() => {
      if (connectionRef.current === controller) setStatus({ state: "checking", waking: true });
    }, 3000);
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    fetch("/api/stats", { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((stats: IndexStats) => {
        if (connectionRef.current === controller) setStatus({ state: "up", stats });
      })
      .catch(() => {
        if (connectionRef.current === controller) setStatus({ state: "down" });
      })
      .finally(() => {
        clearTimeout(slow);
        clearTimeout(timeout);
        if (connectionRef.current === controller) connectionRef.current = null;
      });
  }, []);

  useEffect(() => {
    connect();
    return () => {
      requestId.current += 1;
      requestRef.current?.abort();
      connectionRef.current?.abort();
      requestRef.current = null;
      connectionRef.current = null;
    };
  }, [connect]);

  async function verify(input = text) {
    const value = input.trim();
    if (value.length < 2 || input.length > MAX_INPUT_CHARS) return;
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    const id = ++requestId.current;
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, REQUEST_TIMEOUT_MS);
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: value }),
        signal: controller.signal,
      });
      const data = await res.json().catch(() => {
        throw new Error("لم تصل استجابة سليمة من المحرك. أعد المحاولة بعد لحظات.");
      });
      if (!res.ok) throw new Error(typeof data?.detail === "string" ? data.detail : "تعذّر إتمام التحقق.");
      if (!data || !Array.isArray(data.claims) || !data.summary || !data.index) {
        throw new Error("لم تصل استجابة سليمة من المحرك. أعد المحاولة بعد لحظات.");
      }
      if (id !== requestId.current) return;
      setResult(data as VerifyResponse);
      connectionRef.current?.abort();
      connectionRef.current = null;
      setStatus({ state: "up", stats: data.index });
      requestAnimationFrame(() => {
        if (id === requestId.current) resultsRef.current?.focus();
      });
    } catch (e) {
      if (id !== requestId.current) return;
      setResult(null);
      setError(timedOut
        ? "استغرق المحرك وقتاً أطول من المتوقع. أعد المحاولة بعد لحظات."
        : e instanceof TypeError
          ? "تعذّر الاتصال بالمحرك. تحقق من اتصالك وأعد المحاولة."
          : e instanceof Error ? e.message : "تعذّر إتمام التحقق.");
    } finally {
      clearTimeout(timeout);
      if (id === requestId.current) {
        requestRef.current = null;
        setLoading(false);
      }
    }
  }

  const over = text.length > MAX_INPUT_CHARS;
  const needsReferral = result?.claims.some((claim) => claim.verdict.code === "REFER") ?? false;

  return (
    <>
      <header className="topbar">
        <img src="/logo.png" alt="تثبّت — محرّك التحقق المُسنَد للمحتوى الإسلامي" />
        <IndexStatus status={status} onRetry={connect} />
      </header>

      <section className="hero">
        <h1>تحقّق قبل أن تنشر</h1>
        <p>
          الصق منشوراً أو نصاً يتضمن أحاديث أو آيات أو أقوالاً منسوبة. يفحص «تثبّت» حتى 12 مقطعاً
          مستخرجاً في الطلب، ويقارنها بالمصادر المفهرسة، ثم يعرض النتيجة ودليلها. قسّم النصوص الطويلة
          إلى طلبات أقصر للتحقق من بقية المقاطع.
        </p>
        <p className="coverage-note" id="coverage-note">
          القرآن: المصحف كاملًا (6,236 آية) من Quranpedia. الأحاديث: قاعدة الأحاديث الحالية في المنصة
          بأحكامها من الدرر السنية فقط؛ عدم العثور على حديث هنا لا يعني أنه غير موجود في الدرر السنية ولا يحكم عليه.
          {" "}<Link href="/about">المصادر ونطاق التحقق والخصوصية</Link>
        </p>
      </section>

      <div className="grid">
        <section className="panel sticky" aria-label="النص المراد التحقق منه">
          <h2>
            <label htmlFor="post">النص المراد التحقق منه</label>
            {text && (
              <button className="btn-ghost" onClick={() => changeText("")}>
                مسح
              </button>
            )}
          </h2>
          <textarea
            id="post"
            className="post"
            value={text}
            onChange={(e) => changeText(e.target.value)}
            aria-describedby="post-count coverage-note"
            aria-invalid={over}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                if (!loading) verify();
              }
            }}
            placeholder="الصق هنا منشوراً أو حديثاً أو آية…"
          />
          <div className="row">
            <span id="post-count" className={`count ${over ? "over" : ""}`}>
              {text.length.toLocaleString("ar")} / {MAX_INPUT_CHARS.toLocaleString("ar")} حرف
              {over && " — اختصر النص لإتمام التحقق"}
            </span>
            <span className="kbd" dir="ltr">Ctrl / ⌘ + Enter</span>
            <button className="btn" onClick={() => verify()} disabled={loading || over || text.trim().length < 2}>
              {loading ? "جارٍ التحقق…" : "تثبّت الآن"}
            </button>
          </div>
          <div className="examples">
            <span className="label">أمثلة للتجربة:</span>
            {EXAMPLES.map((ex) => (
              <button
                key={ex.label}
                className="btn-ghost"
                onClick={() => { changeText(ex.text); verify(ex.text); }}
              >
                {ex.label}
              </button>
            ))}
          </div>
        </section>

        <section aria-label="نتائج التحقق" aria-live="polite" aria-busy={loading} tabIndex={-1} ref={resultsRef}>
          {error && <div className="error" role="alert">{error}</div>}
          {loading && <div className="loading">جارٍ استخراج الادعاءات ومطابقتها بالمصادر…</div>}
          {!loading && !error && !result && (
            <div className="empty">
              ستظهر هنا «بطاقة تثبّت» لكل ادعاء: الحكم، والنص المعتمد، والمصدر، والفروق كلمة بكلمة.
            </div>
          )}
          {!loading && result && (
            <>
              <h2 className="sr-only">نتائج التحقق</h2>
              {needsReferral && (
                <div className="referral-notice" role="note" aria-labelledby="referral-heading">
                  <h3 id="referral-heading">تحتاج هذه الحالة إلى مختص</h3>
                  <p>
                    توثيق الآية أو الحديث هنا يخص النص ونسبته فقط. لا يثبت صحة الاستدلال به
                    على حالتك، ولا يعني جواز الفعل المذكور. اعرض السؤال وسياقه على مختص مؤهل.
                  </p>
                </div>
              )}
              <div className="summary">
                {VERDICT_ORDER.map((code) => (
                  <span key={code} className={`chip ${result.summary[code] ? "" : "zero"}`}>
                    {VERDICT_META[code].label}
                    <b>{result.summary[code] ?? 0}</b>
                  </span>
                ))}
                <details className="meta-line">
                  <summary>{claimsCount(result.claims.length)} · تفاصيل تقنية</summary>
                  زمن الاستجابة {result.elapsed_ms} ms
                  {result.engine_version && <> · إصدار المحرك <bdi>{result.engine_version}</bdi></>}
                </details>
              </div>
              {result.claims.length === 0 ? (
                <div className="empty">لم يُعثر على ادعاءات شرعية قابلة للتحقق في هذا النص.</div>
              ) : (
                <div className="cards">
                  {result.claims.map((c) => (
                    <ClaimCard key={c.id} claim={c} />
                  ))}
                </div>
              )}
            </>
          )}
        </section>
      </div>

      <footer className="footer">
        <span>
          تثبّت أداة برمجية آلية تقارن النص بالمصادر المفهرسة بقواعد ثابتة؛ لا يراجع نتائجها مختص بشري ولا تُغني عنه.
          نتائج المطابقة تخص المقاطع المستخرجة ولا تُعد فتوى أو اعتماداً للمنشور كاملاً.
        </span>
        <nav aria-label="روابط المشروع">
          <Link href="/about">المصادر والخصوصية</Link>
          <a href="https://github.com/arifcoTeame/tathabbut/issues/new" target="_blank" rel="noopener noreferrer">
            الإبلاغ عن خطأ في نتيجة ↗
          </a>
        </nav>
      </footer>
    </>
  );
}

import type { Claim } from "@/lib/types";
import { LEVEL_LABEL, TYPE_LABEL, VERDICT_META, pct, verseLabel } from "@/lib/verdicts";
import DiffView from "./DiffView";

function SourceLine({ claim }: { claim: Claim }) {
  const s = claim.source!;
  return (
    <div className="src">
      {s.kind === "quran" ? <span>{verseLabel(s.ref)}</span> : s.ref.narrator ? <span>الراوي: {s.ref.narrator}</span> : null}
      {s.url && (
        <a href={s.url} target="_blank" rel="noopener noreferrer">
          {s.kind === "quran" ? "عرض الآية في الموسوعة القرآنية (طبعة المجمع)" : "التحقق في الدرر السنية"} ↗
        </a>
      )}
      {!s.verified && <span className="tag warn">سجل تجريبي لم يُراجع بعد</span>}
    </div>
  );
}

export default function ClaimCard({ claim }: { claim: Claim }) {
  const meta = VERDICT_META[claim.verdict.code];
  const src = claim.source;
  const showDiff = claim.diff.length > 0 && claim.diff.some((d) => d.op !== "equal");
  const misattributed = claim.type_hint === "hadith" && src?.kind === "quran";
  const hadithReview = src?.kind === "hadith" && claim.verdict.code === "NEEDS_REVIEW";

  return (
    <article className="card" aria-labelledby={`claim-${claim.id}`}>
      <div className={`badge tone-${meta.tone}`}>
        {claim.verdict.code === "NO_ORIGIN" ? meta.label : claim.verdict.label_ar}
        <small>{meta.hint}</small>
        {misattributed && <span className="flag">⚠ النص آية لا حديث</span>}
      </div>

      <div>
        <div className="c-head">
          <span>الادعاء {claim.id} · {TYPE_LABEL[claim.type_hint]}</span>
          <span>{LEVEL_LABEL[claim.level]}</span>
        </div>
        <p className="c-claim" id={`claim-${claim.id}`}>«{claim.text}»</p>

        {claim.verdict.code === "NO_ORIGIN" && (
          <p className="coverage-note">
            {claim.type_hint === "quran"
              ? "لم نجد نصاً مطابقاً في الفهرس القرآني الحالي. راجع النص ونسبته إلى المصحف."
              : "لم نجد مطابقة في المجموعة المفهرسة. هذه النتيجة لا تثبت أن الحديث لا أصل له، ولا تحكم بصحته أو ضعفه."}
            {(claim.type_hint === "hadith" || claim.type_hint === "unknown") && (
              <>
                {" "}
                <a href={`https://dorar.net/hadith/search?q=${encodeURIComponent(claim.text)}`} target="_blank" rel="noopener noreferrer">
                  البحث في الدرر السنية ↗
                </a>
              </>
            )}
          </p>
        )}

        {src && (
          <>
            <blockquote className="quote">
              <span className="lbl">
                {src.kind === "quran" ? "النص المعتمد من المصحف — منسوخ من الفهرس" : "النص كما هو مسجّل في المصدر"}
              </span>
              {src.kind === "quran" ? `﴿${src.text}﴾` : src.text}
              {src.kind === "hadith" && src.ref.context && src.ref.context !== src.text && (
                <span className="ctx">
                  <span className="lbl">الموضع كاملاً كما تعرضه الدرر السنية</span>
                  {src.ref.context}
                </span>
              )}
            </blockquote>
            <SourceLine claim={claim} />
          </>
        )}

        {claim.grades.length > 0 && (
          <>
            {hadithReview && (
              <p className="coverage-note">الدرجات التالية تخص نص المصدر؛ لا تُنقل إلى النص المدخل قبل مراجعة الفروق.</p>
            )}
            <ul className="grades" aria-label="أحكام المحدّثين لنص المصدر">
              {claim.grades.map((g, i) => (
                <li key={i}>
                  <b>{g.grade}</b> — {g.muhaddith}، {g.source} ({g.ref})
                  {g.note && <span className="tag">{g.note}</span>}
                </li>
              ))}
            </ul>
          </>
        )}

        {showDiff && (
          <div style={{ marginTop: 8 }}>
            <div className="c-head">الفروق كلمة بكلمة</div>
            <DiffView ops={claim.diff} sourceKind={src?.kind} />
          </div>
        )}

        {claim.alternatives.length > 0 && (
          <div className="src" style={{ marginTop: 8 }}>
            <span>مواضع أخرى:</span>
            {claim.alternatives.map((a) => (
              <a key={a.id} href={a.url} target="_blank" rel="noopener noreferrer">
                {verseLabel(a.ref).replace("سورة ", "")}
              </a>
            ))}
          </div>
        )}

        {claim.closest && (
          <blockquote className="quote muted">
            <span className="lbl">{claim.closest.note}</span>
            {claim.closest.text}
            {claim.closest.grades?.length > 0 && (
              <span className="src" style={{ display: "block", marginTop: 4 }}>
                {claim.closest.grades
                  .map((g) => `${g.muhaddith} (${g.source} ${g.ref}): ${g.grade}${g.note ? ` — ${g.note}` : ""}`)
                  .join("؛ ")}
              </span>
            )}
          </blockquote>
        )}

        {claim.notes.length > 0 && (
          <ul className="notes">
            {claim.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        )}

        {claim.explanation && (
          <div className="gen">
            <span className="tag">{claim.explanation.kind === "template" ? "توضيح آلي" : "شرح مولَّد"}</span>
            {claim.explanation.text}
          </div>
        )}

        {claim.evidence && (
          <details className="evidence">
            <summary>أدلة المطابقة</summary>
            <dl>
              <dt>تغطية ألفاظ الادعاء</dt><dd>{pct(claim.evidence.claim_coverage)}</dd>
              <dt>تغطية الكلمات الجوهرية</dt><dd>{pct(claim.evidence.content_coverage)}</dd>
              <dt>تطابق المقطع في المصدر</dt><dd>{pct(claim.evidence.span_coverage)}</dd>
              <dt>ترتيب الاسترجاع (لفظي / دلالي)</dt>
              <dd>{claim.evidence.bm25_rank ?? "—"} / {claim.evidence.dense_rank ?? "—"}</dd>
            </dl>
          </details>
        )}
      </div>
    </article>
  );
}

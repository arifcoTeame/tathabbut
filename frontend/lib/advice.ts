import type { Claim, DiffOp, Grade } from "./types";

/**
 * What the reader should take away from a card, in plain words, before the details.
 * Labels never go beyond the two approved references: the Quran text and verse
 * links from Quranpedia (King Fahd print), hadith grades as recorded in Dorar.
 */
export interface Outcome {
  label: string;      // short result shown on the badge
  hint: string;       // second line of the badge
  tone: string;       // CSS tone
  icon: string;
  summary: string;    // what was found
  advice: string;     // what to do before publishing
  note?: string;      // an extra caution shown under the advice
}

/** The hadith base is a limited trial set, unlike the Quran base (the whole mushaf). */
export const HADITH_NOT_FOUND_TEXT = "لم يُعثر على تطابق مطابق ضمن قاعدة الأحاديث الحالية في منصة تثبّت.";
export const HADITH_NOT_FOUND_NOTE =
  "هذه النتيجة لا تعني أن الحديث غير موجود في الدرر السنية، ولا تعني الحكم عليه بالصحة أو الضعف؛ بل تعني فقط أنه لم يُعثر عليه ضمن قاعدة الأحاديث الحالية في المنصة.";
export const HADITH_NOT_FOUND_ADVICE = "للتأكد من وجود النص وحكمه، ابحث عنه كاملًا في موقع الدرر السنية.";
export const DORAR_SEARCH_LABEL = "البحث عن النص كاملًا في الدرر السنية";
export const SIMILAR_TEXT = "هذه نتيجة مشابهة وليست تطابقًا مطابقًا للنص المدخل.";

type GradeKind = "sahih" | "hasan" | "weak" | "fabricated" | "baseless" | "unverified";

/** Strongest recorded grade class, using only the grades copied from Dorar. */
export function gradeKind(grades: Grade[]): GradeKind | null {
  if (!grades.length) return null;
  const classes = new Set(grades.map((g) => g.class));
  if (classes.has("authentic") && classes.size === 1) {
    return grades.some((g) => g.grade.includes("صحيح")) ? "sahih" : "hasan";
  }
  if (classes.has("fabricated")) return "fabricated";
  if (classes.has("baseless")) return "baseless";
  if (classes.has("weak") || classes.has("very_weak")) return "weak";
  return "unverified";
}

const GRADE_LABEL: Record<GradeKind, { label: string; tone: string; icon: string }> = {
  sahih: { label: "حديث صحيح", tone: "verified", icon: "✓" },
  hasan: { label: "حديث حسن", tone: "hasan", icon: "✓" },
  weak: { label: "حديث ضعيف", tone: "weak", icon: "!" },
  fabricated: { label: "حديث موضوع", tone: "fabricated", icon: "✕" },
  baseless: { label: "لا أصل له", tone: "fabricated", icon: "✕" },
  unverified: { label: "لا يصح مرفوعًا", tone: "weak", icon: "!" },
};

/** «في كلمة «طاقتها»، والصحيح «وسعها»» from the word diff. */
export function diffSentence(ops: DiffOp[], kind: "quran" | "hadith", place = ""): string {
  const parts: string[] = [];
  for (const op of ops) {
    // For a hadith the recorded wording is not called "the correct one": other narrations may differ.
    if (op.op === "changed") parts.push(kind === "quran" ? `في «${op.claim}»، والصحيح «${op.source}»` : `في «${op.claim}»، ولفظ المصدر «${op.source}»`);
    else if (op.op === "added") parts.push(`بزيادة «${op.claim}» ليست في ${kind === "quran" ? "الآية" : "لفظ المصدر"}`);
    else if (op.op === "missing") parts.push(`بنقص «${op.source}»`);
  }
  if (!parts.length) return "";
  const what = kind === "quran" ? "النص القرآني المعتمد في Quranpedia" : "لفظ الحديث المسجّل من الدرر السنية";
  return `النص المدخل يختلف عن ${what}${place ? ` (${place})` : ""} ${parts.slice(0, 4).join("، و")}.`;
}

function where(claim: Claim): string {
  const r = claim.source?.ref;
  if (!r?.surah_name) return "";
  return r.ayah_end ? `سورة ${r.surah_name}، الآيات ${r.ayah}–${r.ayah_end}` : `سورة ${r.surah_name}، الآية ${r.ayah}`;
}

function gradeLine(grades: Grade[]): string {
  return grades.slice(0, 2).map((g) => `${g.grade} — ${g.muhaddith}، ${g.source}${g.ref ? ` (${g.ref})` : ""}`).join("؛ ");
}

export function outcome(claim: Claim): Outcome {
  const src = claim.source;
  const isQuran = src?.kind === "quran";
  const attributedToProphet = claim.type_hint === "hadith";
  const dorar = "لا تنسب النص إلى النبي ﷺ ولا تنشره على أنه حديث صحيح قبل التحقق من الدرر السنية.";

  switch (claim.verdict.code) {
    case "VERIFIED": {
      if (isQuran) {
        return {
          label: "مطابق للنص القرآني", hint: "النص المعتمد في Quranpedia", tone: "verified", icon: "✓",
          summary: `تم العثور على تطابق مطابق في المصحف القرآني المعتمد من Quranpedia: ${where(claim)}.`,
          advice: attributedToProphet
            ? "النص آية قرآنية لا حديث؛ انشره آيةً مع ذكر السورة والآية، ولا تنسبه إلى النبي ﷺ."
            : "يمكن نشره آيةً بهذا النص مع ذكر السورة والآية.",
        };
      }
      const g = GRADE_LABEL[gradeKind(claim.grades) ?? "sahih"];
      return {
        label: g.label, hint: "بحسب الدرر السنية", tone: g.tone, icon: g.icon,
        summary: `وُجد بلفظه ضمن قاعدة الأحاديث الحالية في المنصة، وحكمه المنقول من الدرر السنية: ${gradeLine(claim.grades)}.`,
        advice: "يمكن نشره منسوبًا إلى النبي ﷺ مع ذكر مصدره وحكمه كما في الدرر السنية.",
      };
    }
    case "NOT_AUTHENTIC": {
      const kind = gradeKind(claim.grades) ?? "unverified";
      const g = GRADE_LABEL[kind];
      const word = kind === "weak" ? "ضعيف" : kind === "fabricated" ? "موضوع" : kind === "baseless" ? "لا أصل له" : "لا يصح مرفوعًا";
      return {
        label: g.label, hint: "بحسب الدرر السنية", tone: g.tone, icon: g.icon,
        summary: `وُجد ضمن قاعدة الأحاديث الحالية في المنصة، وحكمه المنقول من الدرر السنية: ${gradeLine(claim.grades)}.`,
        advice: `الحديث ${word} بحسب الدرر السنية، فلا يُنشر على أنه حديث صحيح ولا يُنسب إلى النبي ﷺ.`,
      };
    }
    case "DISPUTED":
      return {
        label: "اختلف المحدّثون في حكمه", hint: "بحسب الدرر السنية", tone: "disputed", icon: "⇄",
        summary: `الأحكام المسجّلة في الدرر السنية مختلفة: ${gradeLine(claim.grades)}.`,
        advice: "لا تنشره بصيغة الجزم بصحته؛ الأحكام معروضة كما هي دون ترجيح، ويُرجع فيه إلى مختص.",
      };
    case "ALTERED":
      return {
        label: "يختلف عن النص القرآني", hint: "النص المعتمد في Quranpedia", tone: "altered", icon: "≠",
        summary: diffSentence(claim.diff, "quran", where(claim)) || `النص المدخل يختلف عن النص القرآني المعتمد في Quranpedia (${where(claim)}).`,
        advice: "لا تنشره بهذه الصيغة القرآنية؛ راجع النص المعتمد في Quranpedia.",
      };
    case "NO_ORIGIN":
      if (claim.type_hint === "quran") {
        return {
          label: "لم يُعثر عليه في المصحف", hint: "المصحف كاملًا في Quranpedia", tone: "noorigin", icon: "؟",
          summary: "لم يُعثر على تطابق مطابق ولا على آية قريبة كفايةً في المصحف القرآني المعتمد من Quranpedia (6236 آية).",
          advice: "لا تنشره على أنه آية؛ راجع النص في Quranpedia.",
        };
      }
      return {
        label: "لم يُعثر عليه", hint: "ضمن قاعدة الأحاديث الحالية في المنصة", tone: "noorigin", icon: "؟",
        summary: claim.type_hint === "unknown"
          ? `${HADITH_NOT_FOUND_TEXT.slice(0, -1)}، ولا في المصحف القرآني المعتمد من Quranpedia.`
          : HADITH_NOT_FOUND_TEXT,
        note: HADITH_NOT_FOUND_NOTE,
        advice: `${HADITH_NOT_FOUND_ADVICE} ولا تنسب النص إلى النبي ﷺ قبل هذا التحقق.`,
      };
    case "NEEDS_REVIEW":
      if (isQuran) {
        return {
          label: "يحتاج إلى تحقق إضافي", hint: "نتيجة مشابهة وليست مطابقة", tone: "review", icon: "≈",
          summary: diffSentence(claim.diff, "quran", where(claim)) || `أقرب نص في المصحف المعتمد: ${where(claim)}؛ وليس تطابقًا مطابقًا.`,
          advice: "لا تنشره بهذه الصيغة على أنه آية؛ راجع النص المعتمد في Quranpedia.",
        };
      }
      if (src?.kind === "hadith") {
        return {
          label: "يحتاج إلى تحقق إضافي", hint: "نتيجة مشابهة وليست مطابقة", tone: "review", icon: "≈",
          summary: diffSentence(claim.diff, "hadith") || "لفظ النص المدخل لا يطابق لفظ الحديث المسجّل؛ الحكم المعروض يخص نص المصدر لا النص المدخل.",
          advice: "لا تنسبه إلى النبي ﷺ بهذه الصيغة قبل التحقق من الدرر السنية.",
        };
      }
      return {
        label: "يحتاج إلى تحقق إضافي", hint: "مطابقة غير كافية للحكم", tone: "review", icon: "≈",
        summary: "لم تكفِ المطابقة لإصدار نتيجة.", advice: "لم يُعثر عليه بيقين؛ يلزم التحقق الإضافي قبل النشر.",
      };
    case "REFER":
      return {
        label: "سؤال شخصي", hint: "يُحال إلى مختص", tone: "refer", icon: "↗",
        summary: "هذه حالة شخصية تحتاج إلى فتوى من مختص؛ لا يجيب عنها تثبّت.",
        advice: "اعرض سؤالك وسياقه على مختص مؤهل.",
      };
  }
}

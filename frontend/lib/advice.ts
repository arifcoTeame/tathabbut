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

/** One wording for every hadith card: the rulings come from Dorar, wherever the record was read. */
export const HADITH_NOT_FOUND_TEXT = "لم يُعثر على تطابق مطابق لهذا النص.";
export const HADITH_NOT_FOUND_NOTE =
  "عدم العثور لا يعني أن الحديث غير موجود، ولا يحكم عليه بالصحة أو الضعف؛ قد يكون بلفظ آخر.";
export const HADITH_NOT_FOUND_DIFF = "«لم يُعثر عليه» تختلف عن «حديث لا يصح» التي تعني أن له أحكامًا مسجّلة ترده.";
const CHAIN_NOTE = "وقد يخص بعض هذه الأحكام إسنادًا أو رواية بعينها.";
export const HADITH_NOT_FOUND_ADVICE = "للتأكد من وجود النص وحكمه، ابحث عنه كاملًا في موقع الدرر السنية.";
export const DORAR_SEARCH_LABEL = "البحث عن النص كاملًا في الدرر السنية";
export const SIMILAR_TEXT = "هذه نتيجة مشابهة وليست تطابقًا مطابقًا للنص المدخل.";

type GradeKind = "sahih" | "hasan" | "weak" | "fabricated" | "baseless" | "unverified";

/** Strongest recorded grade class, using only the grades copied from Dorar. */
const EXACT_GRADE_WORDS = ["باطل", "منكر", "ضعيف جداً", "ضعيف جدا"];

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
  const what = kind === "quran" ? "النص القرآني المعتمد في Quranpedia" : "لفظ الحديث في الدرر السنية";
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

/** Rulings from a live Dorar search: shown as found there, never as the platform's own grade. */
function liveOutcome(claim: Claim): Outcome | null {
  const src = claim.source;
  if (!src?.ref.live) return null;
  const pick = (cls: string[]) => claim.grades.filter((g) => cls.includes(g.class));
  switch (claim.verdict.code) {
    // Dorar's terms forbid deriving a ruling that is not stated: the badge says where the rulings
    // are from, and the rulings themselves are quoted as they are.
    case "VERIFIED":
      return {
        label: "وُجد في الدرر السنية", hint: "أحكام المحدّثين معروضة كما هي", tone: "verified", icon: "✓",
        summary: `حكمه في الدرر السنية: ${gradeLine(claim.grades)}.`,
        advice: "إذا نسبته إلى النبي ﷺ فاذكر حكم المحدّث ومصدره كما في الدرر السنية.",
      };
    case "NOT_AUTHENTIC":
      return {
        label: "وُجد في الدرر السنية", hint: "أحكام المحدّثين معروضة كما هي", tone: "fabricated", icon: "!",
        summary: `حكمه في الدرر السنية: ${gradeLine(pick(["fabricated", "baseless", "weak"]))}.`,
        advice: "اقرأ أحكام المحدّثين المعروضة قبل نسبته إلى النبي ﷺ أو نشره على أنه حديث.",
      };
    case "DISPUTED":
      return {
        label: "تعددت أحكام المحدّثين", hint: "قد تخص روايات وأسانيد مختلفة", tone: "disputed", icon: "⇄",
        summary: `له في الدرر السنية أحكام مختلفة: ${gradeLine([...pick(["authentic"]).slice(0, 1), ...pick(["fabricated", "baseless", "weak"]).slice(0, 1)])}.`,
        advice: "راجع الأحكام كاملة في الدرر السنية، ولا تنشره بصيغة الجزم بصحته قبل ذلك.",
        note: CHAIN_NOTE,
      };
    case "IN_SOURCE":
      return {
        label: "وُجد في الدرر السنية", hint: "أحكامه معروضة للمراجعة", tone: "review", icon: "≈",
        summary: "وُجد في الدرر السنية، وأحكامه معروضة أدناه للمراجعة.",
        advice: "اقرأ أحكام المحدّثين في الدرر السنية قبل نسبته إلى النبي ﷺ.",
        note: CHAIN_NOTE,
      };
    case "NEEDS_REVIEW":
      return {
        label: "يحتاج إلى تحقق إضافي", hint: "نتيجة مشابهة وليست مطابقة", tone: "review", icon: "≈",
        summary: diffSentence(claim.diff, "hadith") || "لفظ النص المدخل لا يطابق لفظ الحديث في الدرر السنية؛ الحكم المعروض يخص نص المصدر لا النص المدخل.",
        advice: "لا تنسبه إلى النبي ﷺ بهذه الصيغة قبل التحقق من الدرر السنية.",
      };
  }
  return null;
}

export function outcome(claim: Claim): Outcome {
  const live = liveOutcome(claim);
  if (live) return live;
  const src = claim.source;
  const isQuran = src?.kind === "quran";
  const attributedToProphet = claim.type_hint === "hadith";
  const dorar = "لا تنسب النص إلى النبي ﷺ ولا تنشره على أنه حديث صحيح قبل التحقق من الدرر السنية.";

  // «أعطني حديثاً يثبت هذا الكلام»: nothing to compare, and nothing is produced.
  if (claim.request === "evidence_ref") {
    const what = claim.type_hint === "quran" ? "آيةً تثبت" : "حديثاً يثبت";
    return {
      label: "لا يُنشئ أدلة", hint: "لا يوجد نص منسوب للتحقق منه", tone: "refer", icon: "✕",
      summary: `طلبتَ ${what} كلاماً دون ذكر نص منسوب. تثبّت لا ينشئ أحاديث ولا آيات ولا يأتي بأدلة من عنده، ولا يوجد في الطلب نص يمكن مقارنته بالمصادر؛ فلا دليل مطابق يُعرض.`,
      advice: "لا تنسب إلى النبي ﷺ ولا إلى القرآن الكريم ما لم يثبت. إن كان لديك حديث أو آية منسوبة فالصق نصها كاملاً للتحقق منه، وللسؤال الشرعي ارجع إلى مختص.",
    };
  }

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
        summary: `حكمه في الدرر السنية: ${gradeLine(claim.grades)}.`,
        advice: "يمكن نشره منسوبًا إلى النبي ﷺ مع ذكر مصدره وحكمه كما في الدرر السنية.",
      };
    }
    case "NOT_AUTHENTIC": {
      const kind = gradeKind(claim.grades) ?? "unverified";
      const g = GRADE_LABEL[kind];
      // Several rulings that all reject the hadith (e.g. «ضعيف» and «موضوع») are not a dispute.
      const classes = new Set(claim.grades.map((x) => x.class));
      const mixed = claim.grades.length > 1 && classes.size > 1;
      // A short grade word recorded by the muhaddith («باطل»، «منكر»…) is shown as written, not as its class.
      const words = new Set(claim.grades.map((x) => x.grade.trim()));
      const exact = !mixed && words.size === 1 ? EXACT_GRADE_WORDS.find((w) => words.has(w)) : undefined;
      const word = mixed ? "لا يصح بحسب كل الأحكام المسجّلة له في الدرر السنية"
        : `${exact ?? (kind === "weak" ? "ضعيف" : kind === "fabricated" ? "موضوع" : kind === "baseless" ? "لا أصل له" : "لا يصح مرفوعًا")} بحسب الدرر السنية`;
      return {
        label: mixed ? "حديث لا يصح" : exact ? `حديث ${exact}` : g.label,
        hint: mixed ? "كل أحكامه المسجّلة لا تصححه" : "حكم مسجّل في الدرر السنية",
        tone: g.tone, icon: g.icon,
        summary: mixed
          ? `له أكثر من حكم في الدرر السنية، وكلها لا تصححه (وليس هذا اختلافًا في صحته): ${gradeLine(claim.grades)}.`
          : `حكمه في الدرر السنية: ${gradeLine(claim.grades)}.`,
        advice: `الحديث ${word}، فلا يُنشر على أنه حديث صحيح ولا يُنسب إلى النبي ﷺ.`,
        note: "هذا حكم مسجّل على الحديث في الدرر السنية، وليس مجرد عدم عثور عليه.",
      };
    }
    case "DISPUTED":
      return {
        label: "اختلف المحدّثون في حكمه", hint: "بحسب الدرر السنية", tone: "disputed", icon: "⇄",
        summary: `له في الدرر السنية أحكام مختلفة: ${gradeLine(claim.grades)}.`,
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
      if (claim.live?.searched && claim.live.ok) {
        return {
          label: "لم يُعثر عليه", hint: "في الدرر السنية بهذا اللفظ", tone: "noorigin", icon: "؟",
          summary: claim.type_hint === "unknown"
            ? "لم يُعثر عليه في الدرر السنية بهذا اللفظ، ولا في المصحف القرآني المعتمد من Quranpedia."
            : "لم يُعثر عليه في الدرر السنية بهذا اللفظ.",
          note: `${HADITH_NOT_FOUND_NOTE} ${HADITH_NOT_FOUND_DIFF}`,
          advice: "ابحث عنه بلفظ آخر في موقع الدرر السنية، ولا تنسب النص إلى النبي ﷺ قبل هذا التحقق.",
        };
      }
      return {
        label: "لم يُعثر عليه", hint: claim.live?.searched ? "تعذّر البحث في الدرر السنية الآن" : "لا يعني الحكم بالصحة أو الضعف", tone: "noorigin", icon: "؟",
        summary: claim.type_hint === "unknown"
          ? `${HADITH_NOT_FOUND_TEXT.slice(0, -1)}، ولا في المصحف القرآني المعتمد من Quranpedia.`
          : HADITH_NOT_FOUND_TEXT,
        note: claim.live?.searched
          ? `تعذّر البحث في الدرر السنية الآن؛ أعد المحاولة بعد قليل. ${HADITH_NOT_FOUND_NOTE}`
          : `${HADITH_NOT_FOUND_NOTE} ${HADITH_NOT_FOUND_DIFF}`,
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
    case "OUT_OF_SCOPE":
      return {
        label: "سؤال عام", hint: "خارج نطاق التحقق", tone: "refer", icon: "?",
        summary: "هذا سؤال عام وليس آيةً أو حديثاً منقولاً؛ تثبّت يتحقق من النصوص المنسوبة إلى القرآن الكريم والسنة النبوية، ولا يجيب عن الأسئلة العامة ولا يصدر فتوى.",
        advice: "الصق الآية أو الحديث الذي تريد التحقق منه، مثل: «قال رسول الله ﷺ: الدين النصيحة» أو «ما صحة حديث اطلبوا العلم ولو بالصين؟». وللأسئلة العامة في العقيدة والتعريف بالإسلام ارجع إلى مختص أو إلى الموسوعة العقدية في الدرر السنية.",
      };
    case "IN_SOURCE":
      return {
        label: "وُجد في الدرر السنية", hint: "أحكامه معروضة للمراجعة", tone: "review", icon: "≈",
        summary: "وُجد في الدرر السنية؛ أحكامه معروضة كما هي.", advice: "اقرأ أحكام المحدّثين في الدرر السنية قبل نسبته إلى النبي ﷺ.",
      };
    case "REFER":
      return {
        label: "سؤال شخصي", hint: "يُحال إلى مختص", tone: "refer", icon: "↗",
        summary: "هذه حالة شخصية تحتاج إلى فتوى من مختص؛ لا يجيب عنها تثبّت.",
        advice: "اعرض سؤالك وسياقه على مختص مؤهل.",
      };
  }
}

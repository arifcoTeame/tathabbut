import type { DiffOp } from "@/lib/types";

/** Word-level diff between the quoted claim and the approved source text. */
export default function DiffView({ ops, sourceKind }: { ops: DiffOp[]; sourceKind?: "quran" | "hadith" }) {
  const isHadith = sourceKind === "hadith";
  return (
    <>
      <p className="diff" aria-label="الفروق بين النص المنقول والنص المعتمد">
        {ops.map((op, i) => {
          switch (op.op) {
            case "equal":
              return <span key={i} className="eq">{op.text} </span>;
            case "added":
              return (
                <span key={i}>
                  <del className="add" title={isHadith ? "لفظ في النص المدخل" : "زيادة ليست في المصدر"}>{op.claim}</del>{" "}
                </span>
              );
            case "missing":
              return (
                <span key={i}>
                  <ins className="miss" title={isHadith ? "لفظ في نص المصدر" : "ناقص من النص المنقول"}>{op.source}</ins>{" "}
                </span>
              );
            case "changed":
              return (
                <span key={i}>
                  <del className="add" title={isHadith ? "لفظ في النص المدخل" : "كلمة مستبدلة"}>{op.claim}</del>
                  <span className="arrow" aria-hidden>←</span>
                  <ins className="miss" title={isHadith ? "اللفظ في المصدر" : "الصواب في المصدر"}>{op.source}</ins>{" "}
                </span>
              );
          }
        })}
      </p>
      <div className="legend">
        <span><del className="add">مشطوب</del>{isHadith ? "اللفظ المدخل المختلف" : "ليس في المصدر"}</span>
        <span><ins className="miss">مظلّل</ins>{isHadith ? "اللفظ في المصدر" : "الصواب في المصدر"}</span>
      </div>
    </>
  );
}

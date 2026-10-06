> **وثيقة تاريخية:** خطوات رفع الإصدار 0.6.0، محفوظة لتتبّع مسار التطوير؛ أرقامها ومسمياتها قد تخالف الإصدار الحالي. **الحالي:** [دليل المحكّم](JUDGES_GUIDE.md) و[التحقق من الإصدار](VALIDATION.md).

# خطوات الرفع والنشر والتحقق — الإصدار 0.6.0

كل خطوة لها فحص يثبت أنها وقعت. لا تنتقل إلى التالية قبل نجاح الفحص. الوقت التقديري الكلي: 40–60 دقيقة بلا الفيديو.

## 1) رفع الكود إلى GitHub (10 دقائق)
1. فك ضغط `tathabbut-v0.6.0-source.zip` في مجلد مؤقت.
2. افتح https://github.com/arifcoTeame/tathabbut ← **Add file ← Upload files**.
3. اسحب **محتويات** المجلد (المجلدات `backend`، `data`، `docs`، `frontend`، `scripts`، `LICENSES` والملفات `README.md`، `LICENSE`، `CREDITS.md`، `SOURCES.md`، `THIRD_PARTY.md`، `submission.json`، `.gitignore`) إلى صفحة الرفع. GitHub يستبدل الملفات بالمسار نفسه ويضيف الجديدة؛ شجرة 0.6.0 تحتوي كل ملفات النسخة السابقة، فلا تبقى ملفات قديمة متعارضة.
4. رسالة الالتزام: `release 0.6.0: 72 hadith records, disputed verdict, 137 tests, evaluation evidence` ← **Commit changes** على `main`.
5. **الفحص:** افتح `https://github.com/arifcoTeame/tathabbut/blob/main/backend/app/core/pipeline.py` وتأكد أن `ENGINE_VERSION = "0.6.0"`، وأن `docs/INTERNAL_EVALUATION_2026-10-04.md` موجود.
6. **Releases ← Draft a new release** ← Tag `v0.6.0` على `main` ← العنوان `v0.6.0 — challenge submission` ← Publish.
7. **Settings ← General**: تأكد أن المستودع **Public**. وفي **About** (الصفحة الرئيسية ← ⚙): الوصف «أداة عربية للتحقق من الاقتباسات القرآنية والحديثية قبل النشر» والموقع `https://tathabbut.vercel.app`.

## 2) إعادة نشر المحرك على Render (10–15 دقيقة)
1. لوحة Render ← الخدمة `tathabbut-api` ← **Manual Deploy ← Deploy latest commit** (حتى لو كان Auto-Deploy مفعلاً).
2. انتظر حالة **Live** (البناء 3–6 دقائق).
3. **الفحص:** افتح `https://tathabbut-api.onrender.com/health` ← يجب أن يظهر `"engine_version": "0.6.0"`؛ ثم `https://tathabbut-api.onrender.com/index/stats` ← `"hadith": 72` و`"quran": 6236`.

## 3) إعادة نشر الواجهة على Vercel (5 دقائق)
1. Vercel يعيد النشر تلقائياً عند الالتزام على `main`. إن لم يحدث: المشروع ← **Deployments ← ⋯ ← Redeploy**.
2. **الفحص:** افتح `https://tathabbut.vercel.app/api/stats` ← `"hadith": 72`. ثم افتح الصفحة الرئيسية وجرّب «حديث اختلف فيه المحدّثون» ← يجب أن تظهر النتيجة **خلافي** بحكمي الألباني والذهبي. والتذييل يبدأ بـ «تثبّت أداة برمجية آلية…».

## 4) فحص الحالات الـ25 على الرابط الحي (5 دقائق) — أرسل لي الناتج
من مجلد `backend` بعد `bash setup.sh`:
```bash
.venv/bin/python scripts/evaluate_release.py --base-url https://tathabbut.vercel.app --frontend --repeat 3 --output ../docs/evidence/live-after-v0.6.0.json
```
المتوقع في السطر الأخير: `"passed": 75, "total": 75, "failed": []`. أرسل لي ملف `live-after-v0.6.0.json` (أو الصق آخر 5 أسطر) لأضيفه إلى الأدلة والوثائق، أو ارفعه إلى `docs/evidence/` في GitHub.

## 5) مقابلة النص القرآني بالموسوعة القرآنية (5 دقائق، اختياري لكنه يغلق بنداً مفتوحاً)
1. نزّل من https://quranpedia.net/dumps الملف `mushafs-1.json.gz` (394 KB).
2. من `backend`:
```bash
.venv/bin/python scripts/compare_quranpedia.py ~/Downloads/mushafs-1.json.gz --expected-sha256 fdfdfd8a01fbe9136309f53d300e4b1d1f358d06c5d1111804d819c906f41034 --output ../docs/evidence/quranpedia-compare.json
```
3. أرسل لي الناتج (الملخص المطبوع). إن ظهرت فروق فلا تعدّل البيانات؛ أراجعها معك.

## 6) تسجيل الفيديو ورفعه (30–45 دقيقة)
اتبع `docs/VIDEO_SCRIPT.md` على الرابط الحي بعد الخطوة 3. YouTube ← **غير مُدرج** ← انسخ الرابط ← افتحه من نافذة خاصة للتأكد أنه يعمل دون تسجيل دخول. المدة ≤ 2:00.

## 7) نموذج المنصة (5 دقائق)
النصوص في `docs/SUBMISSION_FORM.md`. ارفع `تثبت - العرض الرسمي.pptx` (3.8 MB). الصق رابط الفيديو والمستودع والرابط الحي. **حفظ وإرسال** ← احفظ لقطة شاشة من رسالة التأكيد. الموعد النهائي: الثلاثاء 6 أكتوبر 23:59 بتوقيت الرياض. عند عطل في المنصة: راسل info@IslamicAIch.org بدليل المحاولة ورقم المشاركة.

## 8) الفحص من جهاز أو حساب مختلف (5 دقائق)
من هاتف ببيانات الجوال أو من متصفح خاص بلا تسجيل دخول: افتح الرابط الحي وجرّب مثالاً، وافتح المستودع وملف README، وافتح الفيديو. سجّل الوقت ونتيجة الفحص وأرسلها لي.

## اختبار مصغّر مع مستخدمين (اختياري، 30 دقيقة، يرفع معيارين)
3–5 أشخاص من الفئة (معرّف/صانع محتوى) يجرّب كل منهم 5 نصوص من الأمثلة، ويسجَّل في `docs/evidence/user-study-template.csv`: الزمن، هل فهم النتيجة، هل كان القرار صحيحاً، أي ملاحظة. دون أسماء أو بيانات شخصية. أرسل لي الملف لأوثقه.

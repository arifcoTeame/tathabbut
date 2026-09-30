# تثبّت — الواجهة (Next.js)

واجهة عربية (RTL) تعرض «بطاقة تثبّت» لكل ادعاء: الحكم، والنص المعتمد، والمصدر
ورابطه، وأحكام المحدّثين، والفروق كلمة بكلمة، والمواضع البديلة، والشرح المولَّد
موسوماً ومفصولاً عن النص الشرعي.

## التشغيل المحلي

يتطلب Node.js 20.9 أو أحدث، وأن يكون محرّك التحقق (backend) يعمل على المنفذ 8000.

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

عنوان المحرّك يُضبط بالمتغير `TATHABBUT_API_URL` (الافتراضي `http://localhost:8000`).
المتصفح لا يتصل بالمحرّك مباشرة: الطلبات تمر عبر `app/api/verify` في الخادم.

## البنية

```
app/
  layout.tsx          RTL + خط Readex Pro (مضمَّن محلياً)
  page.tsx
  api/verify/route.ts وسيط إلى POST /verify
  api/stats/route.ts  وسيط إلى GET /index/stats
components/
  Verifier.tsx        الإدخال، الأمثلة، ملخص الأحكام، حالة المحرّك
  ClaimCard.tsx       بطاقة الادعاء
  DiffView.tsx        الفروق كلمة بكلمة
lib/
  types.ts            مطابق لـ backend/app/schemas.py
  verdicts.ts         تسميات الأحكام والمستويات وألوانها
```

## النشر على Vercel

Root Directory = `frontend`، وأضف متغير البيئة `TATHABBUT_API_URL` برابط المحرّك المنشور.

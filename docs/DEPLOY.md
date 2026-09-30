# النشر (Live Demo) — مجاني بالكامل

| الجزء | المنصة | الخطة |
|---|---|---|
| المحرك (FastAPI) | Render — Web Service (Docker) | Free: 512 MB RAM، والمحرك يستهلك نحو 260 MB مع المصحف كاملاً |
| الواجهة (Next.js) | Vercel | Hobby |

> تشترط Hugging Face اشتراك PRO لأي Space من نوع Docker أو Gradio، فلم تعد خياراً مجانياً.
> لذلك تعمل النسخة الحية بالتضمين الخفيف `tfidf-char`.
> ويبقى BGE-M3 متاحاً بإضافة `--build-arg EMBEDDER=bge-m3` على أي خادم فيه 3 GB من الذاكرة أو أكثر.

## 1) المحرك على Render
1. من New ← Web Service ← Public Git Repository أدخل الرابط `https://github.com/arifcoTeame/tathabbut`.
2. الإعدادات:
   - Language: **Docker**
   - Branch: `main`
   - Region: Frankfurt
   - Instance: **Free**
   - Dockerfile Path: `backend/Dockerfile`
   - Docker Build Context Directory: `.`
   - Health Check Path: `/health`
3. البناء يأخذ قرابة 3 إلى 5 دقائق. للتحقق افتح `https://<service>.onrender.com/index/stats`، ويجب أن يظهر `"quran_complete": true`.

نص المصحف مضمَّن في `data/quran/quran_full.json` من Tanzil، فلا يعتمد البناء على تنزيله.

## 2) الواجهة على Vercel
1. من Add New ← Project استورد `arifcoTeame/tathabbut`.
2. اجعل Root Directory = `frontend`.
3. أضف متغير البيئة `TATHABBUT_API_URL=https://<service>.onrender.com` بدون `/` في آخره.
4. اضغط Deploy.

## ملاحظات
- خدمة Render المجانية تنام بعد 15 دقيقة بلا طلبات، وتستيقظ في نحو 30 إلى 60 ثانية.
  - الواجهة توقظها تلقائياً عند الفتح وتعرض «المحرك يستيقظ…».
  - للإبقاء عليها مستيقظة: مراقب مجاني على UptimeRobot (HTTP(s)، كل 5 دقائق) يطلب `/health`.
  - `/health` و`/` يقبلان GET وHEAD، لأن أدوات المراقبة تفحص بـ HEAD.
  - `.github/workflows/keepalive.yml` احتياط إضافي، لكن مواعيد GitHub المجدولة قد تتأخر أو تُتخطى.
- إذا لم يُعِد Render البناء بعد الرفع إلى GitHub، فاستخدم Manual Deploy ← Deploy latest commit.
- عنوان المحرك لا يصل إلى المتصفح، لأن الواجهة تمرّ عبر `/api/verify` على خادم Vercel.

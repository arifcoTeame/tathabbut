import type { Metadata, Viewport } from "next";
import "@fontsource/readex-pro/400.css";
import "@fontsource/readex-pro/600.css";
import "@fontsource/readex-pro/700.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "تثبّت | محرّك التحقق المُسنَد للمحتوى الإسلامي",
  description:
    "قارن نصوص الآيات وعينة من الأحاديث بالمصادر المفهرسة، وراجع دليل المطابقة والفروق وحدود النتيجة قبل النشر.",
};

export const viewport: Viewport = { themeColor: "#12183F" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ar" dir="rtl">
      <body>{children}</body>
    </html>
  );
}

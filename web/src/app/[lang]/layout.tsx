import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Noto_Sans_JP, Geist_Mono } from "next/font/google";
import "../globals.css";
import Header from "@/components/Header";
import { LOCALES, hasLocale } from "@/i18n/config";
import { getDictionary } from "@/i18n";
import { LocaleProvider } from "@/i18n/LocaleProvider";

const notoSansJP = Noto_Sans_JP({
  variable: "--font-noto-sans-jp",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

// The root layout sits under [lang] (Next.js i18n routing): every page is
// /ja/... or /en/..., and src/proxy.ts redirects locale-less paths.
export function generateStaticParams() {
  return LOCALES.map((lang) => ({ lang }));
}

export async function generateMetadata({ params }: LayoutProps<"/[lang]">): Promise<Metadata> {
  const { lang } = await params;
  if (!hasLocale(lang)) return {};
  return {
    title: "PV Triage Assistant",
    description: getDictionary(lang).meta.description,
  };
}

export default async function RootLayout({ children, params }: LayoutProps<"/[lang]">) {
  const { lang } = await params;
  if (!hasLocale(lang)) notFound();

  return (
    <html
      lang={lang}
      className={`${notoSansJP.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-bg text-text">
        <LocaleProvider locale={lang}>
          <Header />
          <main className="flex-1">{children}</main>
        </LocaleProvider>
      </body>
    </html>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LOCALES, LOCALE_COOKIE, switchLocalePath } from "@/i18n/config";
import { useDict, useLocale, useLocalePath } from "@/i18n/LocaleProvider";

const TABS = [
  { path: "/triage", key: "triage" },
  { path: "/rag", key: "rag" },
  { path: "/samples", key: "samples" },
  { path: "/about", key: "about" },
] as const;

// Remember an explicit choice, so a later locale-less link (e.g. "/") keeps it
// instead of falling back to the browser language. One year; not sensitive.
function rememberLocale(l: string) {
  document.cookie = `${LOCALE_COOKIE}=${l}; path=/; max-age=31536000; samesite=lax`;
}

export default function Header() {
  const pathname = usePathname();
  const t = useDict();
  const locale = useLocale();
  const to = useLocalePath();

  return (
    <header className="sticky top-0 z-10 border-b border-border bg-surface/85 backdrop-blur">
      {/* Phone: brand + language on row 1, the tabs on a row of their own that
          scrolls sideways. From sm up: one row, as before. */}
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-1 px-4 py-2 sm:h-14 sm:flex-nowrap sm:px-6 sm:py-0">
        <Link href={to("/")} className="font-bold tracking-tight text-ink">
          PV&nbsp;Triage&nbsp;Assistant
        </Link>
        <nav className="order-last -mx-1 flex w-full items-center gap-1 overflow-x-auto whitespace-nowrap text-sm [scrollbar-width:none] sm:order-none sm:mx-0 sm:w-auto">
          {TABS.map((tab) => {
            const href = to(tab.path);
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={tab.path}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`rounded-md px-3 py-1.5 transition-colors ${
                  active
                    ? "bg-accent-weak font-medium text-accent"
                    : "text-muted hover:text-ink"
                }`}
              >
                {t.nav[tab.key]}
              </Link>
            );
          })}
        </nav>

        <div
          role="group"
          aria-label={t.nav.languageLabel}
          className="ml-auto inline-flex shrink-0 rounded-lg border border-border bg-surface-2 p-0.5"
        >
          {LOCALES.map((l) => (
            <Link
              key={l}
              href={switchLocalePath(pathname, l)}
              onClick={() => rememberLocale(l)}
              aria-current={l === locale ? "true" : undefined}
              className={`rounded-md px-2.5 py-1 font-mono text-xs transition-colors ${
                l === locale
                  ? "bg-surface font-medium text-accent shadow-sm"
                  : "text-muted hover:text-ink"
              }`}
            >
              {l === "ja" ? "日本語" : "EN"}
            </Link>
          ))}
        </div>
      </div>
    </header>
  );
}

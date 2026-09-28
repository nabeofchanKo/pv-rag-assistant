import { NextResponse, type NextRequest } from "next/server";
import { LOCALE_COOKIE, hasLocale, negotiateLocale } from "@/i18n/config";

// Every page lives under /ja/... or /en/... . A path without a locale is
// redirected to one: the reader's explicit earlier choice (cookie) if any,
// otherwise their browser language — so an English-speaking reader who opens a
// bare link lands on English, and a link to /en/... is always English.
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (hasLocale(pathname.split("/")[1])) return;

  const saved = request.cookies.get(LOCALE_COOKIE)?.value;
  const locale = hasLocale(saved)
    ? saved
    : negotiateLocale(request.headers.get("accept-language"));

  const url = request.nextUrl.clone();
  url.pathname = `/${locale}${pathname === "/" ? "" : pathname}`;
  return NextResponse.redirect(url);
}

export const config = {
  // Pages only: not the BFF (/api), Next internals, or files in public/
  // (anything with an extension, e.g. /samples/case_001.txt, /favicon.ico).
  matcher: ["/((?!api|_next|.*\\..*).*)"],
};

"use client";

import { createContext, useContext, type ReactNode } from "react";
import type { Locale } from "./config";
import { getDictionary, type Dictionary } from "./index";

// The locale comes from the URL (/ja/... or /en/...), read once by the root
// layout and provided here, so any client component can get the strings with
// useDict() instead of threading `lang` through every prop.

const LocaleContext = createContext<Locale>("ja");

export function LocaleProvider({ locale, children }: { locale: Locale; children: ReactNode }) {
  return <LocaleContext.Provider value={locale}>{children}</LocaleContext.Provider>;
}

export function useLocale(): Locale {
  return useContext(LocaleContext);
}

export function useDict(): Dictionary {
  return getDictionary(useContext(LocaleContext));
}

/**
 * Display an API value (重篤, 否定できない, ...) in the current language. The
 * value itself never changes — only how it is shown. Unknown values (a model
 * answer outside the known list) are shown as-is rather than hidden.
 */
export function useTerm(): (value: string | null | undefined) => string {
  const values: Record<string, string | undefined> = useDict().vocab.values;
  return (value) => (value ? (values[value] ?? value) : "");
}

/** "/triage" → "/en/triage" for the current locale. */
export function useLocalePath(): (path: string) => string {
  const locale = useContext(LocaleContext);
  return (path) => `/${locale}${path === "/" ? "" : path}`;
}

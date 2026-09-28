// Supported UI languages. Pure data + helpers, importable from the proxy,
// server components and client components alike.
//
// Scope, deliberately: the UI is bilingual; the case material and the model's
// free-text rationales stay in Japanese (the pipeline, the reference data and
// the evaluation are all Japanese — see README, "Language").

export const LOCALES = ["ja", "en"] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "ja";

/** Cookie remembering an explicit choice made with the header toggle. */
export const LOCALE_COOKIE = "lang";

export function hasLocale(v: string | undefined | null): v is Locale {
  return !!v && (LOCALES as readonly string[]).includes(v);
}

/**
 * Pick a locale from an Accept-Language header, e.g. "en-US,en;q=0.9,ja;q=0.8".
 * Ranks by q-value and takes the first supported primary tag. Small enough not
 * to warrant @formatjs/intl-localematcher + negotiator for two locales.
 */
export function negotiateLocale(acceptLanguage: string | null): Locale {
  if (!acceptLanguage) return DEFAULT_LOCALE;
  const ranked = acceptLanguage
    .split(",")
    .map((part, i) => {
      const [tag, ...params] = part.trim().split(";");
      const q = params.find((p) => p.trim().startsWith("q="));
      return { base: tag.trim().toLowerCase().split("-")[0], q: q ? Number(q.split("=")[1]) : 1, i };
    })
    .filter((x) => x.base && !Number.isNaN(x.q) && x.q > 0)
    .sort((a, b) => b.q - a.q || a.i - b.i);
  return ranked.map((x) => x.base).find(hasLocale) ?? DEFAULT_LOCALE;
}

/** Same path in another locale: "/ja/triage?x=1" → "/en/triage?x=1". */
export function switchLocalePath(pathname: string, to: Locale): string {
  const parts = pathname.split("/");
  if (hasLocale(parts[1])) parts[1] = to;
  else parts.splice(1, 0, to);
  return parts.join("/") || `/${to}`;
}

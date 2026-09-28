import { en } from "./dictionaries/en";
import { ja, type Dictionary } from "./dictionaries/ja";
import type { Locale } from "./config";

export type { Dictionary };

// Both dictionaries are plain TS modules (a few KB), so client components can
// import them directly and pick one by locale. The alternative — handing the
// chosen dictionary down from a server component — would not work here: some
// entries are functions, and functions cannot cross the server→client boundary.
const DICTIONARIES: Record<Locale, Dictionary> = { ja, en };

export function getDictionary(locale: Locale): Dictionary {
  return DICTIONARIES[locale];
}

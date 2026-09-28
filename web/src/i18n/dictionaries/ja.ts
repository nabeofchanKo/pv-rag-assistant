// Japanese UI strings — the source of truth for the dictionary's SHAPE.
// en.ts is typed as `Dictionary`, so a key added here and not translated there
// (or misspelled there) fails the type check instead of rendering `undefined`.
//
// Values are plain strings, or small functions where a value is interpolated.

export const ja = {
  meta: {
    description:
      "医薬品安全性監視（PV）のトリアージ・一次評価支援。すべての回答を出典に紐づけます。",
  },
  nav: {
    triage: "症例トリアージ",
    rag: "RAG Q&A",
    samples: "サンプル症例",
    about: "このプロジェクトについて",
    languageLabel: "表示言語",
  },
};

export type Dictionary = typeof ja;

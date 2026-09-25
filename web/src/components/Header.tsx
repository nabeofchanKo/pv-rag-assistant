"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/triage", label: "症例トリアージ", soon: false },
  { href: "/rag", label: "RAG Q&A", soon: false },
  { href: "/samples", label: "サンプル症例", soon: false },
];

export default function Header() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-10 border-b border-border bg-surface/85 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-5xl items-center gap-6 px-6">
        <Link href="/" className="font-bold tracking-tight text-ink">
          PV&nbsp;Triage&nbsp;Assistant
        </Link>
        <nav className="flex items-center gap-1 text-sm">
          {TABS.map((t) => {
            const active =
              pathname === t.href || pathname.startsWith(`${t.href}/`);
            return (
              <Link
                key={t.href}
                href={t.href}
                aria-current={active ? "page" : undefined}
                className={`rounded-md px-3 py-1.5 transition-colors ${
                  active
                    ? "bg-accent-weak font-medium text-accent"
                    : "text-muted hover:text-ink"
                }`}
              >
                {t.label}
                {t.soon && (
                  <span className="ml-1.5 rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-muted">
                    準備中
                  </span>
                )}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}

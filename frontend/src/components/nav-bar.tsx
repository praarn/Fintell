"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth-context";

const LINKS = [
  { href: "/transactions", label: "Transactions" },
  { href: "/spending", label: "Spending" },
  { href: "/ask", label: "Ask" },
  { href: "/anomalies", label: "Anomalies" },
  { href: "/accounts", label: "Accounts" },
  { href: "/upload", label: "Upload" },
  { href: "/admin", label: "Metrics" },
  { href: "/settings", label: "Settings" },
];

function BrandMark() {
  return (
    <span className="flex items-center gap-2">
      <span
        className="grid h-7 w-7 place-items-center rounded-lg text-[13px] font-bold text-white shadow-sm"
        style={{ backgroundImage: "linear-gradient(140deg, var(--brand) 0%, var(--accent) 100%)" }}
        aria-hidden
      >
        F
      </span>
      <span className="text-sm font-semibold tracking-tight text-content">Fintell</span>
    </span>
  );
}

export function NavBar() {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  if (!user) return null;

  return (
    <nav className="sticky top-0 z-40 border-b border-border bg-surface/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-2.5">
        <div className="flex items-center gap-1">
          <Link href="/transactions" className="mr-3 shrink-0">
            <BrandMark />
          </Link>
          <div className="flex items-center gap-0.5 overflow-x-auto">
            {LINKS.map((link) => {
              const active = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  aria-current={active ? "page" : undefined}
                  className={`rounded-lg px-2.5 py-1.5 text-sm whitespace-nowrap transition-colors ${
                    active
                      ? "bg-brand-soft font-semibold text-brand"
                      : "text-muted hover:bg-surface-2 hover:text-content"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <span className="hidden text-xs text-muted sm:inline">{user.email}</span>
          <button
            onClick={async () => {
              await logout();
              router.replace("/login");
            }}
            className="btn btn-ghost btn-sm"
          >
            Log out
          </button>
        </div>
      </div>
    </nav>
  );
}

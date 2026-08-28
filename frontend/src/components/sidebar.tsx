"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth-context";

type NavItem = { href: string; label: string };
type NavGroup = { title: string; items: NavItem[] };

const NAV: NavGroup[] = [
  {
    title: "Overview",
    items: [
      { href: "/dashboard", label: "Dashboard" },
      { href: "/transactions", label: "Transactions" },
      { href: "/spending", label: "Spending" },
    ],
  },
  {
    title: "Intelligence",
    items: [
      { href: "/ask", label: "Ask your finances" },
      { href: "/anomalies", label: "Anomalies" },
      { href: "/admin", label: "Metrics & cost" },
    ],
  },
  {
    title: "Manage",
    items: [
      { href: "/accounts", label: "Accounts" },
      { href: "/upload", label: "Upload" },
      { href: "/settings", label: "Settings" },
    ],
  },
];

const FLAT = NAV.flatMap((g) => g.items);

function BrandMark({ withWordmark = true }: { withWordmark?: boolean }) {
  return (
    <span className="flex items-center gap-2">
      <span
        className="grid h-7 w-7 place-items-center rounded-md text-[13px] font-bold text-white"
        style={{ backgroundColor: "var(--brand)" }}
        aria-hidden
      >
        F
      </span>
      {withWordmark && (
        <span className="text-[15px] font-semibold tracking-tight text-content">Fintell</span>
      )}
    </span>
  );
}

function useLogout() {
  const { logout } = useAuth();
  const router = useRouter();
  return async () => {
    await logout();
    router.replace("/login");
  };
}

export function Sidebar() {
  const { user } = useAuth();
  const pathname = usePathname();
  const doLogout = useLogout();

  if (!user) return null;

  return (
    <aside className="sidebar hidden lg:flex">
      <div className="flex h-14 items-center border-b border-border px-4">
        <Link href="/dashboard">
          <BrandMark />
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-2">
        {NAV.map((group) => (
          <div key={group.title}>
            <p className="sidebar-section">{group.title}</p>
            {group.items.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className="sidebar-link"
                >
                  <span className="sidebar-dot" aria-hidden />
                  {item.label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="border-t border-border p-3">
        <p className="truncate px-1 pb-2 text-xs text-muted" title={user.email}>
          {user.email}
        </p>
        <button onClick={doLogout} className="btn btn-ghost btn-sm w-full">
          Log out
        </button>
      </div>
    </aside>
  );
}

export function MobileTopBar() {
  const { user } = useAuth();
  const pathname = usePathname();
  const doLogout = useLogout();

  if (!user) return null;

  return (
    <header className="sticky top-0 z-40 flex flex-col gap-2 border-b border-border bg-surface/90 px-4 py-2.5 backdrop-blur-md lg:hidden">
      <div className="flex items-center justify-between">
        <Link href="/dashboard">
          <BrandMark />
        </Link>
        <button onClick={doLogout} className="btn btn-ghost btn-sm">
          Log out
        </button>
      </div>
      <div className="-mx-1 flex gap-1 overflow-x-auto overscroll-x-contain px-1 pb-0.5">
        {FLAT.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={`shrink-0 rounded-md px-3 py-2 text-sm whitespace-nowrap transition-colors ${
                active
                  ? "bg-brand-soft font-semibold text-brand"
                  : "text-secondary hover:bg-surface-2 hover:text-content"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </div>
    </header>
  );
}

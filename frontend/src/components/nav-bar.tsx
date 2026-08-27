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

export function NavBar() {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  if (!user) return null;

  return (
    <nav className="flex items-center justify-between border-b border-black/[.08] bg-white px-6 py-3 dark:border-white/[.145] dark:bg-black">
      <div className="flex items-center gap-6">
        <span className="text-sm font-semibold tracking-tight">Fintell</span>
        {LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={`text-sm ${
              pathname === link.href
                ? "font-medium text-black dark:text-white"
                : "text-zinc-500 hover:text-black dark:text-zinc-400 dark:hover:text-white"
            }`}
          >
            {link.label}
          </Link>
        ))}
      </div>
      <div className="flex items-center gap-3 text-sm text-zinc-500 dark:text-zinc-400">
        <span>{user.email}</span>
        <button
          onClick={async () => {
            await logout();
            router.replace("/login");
          }}
          className="rounded-full border border-black/[.08] px-3 py-1 hover:bg-black/[.04] dark:border-white/[.145] dark:hover:bg-white/[.08]"
        >
          Log out
        </button>
      </div>
    </nav>
  );
}

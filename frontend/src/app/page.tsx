"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/lib/auth-context";

export default function Home() {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;
    router.replace(user ? "/transactions" : "/login");
  }, [isLoading, user, router]);

  return (
    <div className="flex min-h-[60vh] items-center justify-center text-sm text-muted">Loading…</div>
  );
}

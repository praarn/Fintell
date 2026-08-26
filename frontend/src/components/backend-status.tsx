"use client";

import { useEffect, useState } from "react";

import { API_BASE_URL } from "@/lib/config";

type Status = "checking" | "ok" | "unreachable";

export function BackendStatus() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    let cancelled = false;

    fetch(`${API_BASE_URL}/health`)
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then(() => {
        if (!cancelled) setStatus("ok");
      })
      .catch(() => {
        if (!cancelled) setStatus("unreachable");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const label =
    status === "checking"
      ? "Checking backend..."
      : status === "ok"
        ? "Backend: healthy"
        : "Backend: unreachable";

  const color =
    status === "ok"
      ? "bg-green-500"
      : status === "unreachable"
        ? "bg-red-500"
        : "bg-zinc-400";

  return (
    <div className="flex items-center gap-2 rounded-full border border-black/[.08] px-4 py-2 text-sm text-zinc-700 dark:border-white/[.145] dark:text-zinc-300">
      <span className={`h-2 w-2 rounded-full ${color}`} />
      {label}
    </div>
  );
}

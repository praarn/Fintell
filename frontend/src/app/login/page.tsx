"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login(email, password);
      router.replace("/transactions");
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Login failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-[calc(100vh-1px)] items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <span
            className="mb-3 grid h-11 w-11 place-items-center rounded-lg text-lg font-bold text-white shadow-sm"
            style={{ backgroundColor: "var(--brand)" }}
            aria-hidden
          >
            F
          </span>
          <h1 className="page-title text-xl">Welcome back to Fintell</h1>
          <p className="mt-1 text-sm text-muted">Personal finance statement intelligence.</p>
        </div>

        <form onSubmit={handleSubmit} className="card card-pad space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-secondary">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-secondary">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input"
            />
          </div>
          {error && (
            <p className="rounded-lg bg-negative-soft px-3 py-2 text-sm text-negative">{error}</p>
          )}
          <button type="submit" disabled={isSubmitting} className="btn btn-primary w-full">
            {isSubmitting ? "Logging in…" : "Log in"}
          </button>
          <p className="text-center text-sm text-muted">
            No account?{" "}
            <Link href="/register" className="link">
              Register
            </Link>
          </p>
        </form>

        <p className="mt-4 text-center text-xs text-muted">
          Demo account: <span className="font-mono">demo@fintell.app</span> /{" "}
          <span className="font-mono">demo-password-123</span>
        </p>
        <p className="mt-2 text-center text-xs text-muted">
          New here?{" "}
          <Link href="/guide" className="link">
            Read the guide
          </Link>
        </p>
      </div>
    </div>
  );
}

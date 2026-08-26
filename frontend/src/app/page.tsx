import { BackendStatus } from "@/components/backend-status";

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-zinc-50 px-6 font-sans dark:bg-black">
      <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">
        Personal Finance Statement Intelligence
      </h1>
      <p className="max-w-md text-center text-sm text-zinc-600 dark:text-zinc-400">
        Phase 0 foundation. Backend, database, and CI are wired up; features
        land phase by phase.
      </p>
      <BackendStatus />
    </div>
  );
}

// `||` (not `??`) on purpose: an empty NEXT_PUBLIC_API_BASE_URL (the
// Docker build arg's default) should also fall back, not become "".
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

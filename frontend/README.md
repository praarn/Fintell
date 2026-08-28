# Fintell — frontend

Next.js 16 (App Router), TypeScript, Tailwind v4. A typed client over the
Fintell API.

```bash
cp .env.local.example .env.local     # NEXT_PUBLIC_API_BASE_URL
npm install
npm run dev                          # http://localhost:3000
```

Checks: `npx tsc --noEmit` · `npm run lint` · `npm run build`

See [`EXPLANATION.md`](./EXPLANATION.md) for the folder map, the root
[`IMPLEMENTATION.md`](../IMPLEMENTATION.md) §15 for the design rationale,
and [`../commands.md`](../commands.md) for every command including the
Docker path.

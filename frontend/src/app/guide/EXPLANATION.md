# frontend/src/app/guide/ — explanation

A static in-app walkthrough — five numbered steps (create account/demo →
upload → review/correct → explore spending → ask questions), each
linking to the relevant route via a small inline `NavRef` helper. Pure
presentation: no data fetching, no loading state.

## Notes

- **Works signed out.** Unlike every other route, `guide/` does not call
  `useRequireAuth()` — it's reachable from `/login`'s "Read the guide"
  link before a session exists, so a prospective user can see what the
  app does before creating an account.
- Mentions the demo account (`demo@fintell.app`) inline, seeded by
  `backend/scripts/seed_demo.py` — the guide and the seed script
  describe the same six-month synthetic history.
- Content here should stay in sync with whatever the actual route pages
  do; it's hand-written copy, not generated from the routes.

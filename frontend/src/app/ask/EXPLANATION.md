# frontend/src/app/ask/ — explanation

The "ask your finances" question box — the frontend for
`text_to_sql/service.answer_question` (root `IMPLEMENTATION.md` §11).

## Flow

- A text input + submit, plus six clickable example questions
  (`EXAMPLES`) that both fill the input and submit immediately.
- `submit()` calls `askQuestion`, shows the result via `<AnswerCard>`,
  and refreshes the recent-questions history regardless of outcome.
- `<AnswerCard>` branches on `answer.answered`: `false` renders the
  honest decline reason in a warning-styled card; `true` renders the
  plain-language summary, a results table (`columns`/`rows`), an
  optional `<ChartView>` (bar or line depending on `chart.kind`), and a
  footer naming the matched template + confidence.
- Recent questions (`getAskHistory`) are clickable too — clicking one
  re-asks it rather than just displaying the old answer, since the
  underlying data may have changed since it was first asked.

## Notes

- The page's own copy states the honesty guarantee: "the model never
  writes SQL, and it says so honestly when nothing fits" — matches the
  backend's template-registry design exactly, not just page copy.
- A declined history item shows "declined" instead of a template name
  (`item.declined ? "declined" : item.matched_template`), so the
  answered/declined distinction survives into the history list too.

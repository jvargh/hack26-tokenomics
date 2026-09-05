# Working agreements for this repo

## Validate fast, then stop

Cheapest signal first. Stop at the first level that proves the change.

| Change | Validation | Cost |
| --- | --- | --- |
| CSS / layout / colour | One `screenshotPage` of the changed element only (`selector`), or nothing if the rule is unambiguous | seconds |
| React logic | `npx tsc --noEmit` | ~10 s |
| Server logic | `python -m compileall -q tokenos_api` then one targeted request | ~5 s |
| Event stream / phases | `tests\test_workflows_live.py` with pacing disabled | ~2 s |
| Before declaring done | `npm run build` | ~15 s |

Do **not** re-run the whole suite after a change that cannot affect it. A CSS edit does not
need the backend workflow tests. A backend edit does not need a screenshot.

## Fast test mode

Presentation pacing adds ~7 s per run. Turn it off for automated checks:

```powershell
$env:TOKENOS_PHASE_PACING_MS = "0"
$env:TOKENOS_OPERATION_PACING_MS = "0"
$env:TOKENOS_STEP_PACING_MS = "0"
python -m uvicorn tokenos_api.main:app --host 127.0.0.1 --port 8000
```

All four workflows then complete in well under a second combined.

## Browser checks

- Prefer `screenshotPage` with a `selector` over a full-page capture.
- Prefer one Playwright block that asserts and returns a small object over several
  round trips. Return short values, not page dumps.
- Do not snapshot to confirm something the code plainly guarantees.

## Product rules that must not regress

- No browser timer produces a phase, cost, token, quality, or savings value. Every one comes
  from a server event.
- Pacing is presentation only and is subtracted from measured work time.
- Never show a number the server did not produce. If something is unavailable, say so.
- Avoided cost appears only with a valid measured baseline.

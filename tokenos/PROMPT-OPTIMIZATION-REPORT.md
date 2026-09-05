# TokenOS prompt + workflow optimization — implementation report

Implements
[5-TOKENOS-PROMPT-AND-WORKFLOW-OPTIMIZATION-IMPLEMENTATION.md](../5-TOKENOS-PROMPT-AND-WORKFLOW-OPTIMIZATION-IMPLEMENTATION.md).

The fourth workflow now optimizes either a single prompt or a recurring workflow,
through the same seven phases and the same claim-strength rules.

## Latest follow-up: workflow examples in both modes

The two workflow modes now receive the same complete-default treatment as prompt
examples. **Use a measured example** automatically selects the first available
fixture and fills the current-workflow description, desired outcome, quality
requirements, goal, recurring volume, latency, budget, and token/escalation limits.
Each of the four fixtures has a distinct description and outcome. Selecting another
fixture replaces all defaults, and mode changes clear incompatible prompt input.
Catalogs arriving after sample-source selection initialize the form once, without
overwriting subsequent user edits.

The previously exposed Analyze/sample path also works end to end. It analyzes
bundled representative requests locally, clearly explains that historical provider
telemetry is absent, leaves current model cost unknown, and never claims a verified
outcome or saving. Uploaded telemetry analysis retains its existing validation.

Actual validation of this follow-up:

| Check | Result |
| --- | --- |
| `npm run typecheck`; `npm run build` | Passed |
| Optimization and prompt API/unit test files | **110 passed** in 33.38s |
| `e2e_workflow_examples.py` | **11 passed** in 52.53s |
| Additional delayed-catalog regression | **1 passed** in 7.55s |
| Existing workflow, prompt, and visual browser suites | **46 passed** in 93.72s |
| Running application | Analyze and Measure both auto-select one example, fill description/outcome, and enable planning without edits |

Coverage includes all four examples in both modes, entering the sample source
without clicking an individual fixture, switching after edits, both default
paths through proof, and asynchronous catalog loading without overwriting later
edits. The delayed-catalog test also handles React development-mode double
effects. The development API was reloaded after validation.

Changed: workflow fixture catalog and analysis validation, shared frontend
default decoding/selection, `test_optimization_api.py`, new browser
`tests/browser/e2e_workflow_examples.py`, API documentation, and walkthroughs.

Captures:
[Analyze defaults](samples/screenshots/prompt/workflow-defaults-analyze.png) ·
[Measure defaults](samples/screenshots/prompt/workflow-defaults-measure.png)

## Follow-up: complete prompt-example defaults

Both **Verbose support reply with stale history** and **Repeated policy lookup
with irrelevant excerpts** now populate every example-specific input and execution
limit. This includes the previously missing system instructions, conversation
history and expected result, as well as model/format, quality requirements, goal,
recurring volume, latency and budget. Bundled context filenames are displayed.

Selecting either example on a fresh form enables **Build prompt optimization plan**
without editing another field. Switching examples resets the complete set of
defaults rather than mixing values from the previous example. Loading defaults
does not authorize or execute a model.

Latest focused validation for this follow-up:

| Check | Actual result |
| --- | --- |
| `npm run typecheck` | Passed |
| `npm run build` | Passed; 58 modules |
| `pytest tests/test_prompt_api.py tests/test_prompt_unit.py -q` | **32 passed** in 15.01s |
| `pytest -c pytest-browser.ini tests/browser/e2e_prompt.py -q` | **19 passed** in 46.19s |
| User's running app | Both examples verified with instructions, history, expected result populated and the planning button enabled |

The API catalog, frontend decoder and selection handler were updated together.
Regression tests now submit each example without filling any field, verify submitted
defaults, check switching after edits, and ensure no authorization/execution endpoint
was called. The running development API was reloaded to serve the new defaults.

Captures:
[Verbose defaults](samples/screenshots/prompt/example-defaults-verbose_support_reply.png) ·
[Policy lookup defaults](samples/screenshots/prompt/example-defaults-repeated_policy_lookup.png)

## Resolved copy conflict

The request asked for the Step 1 title `Optimize AI work`. The specification gives
two different strings for that area, so this was confirmed before locking exact
copy into tests. **The user chose the specification verbatim**, so the shipped copy is:

- section heading `Optimize AI Prompt or Workflow`
- description `Start with a prompt or workflow. TokenOS reduces AI waste while preserving required quality and outcomes.`
- mode selector label `What do you want to improve?`

`Optimize AI work` is deliberately **not** used. The fourth primary card is
unchanged (`Optimize an existing AI workflow`), as are the first three cards and
all internal workflow IDs.

Note: the supplied description is 16 words, not 15. The exact string was used as given.

## What was delivered

- Three conditional modes inside the existing fourth workflow — `analyze_current_workflow`,
  `optimize_single_prompt` (default), `measure_optimized_workflow` — as a real
  radiogroup that swaps the work area and validates only that mode's fields.
- Prompt Describe: prompt entry, optional system instructions and conversation
  history, context attachments with name/role/size/SHA-256/type/estimated tokens,
  model selection, desired outcome, output format, quality requirements, execution
  limits, and a conditional `Expected result` field.
- Prompt Plan: prompt composition per component with estimated tokens, candidate
  treatment and reason, plus potential improvements. Everything labelled Estimated;
  the word "saving" is asserted absent from this screen.
- Prompt Optimize: current vs governed package side by side, `What TokenOS changed
  and why`, `Copy governed prompt` (no spend), `Continue to safeguards`. There is no
  "Apply optimized prompt" affordance.
- Protect: plain-language safeguards and `Authorize protected prompt run`. No model
  call is possible before it; `/execute` returns 409 until authorization succeeds.
- Run: SSE across the seven phases with polling only as recovery.
- Verify / Prove: outcome first, route explanation, measured economics, collapsed
  technical evidence with raw JSON download.
- Estimated / Measured / Projected / Verified saving remain visibly distinct, and
  `Verified saving` still requires a completed matched baseline that passed the same
  gates and cost more.
- Reporting dimensions for prompt vs workflow runs, context minimization, cache use,
  routing, cost per accepted outcome, quality, escalation and verified savings.

## Actual test results

Every number below is from a real run, not an estimate.

| Check | Command | Result |
| --- | --- | --- |
| Typecheck | `npm run typecheck` | **passed** |
| Build | `npm run build` | **passed** — 58 modules, JS 315.44 kB (gzip 91.25 kB) |
| Unit + API | `.\.venv\Scripts\python.exe -m pytest -q` | **158 passed** in 132.07s |
| Browser (all) | `python -m pytest -c pytest-browser.ini -q` | **44 passed** in 92.45s |

The 44 browser tests are 17 workflow, 17 prompt and 10 visual-regression tests.
The 158 include the 128 that existed before this change, so no prior behaviour
regressed.

Visual regression is **layout-geometry based**, not pixel diffing: it asserts card
wrapping at four viewports, equal card heights, absence of clipping and horizontal
overflow, dynamic field appearance/disappearance, and the mode switch. This stays
valid across machines, fonts and DPI.

No test spends live model tokens. Positive provider paths use explicit in-test
doubles; there is no simulated production mode.

## Bugs found and fixed during integration

These were found by the tests, not assumed:

1. **Context minimizer stripped required grounding.** Exact term matching treated
   "return window" and "Returns are accepted within 30 days." as unrelated, so the
   only relevant excerpt was minimized away — which broke grounded citations and
   forced a model call for a question that was locally provable. Fixed with light
   deterministic stemming plus a rule that an excerpt whose retrieval key is named
   by the request is always retained.
2. **Alias field rejected valid requests.** The UI sends both `testInputIds` and the
   spec's `representativeInputIds`; the server concatenated them and reported a
   duplicate artifact. Fixed to union the aliases while still rejecting a genuine
   repeat within either field or a file reused across roles.
3. **Prompt examples were unusable.** The catalog omitted the prompt text, so
   selecting an example left the form empty. The endpoint now returns the real
   prompt, system instructions, history, desired outcome, model and output format.
4. **Browser suites could not run together.** Session fixtures imported across test
   modules re-entered `sync_playwright` inside a running loop. Fixtures moved to
   `tests/browser/conftest.py`, and the default run now ignores `tests/browser` so
   that conftest cannot shadow the API tests' `from conftest import run_workflow`.

Your reported "Prompt examples are unavailable" was a **stale server**, not a code
defect: the API on port 8000 and the Vite dev server were both running pre-feature
code. Both were restarted, and the live app was then verified with Playwright —
3 mode radios, prompt mode default, 2 examples, no unavailable message, and the
prompt/desired-outcome fields populated from the selected example.

## Files changed

### Frontend — `apps/web/src/optimization/`
`OptimizationDescribe.tsx`, `OptimizationJourney.tsx`, `OptimizationViews.tsx`,
`client.ts`, `types.ts`, `optimization.css`

### Backend — `services/tokenos-api/tokenos_api/optimization/`
`prompts.py` (new), `schemas.py`, `engine.py`, `quality.py`, `fixtures.py`,
`imports.py`, `router.py`

### Tests — `services/tokenos-api/`
`tests/test_prompt_unit.py` (new), `tests/test_prompt_api.py` (new),
`tests/browser/e2e_prompt.py` (new), `tests/browser/e2e_visual.py` (new),
`tests/browser/conftest.py` (promoted from `harness.py`),
`tests/browser/e2e_optimization.py`, `pytest.ini`

### Docs and fixtures
`samples/PROMPT-OPTIMIZATION-WALKTHROUGH.md` (new), `samples/README.md`,
`services/tokenos-api/OPTIMIZATION-API.md`, this report, and prompt-phase
screenshots under `samples/screenshots/prompt/`.

## Commands

```powershell
# API
Set-Location tokenos\services\tokenos-api
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
$env:TOKENOS_MODEL_MODE = "local"
.\.venv\Scripts\python.exe -m uvicorn tokenos_api.app:app --host 127.0.0.1 --port 8000

# UI
Set-Location tokenos\apps\web
npm ci
npm run dev            # http://localhost:5173
```

```powershell
# Validation
Set-Location tokenos\apps\web
npm run typecheck
npm run build

Set-Location tokenos\services\tokenos-api
.\.venv\Scripts\python.exe -m compileall -q tokenos_api
.\.venv\Scripts\python.exe -m pytest -q
$env:TOKENOS_BROWSER_CHANNEL = "msedge"
.\.venv\Scripts\python.exe -m pytest -c pytest-browser.ini -q
```

Browser suites start their own API and Vite servers on random loopback ports with
temporary storage, so a running demo is untouched. Set `TOKENOS_SCREENSHOT_DIR` to
capture screenshots. On Windows the installed Edge channel is used; elsewhere set
`TOKENOS_BROWSER_CHANNEL` or install Chromium.

**If the UI reports a feature as unavailable, restart both servers** — a dev server
started before a change keeps serving the old build.

## Foundry configuration

Server-side only. No credential is ever accepted from, or returned to, the browser.

```powershell
az login
$env:TOKENOS_MODEL_MODE = "foundry"
$env:TOKENOS_FOUNDRY_BASE_URL = "https://<resource>.openai.azure.com/openai/v1/"
$env:TOKENOS_FOUNDRY_AUTH_MODE = "entra"
$env:TOKENOS_FOUNDRY_EFFICIENT_DEPLOYMENT = "<efficient-deployment>"
$env:TOKENOS_FOUNDRY_ADVANCED_DEPLOYMENT  = "<advanced-deployment>"
$env:TOKENOS_FOUNDRY_BASELINE_DEPLOYMENT  = "<baseline-deployment>"
```

The signed-in identity needs a data-plane role such as **Cognitive Services OpenAI
User** on the resource. Then populate `price_table.json` from
[optimization-price-table.example.json](services/tokenos-api/optimization-price-table.example.json)
with your real agreed rates and an explicit `version`. Measured cost is computed
with Decimal arithmetic from provider-reported usage against that pinned table.
Without configured deployments or prices, prompts that need a model block with an
actionable message; nothing is fabricated.

Full contract: [OPTIMIZATION-API.md](services/tokenos-api/OPTIMIZATION-API.md).

## Known limitations and deferred items

- **No live paid run was exercised.** Foundry was not configured in this
  environment, so measured provider usage, measured cost and a verified saving were
  validated through the contract and in-test doubles, never against a live model.
- **Prompt token counts are estimates.** They are deterministic and clearly labelled
  Estimated; they are not provider-exact tokenizer counts.
- **Estimated reduction is floored at zero.** A short prompt with little context can
  legitimately grow once a strict output contract is added. The API reports zero
  rather than inventing a gain, and exposes both token figures so the direction is
  visible — but it does not surface a signed "increase" figure.
- **Deterministic local routing is deliberately narrow.** A prompt routes locally
  only when exactly one eligible context excerpt's retrieval key is named by the
  request and it carries a decision plus citations. Everything else needs a model.
- **`same_answer_quality` needs an expected result** and `required_tests` is
  unsupported for a prompt; both block at Protect rather than auto-passing.
- **Event names deviate from the spec.** The spec lists snake_case
  (`phase_started`); the shipped stream keeps the existing dotted names
  (`phase.started`) plus new `prompt.analyzed` and `context.decided`, to avoid
  breaking the shipped UI and tests.
- **Visual regression is geometry-based, not pixel-based**, by design.
- **Single-tenant local service.** Tenant identity comes from server configuration;
  put an authenticated boundary in front of the API before exposing it.
- Context relevance uses stemmed term overlap and exact keyed retrieval, not
  embeddings; semantic reuse remains conservative exact matching.

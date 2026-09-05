# Sample data provenance

Sample inputs are generated deterministically by
[`tokenos_api/samples.py`](../services/tokenos-api/tokenos_api/samples.py) and then pushed through
the **same** upload validation, extraction, and hashing pipeline as user files. Nothing about the
analysis, routing, measurement, or proof is pre-computed.

| Workflow | Bundled input | Deliberate content |
| --- | --- | --- |
| Review documents against rules | 5 supplier invoices, 1 duplicate invoice, 2 purchase orders, 1 purchasing policy | One charge above the $500 line limit, one freight charge above the $150 limit, one duplicate document, one unapproved charge |
| Test a code change | Small Python widget API as a ZIP, plus its OpenAPI document | One route declared in the specification but not implemented, one failing unit test |
| Process records by a deadline | 10,000-row support-record CSV and a category rule file | Stable category mix, ~40 ambiguous records, ~11 malformed rows |
| Optimize an existing AI workflow | Four representative workflow fixtures | Reusable assistance context, a genuine policy exception, failed-test diagnosis, and classification with ambiguous cases |

Because the engine really processes them, results are labelled **Measured sample run**. They are
never presented as customer-measured savings.

## Prompt optimization

The fourth workflow also optimizes a single prompt. See the
[prompt walkthrough](PROMPT-OPTIMIZATION-WALKTHROUGH.md).

| Prompt example | Deliberate content |
| --- | --- |
| `repeated_policy_lookup` | Verbose request, stale conversation history, and several context artifacts of which only one carries the keyed answer. Resolves by deterministic retrieval with zero model calls. |
| `verbose_support_reply` | Verbose request whose answer genuinely needs interpretation, so it blocks safely when no model is configured. |

`GET /api/optimization/prompt-examples` returns the actual prompt text, desired
outcome and bundled context for each, so selecting an example fills the form with a
real, runnable prompt rather than an empty placeholder.

## Existing workflow optimization

Follow the [evaluator walkthrough](OPTIMIZATION-WALKTHROUGH.md) to exercise all seven
phases, including upload and connected-application alternatives. Each fixture goes
through actual local parsing, routing, and outcome verification; no fixture contains
a precomputed governed-run success or fabricated provider response.

Any imported example usage is explicitly sample telemetry. Cached-token eligibility
does not imply that a provider served cached tokens. Recurring-volume economics are
labelled **Projected** and cannot create a saving.

The 200-run route-history fixture for the legacy `false_savings` API remains available
for compatibility and economics regression tests. It is not a fifth primary workflow.

### Upload fixtures

- [Representative FAQ requests](optimization-requests.json): three synthetic inputs,
  independent expected outputs, source sections, and explicit reuse scope/freshness.
  Upload under **Representative test inputs** or paste the array. Actual local
  execution should pass with zero model calls. For an explicitly sample-badged run,
  use the measured-example selector rather than importing this file as customer work.
- [Normalized telemetry CSV template](normalized-telemetry-template.csv): replace the
  identifiers and fill only provider-reported measurements. Empty measurements stay
  unknown. This file contains no claimed usage or model cost.
- The UI's **Download normalized import template** action returns the server's
  documented JSON shape and instructions, including supported native TokenOS exports.

### Updated phase screenshots

[Describe](screenshots/optimization/01-describe.png) ·
[Connected input](screenshots/optimization/01-connected.png) ·
[Plan](screenshots/optimization/02-plan.png) ·
[Optimize](screenshots/optimization/03-optimize.png) ·
[Protect](screenshots/optimization/04-protect.png) ·
[Run](screenshots/optimization/05-run.png) ·
[Verify](screenshots/optimization/06-verify.png) ·
[Prove](screenshots/optimization/07-prove.png) ·
[History](screenshots/optimization/08-history.png)

These are captures of real local test execution, not design mockups.

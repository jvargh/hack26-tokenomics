# TokenOS demo script — Tokenomics: The Zero-Waste AI Challenge

**Runtime:** ~3 minutes 30 seconds
**Format:** screen recording with voice-over
**Recording:** `tests/browser/demo_recording.py` produces the silent screen capture and a
per-scene timing file; narrate over it using the cues below.

---

## Before you record

1. Start the API in local mode and the web app (see [the README](../README.md)).
2. Confirm `GET /health` reports `"modelMode": "local"` — the demo must not spend
   live tokens.
3. Reset to a clean state: **New run**, and dark mode selected.

Everything shown is produced by the running application. No slide is a mockup, and
no number is typed by hand.

---

## The one-sentence pitch

> Most AI cost tools count tokens after the fact. TokenOS decides whether the model
> was needed at all — and then proves the answer was still correct.

---

## Scene 1 — The problem (0:00–0:25)

**On screen:** the TokenOS home screen, four workflow cards.

> When AI costs rise, the instinct is to cap it. But every cap quietly taxes the
> work we're trying to deliver.
>
> TokenOS takes a different position. Instead of limiting what AI can spend, it
> asks a sharper question on every single step: *does this actually need a model?*
>
> Because most of the time, it doesn't.

**Cue:** hover across the four workflows without clicking.

---

## Scene 2 — Bring real work (0:25–0:50)

**On screen:** select **Process records by a deadline** → **Use sample data**.

> Let's give it real work. This is a support-record backlog with a due time — the
> kind of routine, high-volume job teams now pipe straight into a model.
>
> These files go to the local TokenOS service and are parsed and validated there.
> Nothing is pre-computed — the engine genuinely reads every record.

**Cue:** click **Load sample data**, let the file manifest appear, then click
**Analyze with TokenOS**.

---

## Scene 3 — The seven phases (0:50–1:20)

**On screen:** the run advancing through the stepper.

> TokenOS runs seven phases. It plans the work, chooses the cheapest route that can
> still be verified, pins a safety contract, executes, and then checks its own
> answer.
>
> Watch the route choice. Parsing records, validating the schema, applying the
> category rules, checking the deadline — that's ordinary software. Deterministic,
> auditable, and zero tokens.
>
> A model is only reached when the rules genuinely can't settle something.

**Cue:** let it run to Prove on its own. Do not click through.

---

## Scene 4 — The proof (1:20–2:10)

**On screen:** the Prove screen, top section.

> Here's the result, and this is the part that matters.
>
> **"Your work is done, and it never needed AI."** Six of six steps completed
> without a model. Every record settled by rules that can be checked.
>
> Now look at the cards. If a model had done every step, this run would have cost
> **three dollars fifty-nine**. It cost **zero**.

**Cue:** point at the four cards in turn.

> But notice the wording. It says **estimate**, in amber. Nothing extra has been
> spent yet, so TokenOS calculates that comparison from this run's real token
> counts — and it refuses to call an estimate a saving.
>
> And the last card is the one most cost tools skip entirely: *is the answer still
> correct?* Yes — all six checks passed against the source material.

---

## Scene 5 — Proving it (2:10–2:45)

**On screen:** the all-AI comparison section.

> To turn that estimate into proof, TokenOS re-runs the identical work the all-AI
> way and measures both.
>
> That costs real money, so it sits behind an explicit acknowledgement. TokenOS
> will not spend your tokens to make its own numbers look good.
>
> When both paths finish, the comparison only counts if they used the same inputs,
> the same output contract, the same quality checks and the same price table — and
> both passed. Only then does the amber estimate become a green **verified saving**.

**Cue:** show the acknowledgement checkbox and the disabled button. Do not run it.

---

## Scene 6 — Refusing to lie (2:45–3:10)

**On screen:** start a new run → **Test a code change** → sample data → Prove.

> Here's what I think makes this credible.
>
> This code-change run has a genuinely failing test. TokenOS finished it, measured
> it — and then hid every cost comparison.
>
> No saving. No avoided cost. Just: the answer didn't pass its checks.
>
> A cheaper wrong answer is not a saving. If a tool won't say that, you can't trust
> its good numbers either.

---

## Scene 7 — Close (3:10–3:30)

**On screen:** the fourth workflow, prompt mode.

> The same governance works on a single prompt — trimming context, choosing a
> route, and proving the outcome before you spend anything.
>
> That's TokenOS. Not a token cap. A control layer that finds the cheapest route
> that still produces a verified result — and refuses to claim a saving it hasn't
> earned.

---

## Recording the video

```powershell
Set-Location tokenos\services\tokenos-api
$env:TOKENOS_DEMO_DIR = "<absolute output directory>"
.\.venv\Scripts\python.exe -m pytest -c pytest-browser.ini tests\browser\demo_recording.py -q -s
```

Produces, in that directory:

| File | What it is |
| --- | --- |
| `tokenos-demo.webm` | Silent 1600×900 screen capture, ~3 min 35 s |
| `demo-timings.json` | Start/end seconds per scene, for aligning narration |
| `scene-*.png` | One still per scene, for thumbnails or slides |

The recording drives its own isolated local-mode servers, so it never touches a
running demo and never spends model tokens. It also **asserts** that the screen
actually shows what this script claims — a before/after comparison with an amber
estimate in Scene 4, and no cost comparison at all in Scene 6. If the product
stops matching the narration, the recording fails rather than producing a video
that oversells.

### Adding the voice-over

The capture is deliberately silent. `tools/narrate_demo.py` generates the narration
and muxes it:

```powershell
python tools\narrate_demo.py --check          # does the narration fit? writes nothing
python tools\narrate_demo.py --timings-only   # emit scene lengths for re-recording
python tools\narrate_demo.py                  # generate audio and produce the MP4
python tools\narrate_demo.py --voice David    # Zira, David or Mark
```

Output lands beside the capture:

| File | What it is |
| --- | --- |
| `tokenos-demo-narrated.mp4` | H.264 + AAC, plays anywhere |
| `narration.m4a` | The assembled voice track on its own |
| `narration/*.wav` | One clip per scene |

**Why per-scene audio, not one long track.** Each scene is on screen for a fixed
number of seconds. A single continuous narration drifts a little further out of
sync with every scene. The tool synthesises one clip per scene and places it at
that scene's exact start offset from `demo-timings.json`, so the words stay on the
right frames.

**Keeping picture and narration in step.** Run `--check` first. If a scene's
narration is longer than its window, the tool refuses to build and tells you. The
better fix is to re-pace the picture rather than trim the words:

```powershell
python tools\narrate_demo.py --timings-only   # prints a SCENE_SECONDS block
# paste it into tests/browser/demo_recording.py, then re-record, then narrate
```

The tool will not speed audio up to force a fit; that always sounds rushed.

**Voice quality.** The Windows synthesiser needs no installation and is fine for a
working cut. For the final submission, either record yourself or use a neural voice,
then drop the per-scene files into `narration/` as `<scene>.wav` and re-run the
tool — it reuses whatever is already there.

### Doing it by hand

If you would rather assemble it yourself, the same two steps are:

```powershell
# 1. one narration track, each clip delayed to its scene start
ffmpeg -i 01.wav -i 02.wav -filter_complex `
  "[0:a]adelay=600|600[a0];[1:a]adelay=26700|26700[a1];[a0][a1]amix=inputs=2:normalize=0[out]" `
  -map "[out]" -c:a aac -b:a 192k narration.m4a

# 2. mux onto the capture, re-encoding to H.264 for compatibility
ffmpeg -i tokenos-demo.webm -i narration.m4a `
  -c:v libx264 -crf 20 -pix_fmt yuv420p -c:a aac -b:a 192k -shortest out.mp4
```

`normalize=0` on `amix` matters: without it ffmpeg divides the level by the number
of inputs and the narration comes out very quiet.

---

## Delivery notes

- **Pace:** slower than feels natural. The numbers need a beat to land.
- **Emphasise:** "seven of eight", "estimate", "verified saving", "a cheaper wrong
  answer is not a saving".
- **Do not say** "saved" anywhere before Scene 5. The product doesn't, and the
  script shouldn't either.
- If asked about live model runs: the demo is local-only, so measured provider
  usage and a verified saving require configured Foundry deployments and prices.

## Claim strength cheat-sheet

Keep these distinct when speaking; the UI already does.

| Say this | Only when |
| --- | --- |
| "Estimate" | Nothing extra spent; computed from this run's real token counts |
| "Measured" | Actual provider usage priced against the pinned table |
| "Projected" | A measured unit cost multiplied by a volume the user entered |
| "Verified saving" | Both paths completed, passed identical checks, baseline cost more |

## Questions you should expect

**"Is the 'if every step used AI' number a strawman?"**
It's a ceiling, and it's labelled as one. It uses this run's actual token counts
repriced as if every step had gone to a model. When a customer supplies real
telemetry, TokenOS prefers that as the comparison instead.

**"What if the model is unavailable?"**
It blocks with the missing configuration named. It never invents usage, cost or a
passing outcome.

**"Is zero model tokens the same as free?"**
No, and the UI says so on the card. Local work still consumes compute, storage and
review time.

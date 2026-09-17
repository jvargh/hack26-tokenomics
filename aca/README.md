# TokenOS judge demonstration on Azure Container Apps

A hosted build of the TokenOS application that walks the full product journey
**without calling any model provider**. Judges can open a URL and run the real
workflows; every AI route is answered by an authored simulator, so the
demonstration costs nothing in model spend.

**Live URL:** https://tokenos-hack26.yellowwater-54592620.eastus.azurecontainerapps.io

No sign-in is required.

---

## What is real and what is simulated

This distinction is the point of the product, so the demonstration keeps it
visible rather than blurring it.

| Part of a run | In this demonstration |
|---|---|
| File upload, parsing, hashing | **Real** |
| Duplicate detection, policy lookup, arithmetic | **Real** |
| Schema validation, secret scanning, test execution | **Real** |
| Routing decisions and budget authorisation | **Real** |
| Quality gates and verification checks | **Real** |
| Cost calculation from the pinned price table | **Real arithmetic** on simulated usage |
| **The model response itself** | **Simulated** |

The simulator does not invent results out of nothing. It answers from the
caller's own payload, so a citation refers to a real policy rule in the supplied
document and a classification uses a category that genuinely appears in the
records. The application's unmodified quality gates then check that output for
real. A simulated answer that cannot satisfy a real gate fails it honestly.

---

## Judge walkthrough

1. **Open the URL.** The orange banner at the top states that AI calls are
   simulated. It is driven by the mode the server reports, not a build flag, so
   it cannot disagree with what the API is doing.

2. **Choose a workflow.** Any of the four works. *Review documents against
   rules* is the clearest first run.

3. **Select "Sample" as the input source** and choose **Load example inputs**.
   This is required: the simulator answers the bundled examples only.

4. **Run it.** Watch the seven phases. The Plan and Optimize phases are entirely
   local: no model is involved even in a real deployment.

5. **Authorise the run** at the Protect phase. Nothing executes until you do.

6. **Read the Prove screen.** Note which operations completed without
   generative AI, why the one model call was permitted, and what it cost.

7. **Open Reports.** Runs appear under *Sample* rather than *Measured*, because
   simulated evidence must never aggregate as production spend.

8. **Try something unsupported.** Enter a custom instruction instead of loading
   an example. The run is refused with an explanation rather than answered with
   invented text.

---

## Configuration

| Variable | Value here | Purpose |
|---|---|---|
| `TOKENOS_MODEL_MODE` | `simulated` | Selects the authored simulator. `local` and `foundry` are unchanged. An unrecognised value stops startup rather than being guessed at. |
| `TOKENOS_STORAGE_ROOT` | `/data/tokenos` | Run history, proofs and uploads. |
| `TOKENOS_WEB_DIST_ROOT` | `/app/services/tokenos-api/static` | Built web assets served by the API. |
| `TOKENOS_CORS_ORIGINS` | the app's own URL | Same-origin deployment. |
| `TOKENOS_FOUNDRY_*` | **removed** | The judge build carries no provider endpoint. |

Three independent things must all be true for a model call to happen, and none
of them is true here:

1. `TOKENOS_MODEL_MODE` would have to be `foundry`. It is `simulated`, and
   simulated is checked first, so there is no fallback path to real inference.
2. A Foundry endpoint would have to be configured. The variables are removed.
3. The `openai` and `azure-identity` packages would have to be installed. They
   are **deliberately absent from the image**, so a provider client cannot be
   constructed even by mistake.

The app identity holds **`AcrPull` only**. Its `Cognitive Services OpenAI User`
role was removed as part of this deployment.

---

## Deploying and updating

```powershell
cd aca
.\deploy.ps1          # build, roll out, verify
```

The script discloses the subscription, resource group, region, resource names
and estimated cost, then asks for confirmation before anything billable happens.
Pass `-Yes` to skip the prompt on a repeat run.

**Update behaviour.** `deploy.ps1` builds a new image and points the existing
Container App at it by digest. The app runs in single-revision mode, so the old
revision is replaced rather than run alongside. Expect roughly 30 to 60 seconds
where the previous replica is draining and the new one is starting.

**Rollback.**

```powershell
.\rollback.ps1        # restores the pre-demonstration real-model image
```

Rollback restores the image and mode. It prints, but does not run, the commands
to restore the Foundry endpoint variables and the model-inference role, so
re-enabling real spend is always a deliberate act.

---

## Limitations

These are stated plainly because a demonstration that hides its own boundaries
is not much of a demonstration.

- **Saved runs do not survive container replacement.** Data is written to the
  replica's ephemeral disk. A restart, scale event or new deployment loses every
  saved run. This was an explicit trade-off to avoid provisioning a storage
  account; attaching an Azure Files share at `/data/tokenos` is the single
  change that would fix it, at roughly $0.06/month.

- **Session isolation scopes what is shown, not what is stored.** Each visitor
  gets an opaque cookie and sees only their own run history. All runs still live
  in one store on the server, and reporting aggregates across all of them. It is
  a demonstration convenience, not a security boundary.

- **The simulator understands the bundled examples only.** Custom prompts and
  uploaded documents are refused. This is deliberate: answering them would mean
  inventing text and pretending to understand instructions.

- **Single replica.** The store is file-backed SQLite, and concurrent writers
  corrupt it. `maxReplicas` is 1 for correctness, so the demonstration will not
  scale under heavy concurrent load.

- **Simulated figures are not measured evidence.** Token counts are computed
  from the text actually produced, and costs are real arithmetic against the
  pinned price table, but no provider reported them. Every artifact carries
  `origin=simulated` and `sim-` prefixed identifiers so a downloaded proof
  states its own provenance.

---

## Cleanup

The demonstration reuses existing infrastructure and creates no new billable
resources, so there is nothing to delete. To stop paying for the app entirely:

```powershell
# Stop the app (keeps configuration, stops compute charges)
az rest --method post --url "https://management.azure.com/subscriptions/463a82d4-1896-4332-aeeb-618ee5a5aa93/resourceGroups/azrgda6pvyru4svsw/providers/Microsoft.App/containerApps/tokenos-hack26/stop?api-version=2025-01-01"

# Remove the demonstration image tags
az acr repository untag -n azacrda6pvyru4svsw --image tokenos/tokenos-tokenos-hack26:sim-session
```

The managed environment continues to charge its hourly management fee while it
exists, whether or not the app is running.

---

## Files

| File | Purpose |
|---|---|
| `Dockerfile` | Judge image. Omits the provider SDK on purpose. |
| `.dockerignore` | Allowlist. See the note inside about when it applies. |
| `main.bicep` | Declarative form of the deployed configuration. |
| `deploy.ps1` | Build, roll out, verify. |
| `rollback.ps1` | Restore the real-model image. |
| `verify_deployed.py` | Browser verification of the judge journey. |

The simulator itself lives with the application, not here:
`tokenos/services/tokenos-api/tokenos_api/simulator.py`, with tests in
`tokenos/services/tokenos-api/tests/test_simulated_mode.py`.

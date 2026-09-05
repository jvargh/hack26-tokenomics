---
name: innovation-studio-catalog
description: Extract or refresh complete Microsoft Innovation Studio hackathon project listings into a verified Markdown catalog with one local image per project. Use this skill whenever a user provides an innovation-studio.microsoft.com submissions/projects URL and asks to browse, export, catalog, scrape, summarize, archive, refresh, or update the results, especially when authentication or device-compliance requires an external Edge window.
compatibility: Windows, Microsoft Edge, Node.js 20 or newer, npm, and network access to Innovation Studio.
---

# Innovation Studio Catalog

Create a reproducible Markdown catalog from an authenticated Innovation Studio project-listing URL. The bundled scripts handle browser authentication, result discovery, API extraction, image downloads, resumable progress, Markdown safety, and stale-image cleanup.

## Required workflow

1. Ask the user for any missing choices before starting:
   - Listing URL.
   - Output Markdown path.
   - Whether to refresh in place or create a timestamped copy.
   - Image policy if they did not specify one. Recommend one local project image per listing.
2. Keep authentication in an external Microsoft Edge window when device compliance blocks an embedded browser.
3. Launch Edge with [scripts/launch-edge.ps1](scripts/launch-edge.ps1).
4. Ask the user to finish sign-in and leave the results page visible.
5. Run [scripts/extract.js](scripts/extract.js).
6. Verify the reported submission count, unique project links, image links, missing files, and Markdown fence balance.
7. Report the output file, image folder, number of projects, and number of projects that had an available image.

Do not copy cookies, tokens, request headers, email addresses, or internal user identifiers into outputs. The extractor observes authenticated requests only inside the user's local Edge session and keeps resumable state beside the output.

## One-time dependency setup

Run this only when `node_modules/playwright-core` is missing:

```powershell
npm install --prefix "<skill-directory>"
```

Do not install a bundled Chromium browser. The workflow intentionally controls the installed Microsoft Edge browser.

## Launch external Edge

```powershell
powershell -ExecutionPolicy Bypass -File "<skill-directory>\scripts\launch-edge.ps1" `
  -Url "<innovation-studio-listing-url>"
```

The launcher prints the Edge process ID, CDP endpoint, and profile location. By default it uses `http://127.0.0.1:9222` and a dedicated profile under the user's Copilot directory.

If port 9222 is already serving the dedicated Edge session, reuse it rather than launching another window.

## Extract or refresh

```powershell
node "<skill-directory>\scripts\extract.js" `
  --url "<innovation-studio-listing-url>" `
  --output "<absolute-output-md-path>"
```

Optional arguments:

```text
--images <directory>       Local image directory. Default: <output-base>-images
--state <file>             Resumable state file. Default: .<output-base>-state.json
--cdp <url>                Edge CDP endpoint. Default: http://127.0.0.1:9222
--keep-old-images          Do not remove stale files recorded in the prior image manifest
--help                     Show command help
```

The extractor:

- Determines the event and expected result count from the rendered listing and authenticated API traffic.
- Clicks **Load more** until every result is present.
- Preserves listing order.
- Fetches full project records through the same authenticated browser context.
- Maps custom fields to the live form labels.
- Excludes member email addresses and internal IDs.
- Downloads at most one primary project image per listing.
- Removes authenticated inline content-image references from imported descriptions so Markdown never contains broken `/api/...` image links.
- Repairs unbalanced fenced code blocks from user-authored descriptions.
- Checkpoints after each project and resumes an interrupted run.
- Starts a fresh refresh after a completed run so project changes are not hidden by an old checkpoint.
- Removes only stale files listed in the previous generated image manifest.

## Update behavior

For an in-place refresh, use the same `--output` and `--images` paths. A completed prior state is treated as history, not as a cache: every current project is fetched again. If a run is interrupted, rerun the same command to resume.

Do not delete the state file during an interrupted run. It is what makes the run resumable.

## Verification

The extractor performs verification before it exits successfully. Also inspect the summary:

```text
Projects: N
Unique project links: N
Local images: M
Missing linked images: 0
Non-local image references: 0
Unclosed code fence: false
```

An image count lower than the project count is valid when projects did not provide a primary image.

If the Markdown preview is blank or malformed, run the extractor again. The renderer balances fenced code blocks at each imported field boundary, preventing one project description from swallowing the rest of the document.

## Troubleshooting

### "Checking your access" or "Authentication required"

Confirm the external Edge window is signed in and the filtered listing shows its result count. Do not navigate directly to project pages as a workaround. The site can route direct project navigation incorrectly; the extractor uses the authenticated listing APIs.

### CDP connection refused

Run the Edge launcher, or use the printed endpoint with `--cdp`.

### Result count stops early

Leave the listing tab open and rerun. The extractor fails rather than silently producing a partial catalog.

### Broken description images

Only generated local image paths should remain in the catalog. Authenticated content images embedded in descriptions are intentionally removed to preserve the one-image-per-project policy.

## Tests

Run the deterministic regression tests:

```powershell
npm test --prefix "<skill-directory>"
```

Tests do not access Innovation Studio or require authentication.

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright-core");
const {
  createFieldLabels,
  renderMarkdown,
  sanitizeProject,
  slugify,
  syncStaleImages,
  verifyCatalog,
} = require("./lib/catalog");

const ORIGIN = "https://innovation-studio.microsoft.com";

function printHelp() {
  console.log(`Usage:
  node scripts/extract.js --url <listing-url> --output <catalog.md> [options]

Options:
  --images <directory>       Image directory (default: <output-base>-images)
  --state <file>             Resumable state file (default: .<output-base>-state.json)
  --cdp <url>                Edge CDP endpoint (default: http://127.0.0.1:9222)
  --keep-old-images          Keep stale files from the previous generated manifest
  --help                     Show this help`);
}

function parseArguments(argv) {
  const options = {
    cdp: "http://127.0.0.1:9222",
    keepOldImages: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--help") {
      options.help = true;
    } else if (argument === "--keep-old-images") {
      options.keepOldImages = true;
    } else if (["--url", "--output", "--images", "--state", "--cdp"].includes(argument)) {
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) {
        throw new Error(`${argument} requires a value.`);
      }
      options[argument.slice(2)] = value;
      index += 1;
    } else {
      throw new Error(`Unknown argument: ${argument}`);
    }
  }

  if (options.help) return options;
  if (!options.url || !options.output) {
    throw new Error("--url and --output are required.");
  }
  const listing = new URL(options.url);
  if (
    listing.protocol !== "https:" ||
    listing.hostname !== "innovation-studio.microsoft.com" ||
    !listing.pathname.includes("/submissions/projects")
  ) {
    throw new Error("--url must be an Innovation Studio project-listing URL.");
  }

  options.output = path.resolve(options.output);
  const outputDirectory = path.dirname(options.output);
  const outputBase = path.basename(options.output, path.extname(options.output));
  options.images = path.resolve(
    options.images || path.join(outputDirectory, `${outputBase}-images`)
  );
  options.state = path.resolve(
    options.state || path.join(outputDirectory, `.${outputBase}-state.json`)
  );
  options.manifest = path.join(options.images, ".innovation-studio-images.json");
  return options;
}

function safeRequestHeaders(headers) {
  return Object.fromEntries(
    Object.entries(headers || {}).filter(
      ([name]) =>
        !name.startsWith(":") &&
        name !== "host" &&
        name !== "content-length" &&
        name !== "accept-encoding"
    )
  );
}

async function requestWithRetry(context, url, headers, responseType = "json") {
  let lastError;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      const response = await context.request.get(url, {
        headers: safeRequestHeaders(headers),
        timeout: 30000,
      });
      if (!response.ok()) {
        throw new Error(`HTTP ${response.status()} ${response.statusText()}`);
      }
      return responseType === "body"
        ? {
            body: await response.body(),
            contentType: response.headers()["content-type"] || "",
          }
        : await response.json();
    } catch (error) {
      lastError = error;
      console.error(`  Request attempt ${attempt} failed: ${error.message}`);
      await new Promise((resolve) => setTimeout(resolve, attempt * 1000));
    }
  }
  throw lastError;
}

async function discoverProjects(page, listingUrl) {
  let apiHeaders;
  let imageHeaders;
  let eventId;

  page.on("request", async (request) => {
    const url = request.url();
    const apiMatch = url.match(
      /\/api\/events\/([^/]+)\/(?:browse\/projects|projects\?ids=)/
    );
    if (!apiHeaders && apiMatch) {
      eventId = apiMatch[1];
      apiHeaders = await request.allHeaders();
    }
    if (!imageHeaders && /\/api\/events\/[^/]+\/projects\/[^/]+\/images\//.test(url)) {
      imageHeaders = await request.allHeaders();
    }
  });

  await page.goto(listingUrl, { waitUntil: "commit", timeout: 20000 });
  await page.locator("body").waitFor({ state: "visible", timeout: 15000 });

  const expectedCount = await page
    .locator("body")
    .evaluate(async (body) => {
      const deadline = Date.now() + 30000;
      while (Date.now() < deadline) {
        const match = body.innerText.match(/(?:^|\n)(\d+)\s+results(?:\n|$)/i);
        if (match) return Number(match[1]);
        await new Promise((resolve) => setTimeout(resolve, 250));
      }
      return null;
    });
  if (!expectedCount) {
    throw new Error(
      "The listing result count was not visible. Complete sign-in in external Edge and retry."
    );
  }

  let previousCount = -1;
  const maxLoads = Math.ceil(expectedCount / 20) + 5;
  for (let attempt = 1; attempt <= maxLoads; attempt += 1) {
    const links = page.locator('a[data-testid="search-result-card-overlay"]');
    const count = await links.count();
    console.log(`Discovered ${count}/${expectedCount} project cards`);
    if (count >= expectedCount) break;

    const loadMore = page.getByText("Load more", { exact: true });
    if (!(await loadMore.isVisible().catch(() => false))) {
      throw new Error(`Load more is unavailable after finding ${count} projects.`);
    }
    await loadMore.click({ timeout: 10000 });
    await page.waitForTimeout(count === previousCount ? 3000 : 1500);
    previousCount = count;
  }

  const projects = await page
    .locator('a[data-testid="search-result-card-overlay"]')
    .evaluateAll((links) => {
      const records = [];
      const seen = new Set();
      for (const link of links) {
        const href = link.getAttribute("href") || "";
        const id = href.match(/\/project\/(proj-[a-f0-9-]+)/i)?.[1];
        if (!id || seen.has(id)) continue;
        seen.add(id);
        records.push({ id, href: new URL(href, location.origin).href });
      }
      return records;
    });

  for (let attempt = 0; attempt < 20 && !apiHeaders; attempt += 1) {
    await page.waitForTimeout(250);
  }
  if (!apiHeaders || !eventId) {
    throw new Error("Could not observe authenticated Innovation Studio API traffic.");
  }
  if (projects.length !== expectedCount) {
    throw new Error(
      `Expected ${expectedCount} unique projects but discovered ${projects.length}.`
    );
  }
  return {
    eventId,
    expectedCount,
    projects,
    apiHeaders,
    imageHeaders: imageHeaders || apiHeaders,
  };
}

function loadJson(file, fallback) {
  if (!fs.existsSync(file)) return fallback;
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function saveState(file, state) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temporary = `${file}.tmp`;
  fs.writeFileSync(temporary, JSON.stringify(state, null, 2));
  fs.renameSync(temporary, file);
}

function extensionFor(contentType, sourceUrl) {
  if (contentType.includes("jpeg") || contentType.includes("jpg")) return ".jpg";
  if (contentType.includes("webp")) return ".webp";
  if (contentType.includes("gif")) return ".gif";
  const sourceExtension = path.extname(new URL(sourceUrl, ORIGIN).pathname);
  return [".png", ".jpg", ".jpeg", ".webp", ".gif"].includes(
    sourceExtension.toLowerCase()
  )
    ? sourceExtension.toLowerCase().replace(".jpeg", ".jpg")
    : ".png";
}

async function downloadFirstImage({
  context,
  project,
  index,
  headers,
  imageDirectory,
  outputDirectory,
}) {
  const relativeUrl = project.images?.[0]?.url || project.cardImageUrl;
  if (!relativeUrl) return { markdownPath: null, filename: null };

  const separator = relativeUrl.includes("?") ? "&" : "?";
  const imageUrl = `${ORIGIN}${relativeUrl}${separator}format=inline`;
  const { body, contentType } = await requestWithRetry(
    context,
    imageUrl,
    headers,
    "body"
  );
  const extension = extensionFor(contentType, imageUrl);
  const filename = `${String(index).padStart(3, "0")}-${slugify(
    project.title,
    `project-${index}`
  )}${extension}`;
  fs.mkdirSync(imageDirectory, { recursive: true });
  fs.writeFileSync(path.join(imageDirectory, filename), body);
  return {
    filename,
    markdownPath: path
      .relative(outputDirectory, path.join(imageDirectory, filename))
      .split(path.sep)
      .join("/"),
  };
}

async function run(options) {
  const browser = await chromium.connectOverCDP(options.cdp);
  try {
    const context = browser.contexts()[0];
    if (!context) throw new Error("The Edge debugging session has no browser context.");
    let page = context
      .pages()
      .find((candidate) => candidate.url().includes("innovation-studio.microsoft.com"));
    if (!page) page = await context.newPage();

    const discovery = await discoverProjects(page, options.url);
    const priorState = loadJson(options.state, null);
    const canResume =
      priorState &&
      !priorState.completed &&
      priorState.listingUrl === options.url &&
      priorState.eventId === discovery.eventId &&
      JSON.stringify(priorState.projectIds) ===
        JSON.stringify(discovery.projects.map((project) => project.id));
    const state = canResume
      ? priorState
      : {
          version: 1,
          listingUrl: options.url,
          eventId: discovery.eventId,
          projectIds: discovery.projects.map((project) => project.id),
          records: [],
          completed: false,
          startedAt: new Date().toISOString(),
        };
    const recordsById = new Map(
      state.records.map((record) => [record.id, record])
    );

    const form = await requestWithRetry(
      context,
      `${ORIGIN}/api/events/${discovery.eventId}/project-form-versions/live`,
      discovery.apiHeaders
    );
    const fieldLabels = createFieldLabels(form);
    const outputDirectory = path.dirname(options.output);

    for (let offset = 0; offset < discovery.projects.length; offset += 1) {
      const listingProject = discovery.projects[offset];
      const index = offset + 1;
      if (recordsById.has(listingProject.id)) {
        console.log(
          `[${index}/${discovery.expectedCount}] Resuming ${listingProject.id}`
        );
        continue;
      }

      console.log(
        `[${index}/${discovery.expectedCount}] Fetching ${listingProject.id}`
      );
      const project = await requestWithRetry(
        context,
        `${ORIGIN}/api/events/${discovery.eventId}/projects/${listingProject.id}`,
        discovery.apiHeaders
      );
      let image = { markdownPath: null, filename: null };
      try {
        image = await downloadFirstImage({
          context,
          project,
          index,
          headers: discovery.imageHeaders,
          imageDirectory: options.images,
          outputDirectory,
        });
      } catch (error) {
        console.error(`  Image unavailable: ${error.message}`);
      }

      recordsById.set(
        listingProject.id,
        sanitizeProject({
          project,
          index,
          fieldLabels,
          imagePath: image.markdownPath,
          projectUrl: listingProject.href,
        })
      );
      state.records = discovery.projects
        .map((item) => recordsById.get(item.id))
        .filter(Boolean);
      saveState(options.state, state);
    }

    const records = discovery.projects.map((item) => recordsById.get(item.id));
    const markdown = renderMarkdown(records, options.url);
    fs.mkdirSync(outputDirectory, { recursive: true });
    fs.writeFileSync(options.output, markdown);

    const currentManifest = records
      .map((record) => record.imagePath)
      .filter(Boolean)
      .map((imagePath) => path.basename(imagePath));
    fs.mkdirSync(options.images, { recursive: true });
    const previousManifest = loadJson(options.manifest, []);
    const removed = options.keepOldImages
      ? []
      : syncStaleImages(options.images, previousManifest, currentManifest);
    fs.writeFileSync(options.manifest, JSON.stringify(currentManifest, null, 2));

    const verification = verifyCatalog(markdown, outputDirectory);
    if (
      verification.projects !== discovery.expectedCount ||
      verification.uniqueProjectLinks !== discovery.expectedCount ||
      verification.missingLinkedImages !== 0 ||
      verification.nonLocalImageReferences !== 0 ||
      verification.unclosedCodeFence ||
      verification.submissionBoundariesInsideFence !== 0
    ) {
      throw new Error(
        `Catalog verification failed: ${JSON.stringify(verification)}`
      );
    }

    state.completed = true;
    state.completedAt = new Date().toISOString();
    state.verification = verification;
    saveState(options.state, state);

    console.log(`Completed: ${options.output}`);
    console.log(`Projects: ${verification.projects}`);
    console.log(`Unique project links: ${verification.uniqueProjectLinks}`);
    console.log(`Local images: ${verification.localImages}`);
    console.log(`Missing linked images: ${verification.missingLinkedImages}`);
    console.log(
      `Non-local image references: ${verification.nonLocalImageReferences}`
    );
    console.log(`Unclosed code fence: ${verification.unclosedCodeFence}`);
    console.log(`Stale images removed: ${removed.length}`);
  } finally {
    await browser.close();
  }
}

(async () => {
  try {
    const options = parseArguments(process.argv.slice(2));
    if (options.help) {
      printHelp();
      return;
    }
    await run(options);
  } catch (error) {
    console.error(error.stack || error.message || error);
    process.exitCode = 1;
  }
})();

module.exports = { parseArguments };

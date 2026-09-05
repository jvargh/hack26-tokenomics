const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");
const test = require("node:test");
const {
  balancedMarkdown,
  createFieldLabels,
  renderMarkdown,
  sanitizeProject,
  syncStaleImages,
  verifyCatalog,
} = require("../scripts/lib/catalog");

function sampleRecord(overrides = {}) {
  return {
    index: 1,
    id: "proj-1",
    title: "Sample Project",
    tagline: "A useful project",
    description: "Project details",
    challenge: "Example Challenge",
    keywords: ["AI", "Efficiency"],
    memberCount: 1,
    members: [{ displayName: "Example Owner", role: "owner" }],
    openToJoin: false,
    openRoles: [],
    customFields: [],
    challengeLinks: [],
    videos: [],
    githubRepo: null,
    createdAt: "2026-01-01T00:00:00.000Z",
    updatedAt: "2026-01-02T00:00:00.000Z",
    imagePath: null,
    projectUrl:
      "https://innovation-studio.microsoft.com/e/event/project/proj-1",
    capturedAt: "2026-01-03T00:00:00.000Z",
    ...overrides,
  };
}

test("removes authenticated inline images and balances code fences", () => {
  const value = [
    "Before",
    "![image.png](/api/events/event/content-images/image.png?scope=project)",
    "```sh",
    "command",
  ].join("\n");
  const output = balancedMarkdown(value);
  assert.doesNotMatch(output, /content-images/);
  assert.equal((output.match(/^```/gm) || []).length, 2);
  assert.match(output, /command\n```$/);
});

test("sanitizes project members without retaining email addresses or IDs", () => {
  const labels = createFieldLabels({
    formRequired: [{ id: "custom-1", label: "Problem" }],
  });
  const record = sanitizeProject({
    project: {
      id: "proj-1",
      title: "Private-safe project",
      members: [
        {
          id: "internal-id",
          aadObjectId: "aad-id",
          displayName: "Example Owner",
          mail: "owner@example.com",
          role: "owner",
        },
      ],
      customFields: { "custom-1": "A problem" },
    },
    index: 1,
    fieldLabels: labels,
    imagePath: null,
    projectUrl: "https://example.test/project/proj-1",
  });
  const serialized = JSON.stringify(record);
  assert.match(serialized, /Example Owner/);
  assert.match(serialized, /"Problem"/);
  assert.doesNotMatch(serialized, /owner@example\.com|internal-id|aad-id/);
});

test("renders a complete catalog with one verified local image", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "catalog-render-"));
  const imageDirectory = path.join(root, "catalog-images");
  fs.mkdirSync(imageDirectory);
  fs.writeFileSync(path.join(imageDirectory, "001-sample.png"), "image");
  const markdown = renderMarkdown(
    [
      sampleRecord({
        imagePath: "catalog-images/001-sample.png",
        description:
          "Text\n![broken](/api/events/e/content-images/x.png?scope=project)",
      }),
    ],
    "https://innovation-studio.microsoft.com/events/e/submissions/projects"
  );
  const verification = verifyCatalog(markdown, root);
  assert.equal(verification.projects, 1);
  assert.equal(verification.uniqueProjectLinks, 1);
  assert.equal(verification.localImages, 1);
  assert.equal(verification.missingLinkedImages, 0);
  assert.equal(verification.nonLocalImageReferences, 0);
  assert.equal(verification.unclosedCodeFence, false);
  assert.doesNotMatch(markdown, /content-images/);
  fs.rmSync(root, { recursive: true, force: true });
});

test("removes only stale files named by the previous image manifest", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "catalog-cleanup-"));
  fs.writeFileSync(path.join(root, "stale.png"), "old");
  fs.writeFileSync(path.join(root, "current.png"), "current");
  fs.writeFileSync(path.join(root, "user-file.png"), "keep");

  const removed = syncStaleImages(
    root,
    ["stale.png", "current.png", "../outside.png"],
    ["current.png"]
  );
  assert.deepEqual(removed, ["stale.png"]);
  assert.equal(fs.existsSync(path.join(root, "stale.png")), false);
  assert.equal(fs.existsSync(path.join(root, "current.png")), true);
  assert.equal(fs.existsSync(path.join(root, "user-file.png")), true);
  fs.rmSync(root, { recursive: true, force: true });
});

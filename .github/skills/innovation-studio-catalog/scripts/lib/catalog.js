const fs = require("fs");
const path = require("path");

const GENERATED_IMAGE_PATTERN = /!\[[^\]]*\]\(([^)]+)\)/g;
const AUTHENTICATED_CONTENT_IMAGE_PATTERN =
  /!\[[^\]]*\]\(\/api\/events\/[^)\s]+\/content-images\/[^)]+\)/g;

function slugify(value, fallback) {
  const slug = String(value || "")
    .normalize("NFKD")
    .replace(/[^\x00-\x7F]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 70);
  return slug || fallback;
}

function markdownText(value) {
  return String(value || "").replace(/\r/g, "").trim();
}

function balancedMarkdown(value) {
  const markdown = markdownText(value)
    .replace(AUTHENTICATED_CONTENT_IMAGE_PATTERN, "")
    .replace(/\n{3,}/g, "\n\n");
  const fenceCount = (markdown.match(/^```/gm) || []).length;
  return fenceCount % 2 === 0 ? markdown : `${markdown}\n\`\`\``;
}

function inlineText(value) {
  return markdownText(value).replace(/\|/g, "\\|").replace(/\n+/g, " ");
}

function hasValue(value) {
  return !(
    value === null ||
    value === undefined ||
    value === "" ||
    (Array.isArray(value) && value.length === 0)
  );
}

function formatValue(value) {
  if (Array.isArray(value)) {
    return value.map((item) => inlineText(item)).join(", ");
  }
  if (value && typeof value === "object") {
    return `\`\`\`json\n${JSON.stringify(value, null, 2)}\n\`\`\``;
  }
  return balancedMarkdown(value);
}

function createFieldLabels(form) {
  const labels = new Map([
    ["fixed-title", "Project Name"],
    ["fixed-tagline", "Tagline"],
    ["fixed-description", "Description"],
    ["default-keywords", "Keywords"],
    ["default-open-roles", "Recruiting"],
  ]);
  for (const field of [
    ...(form.formRequired || []),
    ...(form.formOptional || []),
  ]) {
    labels.set(field.id, field.label);
  }
  return labels;
}

function sanitizeProject({
  project,
  index,
  fieldLabels,
  imagePath,
  projectUrl,
}) {
  const customFields = Object.entries(project.customFields || {})
    .filter(([, value]) => hasValue(value))
    .map(([id, value]) => ({
      label: fieldLabels.get(id) || `Additional field (${id})`,
      value,
    }));

  return {
    index,
    id: project.id,
    title: project.title || `Project ${index}`,
    tagline: project.tagline || "",
    description: project.description || "",
    challenge: project.execChallengeTitle || "",
    keywords: project.keywords || [],
    memberCount: project.memberCount || project.members?.length || 0,
    members: (project.members || []).map((member) => ({
      displayName: member.displayName,
      role: member.role,
    })),
    openToJoin: Boolean(project.openToJoin),
    openRoles: (project.openRoles || []).map((role) => ({
      title: role.title,
      description: role.description,
      keywords: role.keywords || [],
      professions: role.professions || [],
    })),
    customFields,
    challengeLinks: (project.challengeLinks || []).map((challenge) => ({
      typeLabel: challenge.typeLabel,
      challengeTitle: challenge.challengeTitle,
    })),
    videos: project.videos || [],
    githubRepo: project.githubRepo || null,
    createdAt: project.createdAt || null,
    updatedAt: project.updatedAt || null,
    imagePath,
    projectUrl,
    capturedAt: new Date().toISOString(),
  };
}

function renderOpenRoles(openRoles) {
  if (!openRoles.length) return "";
  return [
    "### Recruiting",
    "",
    ...openRoles.flatMap((role) => [
      `#### ${inlineText(role.title)}`,
      "",
      role.description ? balancedMarkdown(role.description) : "",
      role.keywords.length
        ? `\n**Skills:** ${role.keywords.map(inlineText).join(", ")}`
        : "",
      role.professions.length
        ? `\n**Professions:** ${role.professions.map(inlineText).join(", ")}`
        : "",
      "",
    ]),
  ]
    .filter((line) => line !== "")
    .join("\n");
}

function renderRecord(record) {
  const metadata = [
    ["Challenge", record.challenge],
    ["Members", record.memberCount],
    ["Open to join", record.openToJoin ? "Yes" : "No"],
    ["Keywords", record.keywords.join(", ")],
    ["Created", record.createdAt],
    ["Updated", record.updatedAt],
  ].filter(([, value]) => hasValue(value));

  const sections = [
    `<a id="submission-${String(record.index).padStart(3, "0")}"></a>`,
    `## ${record.index}. ${inlineText(record.title)}`,
    "",
    `**Project page:** [Open submission](${record.projectUrl})`,
    record.imagePath
      ? `\n![${inlineText(record.title)}](${record.imagePath})`
      : "",
    record.tagline ? `\n> ${inlineText(record.tagline)}` : "",
    "",
    "### Project information",
    "",
    "| Field | Value |",
    "| --- | --- |",
    ...metadata.map(
      ([label, value]) => `| ${label} | ${inlineText(value)} |`
    ),
  ];

  if (record.description) {
    sections.push("", "### Description", "", balancedMarkdown(record.description));
  }

  if (record.customFields.length) {
    sections.push("", "### Additional information", "");
    for (const field of record.customFields) {
      sections.push(
        `#### ${inlineText(field.label)}`,
        "",
        formatValue(field.value),
        ""
      );
    }
  }

  if (record.members.length) {
    sections.push(
      "",
      "### Team",
      "",
      ...record.members.map(
        (member) =>
          `- ${inlineText(member.displayName)}${
            member.role === "owner" ? " (Owner)" : ""
          }`
      )
    );
  }

  const recruiting = renderOpenRoles(record.openRoles);
  if (recruiting) sections.push("", recruiting);

  if (record.challengeLinks.length) {
    sections.push(
      "",
      "### Challenge entries",
      "",
      ...record.challengeLinks.map(
        (challenge) =>
          `- **${inlineText(challenge.typeLabel)}:** ${inlineText(
            challenge.challengeTitle
          )}`
      )
    );
  }

  if (record.githubRepo) {
    const repository =
      typeof record.githubRepo === "string"
        ? record.githubRepo
        : record.githubRepo.url || JSON.stringify(record.githubRepo);
    sections.push("", `**Repository:** ${repository}`);
  }

  return sections.join("\n").replace(/\n{3,}/g, "\n\n");
}

function renderMarkdown(records, listingUrl) {
  return [
    "# Innovation Studio Project Catalog",
    "",
    `Catalog of all ${records.length} Innovation Studio submissions in listing order.`,
    "",
    `**Source:** [Innovation Studio submissions](${listingUrl})`,
    "",
    `**Captured:** ${new Date().toISOString()}`,
    "",
    "Only one project image is included per submission. Team email addresses and internal identifiers are intentionally excluded.",
    "",
    "## Contents",
    "",
    ...records.map(
      (record) =>
        `${record.index}. [${inlineText(record.title)}](#submission-${String(
          record.index
        ).padStart(3, "0")})`
    ),
    "",
    "---",
    "",
    ...records.flatMap((record) => [renderRecord(record), "", "---", ""]),
  ].join("\n");
}

function readImageReferences(markdown) {
  return [...markdown.matchAll(GENERATED_IMAGE_PATTERN)].map(
    (match) => match[1]
  );
}

function syncStaleImages(imageDirectory, previousManifest, currentManifest) {
  const current = new Set(currentManifest);
  const root = path.resolve(imageDirectory);
  const removed = [];

  for (const filename of previousManifest) {
    if (current.has(filename)) continue;
    const candidate = path.resolve(imageDirectory, filename);
    if (
      path.dirname(candidate) !== root ||
      !fs.existsSync(candidate) ||
      !fs.statSync(candidate).isFile()
    ) {
      continue;
    }
    fs.unlinkSync(candidate);
    removed.push(filename);
  }
  return removed;
}

function verifyCatalog(markdown, outputDirectory) {
  const anchors = [...markdown.matchAll(/<a id="submission-\d{3}"><\/a>/g)];
  const links = [
    ...markdown.matchAll(
      /\*\*Project page:\*\* \[Open submission\]\(([^)]+)\)/g
    ),
  ].map((match) => match[1]);
  const images = readImageReferences(markdown);
  const localImages = images.filter((image) => !/^[a-z]+:/i.test(image));
  const missing = localImages.filter(
    (image) =>
      !fs.existsSync(path.resolve(outputDirectory, image.replace(/\//g, path.sep)))
  );

  let insideFence = false;
  let boundariesInsideFence = 0;
  for (const line of markdown.split("\n")) {
    if (/^```/.test(line)) {
      insideFence = !insideFence;
    } else if (insideFence && /^<a id="submission-/.test(line)) {
      boundariesInsideFence += 1;
    }
  }

  return {
    projects: anchors.length,
    uniqueProjectLinks: new Set(links).size,
    localImages: localImages.length,
    missingLinkedImages: missing.length,
    nonLocalImageReferences: images.length - localImages.length,
    unclosedCodeFence: insideFence,
    submissionBoundariesInsideFence: boundariesInsideFence,
  };
}

module.exports = {
  balancedMarkdown,
  createFieldLabels,
  readImageReferences,
  renderMarkdown,
  sanitizeProject,
  slugify,
  syncStaleImages,
  verifyCatalog,
};

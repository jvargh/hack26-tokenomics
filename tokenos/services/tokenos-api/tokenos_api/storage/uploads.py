"""Upload storage: real validation, text extraction, and hashing.

A file is only `ready` once its type is accepted and content could actually be
read. Receiving bytes is never enough.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from ..config import settings

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".jsonl", ".diff", ".patch", ".yaml", ".yml", ".xml"}
ARCHIVE_EXTENSIONS = {".zip"}
PDF_EXTENSIONS = {".pdf"}
ALLOWED_EXTENSIONS = TEXT_EXTENSIONS | ARCHIVE_EXTENSIONS | PDF_EXTENSIONS

MEDIA_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".diff": "text/x-diff",
    ".patch": "text/x-diff",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".xml": "application/xml",
    ".zip": "application/zip",
    ".pdf": "application/pdf",
}


class UploadError(Exception):
    """Raised when an upload cannot be accepted or read."""


@dataclass
class Upload:
    upload_id: str
    name: str
    role: str
    workflow_id: str
    media_type: str
    size_bytes: int
    sha256: str
    status: str
    path: Path
    data_classification: str = "internal"
    extracted_text: str = ""
    extracted_character_count: int = 0
    detail: dict = field(default_factory=dict)
    origin: str = "upload"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def public(self) -> dict:
        return {
            "upload_id": self.upload_id,
            "name": self.name,
            "role": self.role,
            "workflow_id": self.workflow_id,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "status": self.status,
            "data_classification": self.data_classification,
            "extracted_character_count": self.extracted_character_count,
            "detail": self.detail,
            "origin": self.origin,
        }


def _extract_pdf_text(raw: bytes) -> str:
    """Minimal text extraction for PDFs that carry an uncompressed text layer.

    Image-only PDFs return an empty string so the caller can reject them with a
    clear message rather than pretending extraction succeeded.
    """
    import zlib

    chunks: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", raw, re.DOTALL):
        blob = match.group(1)
        try:
            blob = zlib.decompress(blob)
        except zlib.error:
            pass
        for text_match in re.finditer(rb"\((?:\\.|[^\\()])*\)", blob):
            piece = text_match.group(0)[1:-1]
            chunks.append(
                piece.replace(b"\\(", b"(").replace(b"\\)", b")").decode("latin-1", "ignore")
            )
    return " ".join(chunk for chunk in chunks if chunk.strip())


def _validate_archive(raw: bytes) -> dict:
    """Rejects path traversal and absolute paths before anything is extracted."""
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(names) > 500:
            raise UploadError("Archive contains more than 500 entries.")
        for name in names:
            normalized = name.replace("\\", "/")
            if normalized.startswith("/") or ".." in Path(normalized).parts:
                raise UploadError(f"Archive entry '{name}' is outside the archive root.")
        total = sum(info.file_size for info in archive.infolist())
        if total > settings.max_total_bytes:
            raise UploadError("Archive expands beyond the allowed total size.")
        return {"entry_count": len(names), "uncompressed_bytes": total, "entries": names[:50]}


class UploadStore:
    def __init__(self) -> None:
        self._uploads: dict[str, Upload] = {}
        self._root = settings.storage_root / "uploads"
        self._root.mkdir(parents=True, exist_ok=True)

    def add(
        self,
        *,
        name: str,
        raw: bytes,
        role: str,
        workflow_id: str,
        data_classification: str = "internal",
        origin: str = "upload",
    ) -> Upload:
        suffix = Path(name).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise UploadError(
                f"{name}: {suffix or 'files without an extension'} is not an accepted file type."
            )
        if len(raw) == 0:
            raise UploadError(f"{name} is empty.")
        if len(raw) > settings.max_file_bytes:
            raise UploadError(
                f"{name} is {len(raw) // 1024} KB, above the "
                f"{settings.max_file_bytes // (1024 * 1024)} MB limit."
            )

        upload_id = f"upl-{secrets.token_hex(6)}"
        digest = hashlib.sha256(raw).hexdigest()
        detail: dict = {}
        text = ""

        if suffix in PDF_EXTENSIONS:
            if not raw.startswith(b"%PDF"):
                raise UploadError(f"{name} is not a valid PDF.")
            text = _extract_pdf_text(raw)
            if not text.strip():
                raise UploadError(
                    f"{name} does not contain extractable text. "
                    "Upload a text-based version or enable the document-extraction adapter."
                )
        elif suffix in ARCHIVE_EXTENSIONS:
            if not zipfile.is_zipfile(BytesIO(raw)):
                raise UploadError(f"{name} is not a valid ZIP archive.")
            detail = _validate_archive(raw)
        else:
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    text = raw.decode("latin-1")
                except UnicodeDecodeError as error:  # pragma: no cover - defensive
                    raise UploadError(f"{name} could not be read as text.") from error
            if suffix == ".json":
                try:
                    json.loads(text)
                except json.JSONDecodeError as error:
                    raise UploadError(f"{name} is not valid JSON: {error.msg}.") from error

        # Storage never uses the original filename as a path.
        stored = self._root / f"{upload_id}{suffix}"
        stored.write_bytes(raw)

        upload = Upload(
            upload_id=upload_id,
            name=Path(name).name,
            role=role,
            workflow_id=workflow_id,
            media_type=MEDIA_TYPES.get(suffix, "application/octet-stream"),
            size_bytes=len(raw),
            sha256=digest,
            status="ready",
            path=stored,
            data_classification=data_classification,
            extracted_text=text,
            extracted_character_count=len(text),
            detail=detail,
            origin=origin,
        )
        self._uploads[upload_id] = upload
        return upload

    def get(self, upload_id: str) -> Upload:
        upload = self._uploads.get(upload_id)
        if upload is None:
            raise UploadError(f"Upload {upload_id} was not found. Upload the file again.")
        return upload

    def many(self, upload_ids: list[str]) -> list[Upload]:
        return [self.get(upload_id) for upload_id in upload_ids]

    def remove(self, upload_id: str) -> None:
        upload = self._uploads.pop(upload_id, None)
        if upload and upload.path.exists():
            upload.path.unlink(missing_ok=True)


upload_store = UploadStore()

"""Configuration for the local TokenOS API.

Every value can be overridden with an environment variable so the same build can
run local-only or with Microsoft Foundry deployments configured.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).resolve().parent.parent / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
except ImportError:
    pass

SERVICE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SERVICE_ROOT.parent.parent


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass
class Settings:
    version: str = "0.1.0"

    # Model routing
    model_mode: str = field(default_factory=lambda: os.getenv("TOKENOS_MODEL_MODE", "local"))
    foundry_base_url: str = field(default_factory=lambda: os.getenv("TOKENOS_FOUNDRY_BASE_URL", ""))
    foundry_efficient_deployment: str = field(
        default_factory=lambda: os.getenv("TOKENOS_FOUNDRY_EFFICIENT_DEPLOYMENT", "tokenos-efficient")
    )
    foundry_advanced_deployment: str = field(
        default_factory=lambda: os.getenv("TOKENOS_FOUNDRY_ADVANCED_DEPLOYMENT", "tokenos-advanced")
    )
    foundry_auth_mode: str = field(
        default_factory=lambda: os.getenv("TOKENOS_FOUNDRY_AUTH_MODE", "entra")
    )
    # Entra token audience. Azure OpenAI and AI Services accounts both issue tokens
    # for the Cognitive Services audience; override only for a different resource type.
    foundry_token_scope: str = field(
        default_factory=lambda: os.getenv(
            "TOKENOS_FOUNDRY_TOKEN_SCOPE", "https://cognitiveservices.azure.com/.default"
        )
    )
    model_timeout_seconds: float = field(
        default_factory=lambda: _float("TOKENOS_MODEL_TIMEOUT_SECONDS", 20.0)
    )
    model_max_retries: int = field(default_factory=lambda: _int("TOKENOS_MODEL_MAX_RETRIES", 1))
    max_output_tokens: int = field(default_factory=lambda: _int("TOKENOS_MAX_OUTPUT_TOKENS", 500))
    max_model_input_characters: int = field(
        default_factory=lambda: _int("TOKENOS_MAX_MODEL_INPUT_CHARACTERS", 12000)
    )

    # Upload limits
    max_files_per_run: int = field(default_factory=lambda: _int("TOKENOS_MAX_FILES_PER_RUN", 10))
    max_file_bytes: int = field(
        default_factory=lambda: _int("TOKENOS_MAX_FILE_BYTES", 10 * 1024 * 1024)
    )
    max_total_bytes: int = field(
        default_factory=lambda: _int("TOKENOS_MAX_TOTAL_BYTES", 25 * 1024 * 1024)
    )

    # Execution limits
    ambiguous_sample_limit: int = field(
        default_factory=lambda: _int("TOKENOS_AMBIGUOUS_SAMPLE_LIMIT", 20)
    )
    test_command_timeout_seconds: float = field(
        default_factory=lambda: _float("TOKENOS_TEST_TIMEOUT_SECONDS", 10.0)
    )

    # Presentation pacing.
    # Real analysis finishes in milliseconds, which is too fast for a person to
    # follow. These delays are inserted between emitted events only: they never
    # touch the measured work time reported in the proof. Set them to 0 for
    # automated clients.
    phase_pacing_ms: int = field(default_factory=lambda: _int("TOKENOS_PHASE_PACING_MS", 500))
    operation_pacing_ms: int = field(
        default_factory=lambda: _int("TOKENOS_OPERATION_PACING_MS", 240)
    )
    step_pacing_ms: int = field(default_factory=lambda: _int("TOKENOS_STEP_PACING_MS", 90))
    stream_attach_timeout_seconds: float = field(
        default_factory=lambda: _float("TOKENOS_STREAM_ATTACH_TIMEOUT_SECONDS", 3.0)
    )

    # Hosting
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            origin.strip()
            for origin in os.getenv(
                "TOKENOS_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            ).split(",")
            if origin.strip()
        )
    )
    storage_root: Path = field(
        default_factory=lambda: Path(
            os.getenv("TOKENOS_STORAGE_ROOT", str(Path.home() / ".tokenos" / "runtime"))
        )
    )

    @property
    def foundry_configured(self) -> bool:
        if self.model_mode != "foundry" or not self.foundry_base_url:
            return False
        if self.foundry_auth_mode == "api_key":
            return bool(os.getenv("AZURE_INFERENCE_CREDENTIAL"))
        return True

    def deployment_for(self, route: str) -> str:
        return (
            self.foundry_advanced_deployment
            if route == "advanced_ai"
            else self.foundry_efficient_deployment
        )


settings = Settings()
settings.storage_root.mkdir(parents=True, exist_ok=True)

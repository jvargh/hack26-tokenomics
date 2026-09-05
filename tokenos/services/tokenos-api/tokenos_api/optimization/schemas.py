from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


OptimizationTarget = Literal["current_workflow", "single_prompt", "measured_workflow"]
Mode = Literal["analyze", "measure"]
InputSource = Literal[
    "paste_prompt", "attach_context", "prompt_example",
    "upload", "telemetry_upload", "workflow_upload",
    "connected", "connected_application",
    "sample", "workflow_example",
]
CurrentModel = Literal["recommend", "efficient", "advanced", "application"]
OutputFormat = Literal["text", "markdown", "json", "table", "code_patch", "custom"]

_SOURCE_FAMILIES = {
    "paste_prompt": "prompt",
    "attach_context": "prompt",
    "prompt_example": "prompt_sample",
    "upload": "upload",
    "telemetry_upload": "upload",
    "workflow_upload": "upload",
    "connected": "connected",
    "connected_application": "connected",
    "sample": "sample",
    "workflow_example": "sample",
}
_TARGET_TO_MODE = {
    "current_workflow": "analyze",
    "single_prompt": "measure",
    "measured_workflow": "measure",
}
_MODE_DEFAULT_TARGET = {"analyze": "current_workflow", "measure": "measured_workflow"}
_PROMPT_FAMILIES = {"prompt", "prompt_sample"}
_WORKFLOW_FAMILIES = {"upload", "connected", "sample"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class Volume(StrictModel):
    value: int = Field(gt=0, le=1_000_000_000)
    period: Literal["day", "week", "month", "year"]


class Inputs(StrictModel):
    workflowDescription: str | None = Field(default=None, min_length=1, max_length=8000)
    telemetryExportIds: list[str] = Field(default_factory=list, max_length=10)
    testInputIds: list[str] = Field(default_factory=list, max_length=10)
    representativeInputIds: list[str] = Field(default_factory=list, max_length=10)
    representativeRequests: list[dict[str, Any] | str] = Field(default_factory=list, max_length=20)
    sampleId: str | None = None
    applicationId: str | None = None
    filters: dict[str, str] = Field(default_factory=dict)
    recurringVolume: Volume | None = None
    owner: str = Field(default="", max_length=120)
    costCenter: str = Field(default="", max_length=120)
    environment: str = Field(default="local", max_length=80)

    # Prompt-level inputs. They stay optional here so legacy workflow requests
    # remain valid; DescribeRequest applies target-specific requirements.
    userPrompt: str | None = Field(default=None, min_length=1, max_length=20000)
    systemInstructions: str | None = Field(default=None, max_length=8000)
    conversationHistory: str | None = Field(default=None, max_length=40000)
    contextFileIds: list[str] = Field(default_factory=list, max_length=10)
    currentModel: CurrentModel = "recommend"
    outputFormat: OutputFormat = "text"
    desiredOutcome: str | None = Field(default=None, max_length=2000)
    expectedResult: str | None = Field(default=None, max_length=8000)
    promptExampleId: Literal["verbose_support_reply", "repeated_policy_lookup"] | None = None

    @field_validator("workflowDescription", "userPrompt", "desiredOutcome")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Text fields cannot be blank when supplied.")
        return value


class Requirements(StrictModel):
    qualityRequirements: list[str] = Field(min_length=1, max_length=12)
    optimizationGoal: Literal[
        "cost_per_accepted_outcome", "reduce_model_calls", "reduce_context",
        "reduce_latency", "compare_models",
    ]
    maxModelSpendUsd: float = Field(default=0.05, ge=0, le=100)
    maxInputTokens: int = Field(default=8000, ge=1, le=200000)
    allowAdvancedEscalation: bool = False
    maxAdvancedCalls: int = Field(default=1, ge=0, le=20)
    maxOutputTokens: int = Field(default=500, ge=32, le=4096)
    maxOutputCharacters: int = Field(default=8000, ge=32, le=65536)
    latencyTargetMs: int | None = Field(default=None, gt=0, le=3_600_000)
    humanApprovalGranted: bool = False
    dataHandling: Literal["allow", "redact", "minimize", "approval_required", "block"] = "minimize"
    outputContract: dict[str, Any] = Field(default_factory=lambda: {
        "type": "object",
        "required": ["decision"],
        "properties": {
            "decision": {"type": "string"},
            "citations": {"type": "array", "items": {"type": "string"}},
            "diagnosis": {"type": "string"},
        },
        "additionalProperties": False,
    })


class DescribeRequest(StrictModel):
    workflow: Literal["workflow_optimization"]
    optimizationTarget: OptimizationTarget | None = None
    inputSource: InputSource
    mode: Mode | None = None
    inputs: Inputs
    requirements: Requirements

    @model_validator(mode="before")
    @classmethod
    def derive_mode_and_target(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        value = dict(data)
        target = value.get("optimizationTarget")
        mode = value.get("mode")
        if target is None and mode is None:
            mode = "measure"
            target = "measured_workflow"
        elif target is None:
            target = _MODE_DEFAULT_TARGET.get(mode)
        elif mode is None:
            mode = _TARGET_TO_MODE.get(target)
        else:
            expected = _TARGET_TO_MODE.get(target)
            if expected is not None and mode != expected:
                raise ValueError("optimizationTarget and mode do not agree.")
        value["optimizationTarget"] = target
        value["mode"] = mode
        return value

    @model_validator(mode="after")
    def validate_target_inputs(self) -> "DescribeRequest":
        family = _SOURCE_FAMILIES[self.inputSource]
        if self.optimizationTarget == "single_prompt":
            if family not in _PROMPT_FAMILIES:
                raise ValueError("single_prompt accepts only prompt or prompt_example input sources.")
            if not (self.inputs.userPrompt or self.inputs.promptExampleId):
                raise ValueError("userPrompt is required for single_prompt unless a promptExampleId is selected.")
            if not self.inputs.desiredOutcome and not self.inputs.promptExampleId:
                raise ValueError("desiredOutcome is required for single_prompt.")
            if self.inputs.telemetryExportIds or self.inputs.testInputIds or self.inputs.representativeInputIds or self.inputs.representativeRequests:
                raise ValueError("single_prompt does not accept workflow telemetry or representative workflow requests.")
        else:
            if family not in _WORKFLOW_FAMILIES:
                raise ValueError("Workflow targets accept only upload, connected, or sample input sources.")
            if not self.inputs.workflowDescription:
                raise ValueError("workflowDescription is required for workflow targets.")
            if self.inputs.userPrompt or self.inputs.systemInstructions or self.inputs.conversationHistory or self.inputs.contextFileIds or self.inputs.promptExampleId:
                raise ValueError("Prompt fields are accepted only with optimizationTarget='single_prompt'.")
        return self

    @property
    def input_family(self) -> str:
        return _SOURCE_FAMILIES[self.inputSource]


class OptimizeRequest(StrictModel):
    approvePlan: Literal[True]

    @field_validator("approvePlan", mode="before")
    @classmethod
    def explicit_approval(cls, value):
        if value is not True:
            raise ValueError("Explicit boolean approval is required.")
        return value


class AuthorizeRequest(StrictModel):
    authorizeModelCost: bool = False
    humanApprovalGranted: bool = False


class BaselineRequest(StrictModel):
    acknowledgeModelCost: Literal[True]
    baselineProfile: Literal["all_ai_v1"]

    @field_validator("acknowledgeModelCost", mode="before")
    @classmethod
    def explicit_acknowledgement(cls, value):
        if value is not True:
            raise ValueError("Explicit boolean model-cost acknowledgement is required.")
        return value

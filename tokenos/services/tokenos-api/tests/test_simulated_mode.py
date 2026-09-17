"""Tests for the judge demonstration's simulated model mode.

The most important test here is `test_no_provider_call_is_ever_attempted`. The
whole premise of the hosted demonstration is that it costs nothing in model
spend, and that claim needs a test that would actually fail if it stopped being
true rather than an assertion about configuration.

Run: .\\.venv\\Scripts\\python.exe -m pytest tests/test_simulated_mode.py -v
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import subprocess
import sys

import pytest

from tokenos_api import modeladapter
from tokenos_api.config import MODEL_MODES, settings
from tokenos_api.simulator import (
    SIMULATION_ORIGIN,
    SimulatedModelAdapter,
    UnsupportedSimulationRequest,
)


@pytest.fixture()
def simulated(monkeypatch):
    """Selects simulated mode and clears the cached adapter."""
    monkeypatch.setattr(settings, "model_mode", "simulated")
    modeladapter.reset_model_adapter()
    yield
    modeladapter.reset_model_adapter()


def generate(**kwargs):
    return asyncio.run(SimulatedModelAdapter().generate(**kwargs))


# ------------------------------------------------------------- mode safety


def test_simulated_is_a_recognised_mode():
    assert "simulated" in MODEL_MODES


@pytest.mark.parametrize("value", ["", "Simulated ", "SIMULATED"])
def test_mode_is_normalised_not_guessed(value, monkeypatch):
    """Whitespace and case are tolerated; anything else is not."""
    monkeypatch.setenv("TOKENOS_MODEL_MODE", value or "local")
    import tokenos_api.config as config

    importlib.reload(config)
    assert config.settings.model_mode in MODEL_MODES


def test_an_unrecognised_mode_stops_startup():
    """A typo must not be silently coerced.

    Coercing to `local` would quietly disable AI routes and make the demo look
    broken; coercing the other way could spend money. Failing loudly with the
    offending value named is the only safe option.
    """
    env = dict(os.environ, TOKENOS_MODEL_MODE="definitely-not-a-mode")
    result = subprocess.run(
        [sys.executable, "-c", "import tokenos_api.config"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode != 0
    assert "not recognised" in result.stderr


def test_simulated_mode_never_looks_foundry_configured(simulated):
    """`foundry_configured` gates credential acquisition and client construction.

    If simulated mode satisfied it, the application would build a provider
    client and try to authenticate.
    """
    assert settings.simulated is True
    assert settings.foundry_configured is False


def test_simulated_mode_selects_the_simulator(simulated):
    assert isinstance(modeladapter.get_model_adapter(), SimulatedModelAdapter)


def test_simulated_mode_reports_a_model_route_is_available(simulated):
    """Workflows must still take their AI branches, or the demonstration would
    only ever show the local path."""
    assert modeladapter.model_available() is True


def test_foundry_variables_cannot_override_simulated_mode(simulated, monkeypatch):
    """Leftover Foundry configuration must not reopen a path to real spend."""
    monkeypatch.setattr(settings, "foundry_base_url", "https://example.invalid/openai/v1/")
    monkeypatch.setattr(settings, "foundry_auth_mode", "entra")
    modeladapter.reset_model_adapter()

    assert settings.foundry_configured is False
    assert isinstance(modeladapter.get_model_adapter(), SimulatedModelAdapter)


# ------------------------------------------------------ zero provider calls


def test_no_provider_call_is_ever_attempted(simulated):
    """Proves the cost claim rather than asserting it.

    Outbound connections are intercepted and recorded. Loopback is allowed
    through because asyncio builds its event loop from a local socketpair on
    Windows; blocking that would fail the test for reasons unrelated to model
    spend. Any connection to a non-loopback address is treated as a provider
    call and fails the test.
    """
    attempts: list[str] = []

    import ipaddress
    import socket

    def is_loopback(address) -> bool:
        try:
            host = address[0] if isinstance(address, tuple) else str(address)
            return ipaddress.ip_address(host).is_loopback
        except (ValueError, IndexError, TypeError):
            # A hostname rather than an address: not verifiably local, so it
            # counts as an outbound attempt.
            return False

    original_connect = socket.socket.connect
    original_create = socket.create_connection

    def watched_connect(self, address, *args, **kwargs):
        if not is_loopback(address):
            attempts.append(f"socket.connect -> {address}")
            raise AssertionError(f"Simulated mode attempted an outbound call to {address}")
        return original_connect(self, address, *args, **kwargs)

    def watched_create(address, *args, **kwargs):
        if not is_loopback(address):
            attempts.append(f"create_connection -> {address}")
            raise AssertionError(f"Simulated mode attempted an outbound call to {address}")
        return original_create(address, *args, **kwargs)

    socket.socket.connect = watched_connect
    socket.create_connection = watched_create
    try:
        result = generate(
            route="efficient_ai",
            system='Reply with JSON only {"explanations":[{"document":"...","policy_citation":"..."}]}',
            input_text=json.dumps({
                "ambiguous_charges": [{"document": "invoice.md", "amount_usd": 150.0}],
                "policy_rules": ["Section 4.2"],
            }),
            json_response=True,
        )
    finally:
        socket.socket.connect = original_connect
        socket.create_connection = original_create

    assert not attempts, f"Outbound connections attempted: {attempts}"
    assert result.content


def test_the_provider_sdk_is_never_imported(simulated):
    """The judge image omits the SDK entirely, so importing it would crash.

    This catches a regression before it reaches the image.
    """
    generate(
        route="efficient_ai",
        system='Reply with JSON only {"mapping":{}}. classify records',
        input_text=json.dumps({"known_categories": ["A"], "records": [{"index": 0, "text": "a"}]}),
        json_response=True,
    )
    assert "openai" not in sys.modules
    assert not any(name.startswith("azure.identity") for name in sys.modules)


# ---------------------------------------------------------------- provenance


def test_every_result_carries_a_simulation_identifier(simulated):
    result = generate(
        route="efficient_ai",
        system='Reply with JSON only {"mapping":{}}. classify records',
        input_text=json.dumps({"known_categories": ["Billing"], "records": ["invoice"]}),
        json_response=True,
    )
    assert result.request_id.startswith("sim-"), result.request_id
    assert result.model_version == "tokenos-simulator-v1"


def test_identifiers_are_deterministic_for_the_same_request(simulated):
    """A judge re-running the same example should see the same evidence."""
    payload = dict(
        route="efficient_ai",
        system='Reply with JSON only {"mapping":{}}. classify records',
        input_text=json.dumps({"known_categories": ["Billing"], "records": ["invoice"]}),
        json_response=True,
    )
    assert generate(**payload).request_id == generate(**payload).request_id


def test_a_simulated_identifier_cannot_pass_as_a_provider_receipt(simulated):
    """Provider request IDs never carry this prefix, so a downloaded artifact
    cannot be mistaken for measured evidence."""
    result = generate(
        route="efficient_ai",
        system='Reply with JSON only {"mapping":{}}. classify records',
        input_text=json.dumps({"known_categories": ["Billing"], "records": ["invoice"]}),
        json_response=True,
    )
    assert SIMULATION_ORIGIN == "simulated"
    assert result.request_id.startswith("sim-")


# ------------------------------------------------------- authored responses


def test_explanations_cite_the_supplied_policy_and_document(simulated):
    """The simulator answers from the caller's real input, so the downstream
    citation check does genuine work."""
    result = generate(
        route="efficient_ai",
        system='Reply with JSON only {"explanations":[{"policy_citation":"..."}]}',
        input_text=json.dumps({
            "ambiguous_charges": [
                {"document": "NW-2026-04-0119.md", "amount_usd": 150.0, "description": "weekend surcharge"},
            ],
            "policy_rules": ["Section 4.2 surcharges require written approval"],
        }),
        json_response=True,
    )
    explanation = json.loads(result.content)["explanations"][0]
    assert explanation["document"] == "NW-2026-04-0119.md"
    assert explanation["amount_usd"] == 150.0
    assert "Section 4.2" in explanation["policy_citation"]


def test_classification_only_uses_categories_the_caller_offered(simulated):
    result = generate(
        route="efficient_ai",
        system='Reply with JSON only {"mapping":{}}. classify records',
        input_text=json.dumps({
            "known_categories": ["Billing", "Shipping"],
            "records": [
                {"index": 1, "text": "invoice not paid"},
                {"index": 2, "text": "parcel delayed"},
            ],
        }),
        json_response=True,
    )
    mapping = json.loads(result.content)["mapping"]
    assert set(mapping.values()) <= {"Billing", "Shipping"}
    assert mapping["1"] == "Billing"
    assert mapping["2"] == "Shipping"


def test_a_diagnosis_never_claims_the_test_passed(simulated):
    """The caller rejects a summary that claims an unearned pass. The authored
    text must satisfy that check honestly rather than evade it."""
    result = generate(
        route="advanced_ai",
        system="Diagnose the failing test from the supplied output.",
        input_text=json.dumps({
            "requested_change": "Add the archive endpoint",
            "test_output": "test_archive FAILED: AssertionError: expected 200, got 404",
            "schema_issues": [],
        }),
    )
    assert "FAILED" in result.content or "not pass" in result.content
    assert "tests pass" not in result.content.lower()


# ------------------------------------------------------- refusing the unknown


@pytest.mark.parametrize("system,text", [
    ("Write a poem about otters", "be creative"),
    ("You are a helpful assistant", "summarise this contract"),
    ("", ""),
])
def test_unsupported_requests_are_refused(simulated, system, text):
    """The simulator does not understand arbitrary instructions and must not
    appear to. Inventing prose would misrepresent what the demo does."""
    with pytest.raises(UnsupportedSimulationRequest) as error:
        generate(route="efficient_ai", system=system, input_text=text, json_response=False)
    assert "example" in str(error.value).lower()


def test_the_refusal_tells_the_judge_what_to_do(simulated):
    with pytest.raises(UnsupportedSimulationRequest) as error:
        generate(route="efficient_ai", system="freeform", input_text="anything", json_response=False)
    message = str(error.value)
    assert "Load example inputs" in message or "example" in message
    assert "does not run a model" in message or "not run a model" in message


# -------------------------------------------------------------- boundaries


def test_output_ceiling_is_respected(simulated):
    """The caller pins a maximum output length and enforces it. Overflow is
    reported rather than silently returning unparseable truncated JSON."""
    charges = [
        {"document": f"doc-{index}.md", "amount_usd": 10.0, "description": "x" * 200}
        for index in range(60)
    ]
    with pytest.raises(UnsupportedSimulationRequest) as error:
        generate(
            route="efficient_ai",
            system='Reply with JSON only {"explanations":[{"policy_citation":"..."}]}',
            input_text=json.dumps({"ambiguous_charges": charges, "policy_rules": ["Section 1"]}),
            max_output_tokens=50,
            json_response=True,
        )
    assert "ceiling" in str(error.value).lower()


def test_usage_figures_describe_the_text_actually_produced(simulated):
    result = generate(
        route="efficient_ai",
        system='Reply with JSON only {"mapping":{}}. classify records',
        input_text=json.dumps({"known_categories": ["Billing"], "records": ["invoice"]}),
        json_response=True,
    )
    assert result.input_tokens > 0
    assert result.output_tokens > 0
    # Never claimed: the provider reports these, and no provider was involved.
    assert result.cached_input_tokens == 0
    assert result.reasoning_tokens == 0


# ------------------------------------------------------------------- health


def test_health_reports_simulated_mode_truthfully(simulated):
    """/health must state the configured mode, not infer it.

    It previously derived the mode from "is a model route available", which is
    true in simulated mode, so it reported modelMode=foundry and
    foundryAvailable=true with no provider configured at all. That is a false
    statement about spend, and it also suppressed the judge banner, which keys
    off the reported mode.
    """
    from fastapi.testclient import TestClient

    from tokenos_api.app import app

    with TestClient(app) as client:
        body = client.get("/health").json()

    assert body["modelMode"] == "simulated"
    assert body["foundryAvailable"] is False
    # No provider deployment exists, so none may be advertised.
    assert body["efficientDeployment"] is None
    assert body["advancedDeployment"] is None


def test_health_still_reports_local_mode_unchanged(monkeypatch):
    """The existing local behaviour must not shift."""
    monkeypatch.setattr(settings, "model_mode", "local")
    modeladapter.reset_model_adapter()

    from fastapi.testclient import TestClient

    from tokenos_api.app import app

    with TestClient(app) as client:
        body = client.get("/health").json()

    assert body["modelMode"] == "local"
    assert body["foundryAvailable"] is False


# -------------------------------------------------------- session scoping


def test_a_session_cookie_is_issued_in_simulated_mode(simulated):
    from fastapi.testclient import TestClient

    from tokenos_api.app import app
    from tokenos_api.session import COOKIE_NAME

    with TestClient(app) as client:
        response = client.get("/health")

    cookie = response.cookies.get(COOKIE_NAME)
    assert cookie, "no session cookie issued"
    header = " ".join(response.headers.get_list("set-cookie"))
    assert "HttpOnly" in header
    assert "Secure" in header
    assert "SameSite=lax" in header.lower() or "samesite=lax" in header.lower()


def test_no_session_cookie_outside_simulated_mode(monkeypatch):
    """Local and Foundry deployments keep their existing behaviour."""
    monkeypatch.setattr(settings, "model_mode", "local")

    from fastapi.testclient import TestClient

    from tokenos_api.app import app
    from tokenos_api.session import COOKIE_NAME

    with TestClient(app) as client:
        response = client.get("/health")

    assert COOKIE_NAME not in response.cookies


def test_visitors_do_not_see_each_others_runs(simulated):
    """One judge's history must not appear in another's.

    Uses two independent clients, which is what two browsers amount to: each
    gets its own cookie jar and therefore its own session identifier.
    """
    from fastapi.testclient import TestClient

    from tokenos_api.app import app

    def start_run(client) -> str:
        sample = client.post("/api/uploads/sample", json={"workflow_id": "document_review"})
        uploads = {role: [item["upload_id"] for item in items]
                   for role, items in sample.json()["uploads"].items()}
        analyze = client.post("/api/runs/analyze", json={
            "workflow_id": "document_review", "input_source": "sample", "uploads": uploads,
            "inputs": {"review-focus": "Unsupported charges"}, "desired_outcome": "",
            "requirements": {"maximum_cost_usd": 1.0, "required_quality_score": 0.9},
        })
        assert analyze.status_code == 200, analyze.text
        started = client.post("/api/runs", json={"plan_id": analyze.json()["plan_id"]})
        assert started.status_code == 200, started.text
        return started.json()["run_id"]

    with TestClient(app, base_url="https://testserver") as first, \
         TestClient(app, base_url="https://testserver") as second:
        first_run = start_run(first)
        second_run = start_run(second)

        first_visible = {run["run_id"] for run in first.get("/api/runs").json()["runs"]}
        second_visible = {run["run_id"] for run in second.get("/api/runs").json()["runs"]}

    assert first_run in first_visible
    assert second_run in second_visible
    assert second_run not in first_visible, "visitor 1 can see visitor 2's run"
    assert first_run not in second_visible, "visitor 2 can see visitor 1's run"


def test_a_malformed_session_cookie_is_replaced(simulated):
    """A crafted cookie value must not become a storage key."""
    from fastapi.testclient import TestClient

    from tokenos_api.app import app
    from tokenos_api.session import COOKIE_NAME

    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set(COOKIE_NAME, "../../etc/passwd")
        response = client.get("/api/runs")

    assert response.status_code == 200
    issued = response.cookies.get(COOKIE_NAME)
    assert issued and "/" not in issued

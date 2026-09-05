"""Explicit browser fixtures; kept out of conftest to preserve legacy imports."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

import httpx
import pytest

SERVICE = Path(__file__).resolve().parents[2]
WEB = SERVICE.parents[1] / "apps" / "web"


def _port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _wait(url: str, process: subprocess.Popen, log: Path) -> None:
    deadline = time.monotonic() + 40
    with httpx.Client(trust_env=False) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(f"Server exited before readiness: {log.read_text(encoding='utf-8')}")
            try:
                if client.get(url, timeout=1).is_success:
                    return
            except httpx.TransportError:
                pass
            time.sleep(0.1)
    pytest.fail(f"Server never became ready at {url}; see {log}")


@pytest.fixture(scope="session")
def browser_servers(tmp_path_factory):
    root = tmp_path_factory.mktemp("browser-servers")
    api_url = f"http://127.0.0.1:{_port()}"
    web_url = f"http://127.0.0.1:{_port()}"
    env = {
        **os.environ,
        "TOKENOS_MODEL_MODE": "local",
        "TOKENOS_STORAGE_ROOT": str(root / "runtime"),
        "TOKENOS_CORS_ORIGINS": web_url,
        "TOKENOS_PHASE_PACING_MS": "0",
        "TOKENOS_OPERATION_PACING_MS": "0",
        "TOKENOS_STEP_PACING_MS": "0",
        "TOKENOS_STREAM_ATTACH_TIMEOUT_SECONDS": "0",
        "VITE_TOKENOS_API_BASE": api_url,
    }
    node = shutil.which("node")
    assert node, "Node.js is required; install application prerequisites before browser tests."
    commands = [
        (
            [sys.executable, "-m", "uvicorn", "tokenos_api.app:app",
             "--host", "127.0.0.1", "--port", api_url.rsplit(":", 1)[1]],
            SERVICE, api_url + "/health",
        ),
        (
            [node, str(WEB / "node_modules" / "vite" / "bin" / "vite.js"),
             "--host", "127.0.0.1", "--port", web_url.rsplit(":", 1)[1], "--strictPort"],
            WEB, web_url,
        ),
    ]
    processes = []
    handles = []
    try:
        for index, (command, cwd, url) in enumerate(commands):
            log = root / f"server-{index}.log"
            handle = log.open("w", encoding="utf-8")
            handles.append(handle)
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=handle, stderr=handle)
            processes.append(process)
            _wait(url, process, log)
        yield {"api": api_url, "web": web_url}
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        for handle in handles:
            handle.close()


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        channel = os.getenv("TOKENOS_BROWSER_CHANNEL", "msedge" if sys.platform == "win32" else "")
        instance = playwright.chromium.launch(headless=True, **({"channel": channel} if channel else {}))
        yield instance
        instance.close()


@pytest.fixture
def page(browser, browser_servers):
    context = browser.new_context(viewport={"width": 1440, "height": 1100})
    tab = context.new_page()
    tab.set_default_timeout(15000)
    tab.goto(browser_servers["web"], wait_until="networkidle")
    yield tab
    context.close()

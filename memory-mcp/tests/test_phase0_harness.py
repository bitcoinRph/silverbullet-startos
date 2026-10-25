"""Offline regression tests for CI fixture plumbing, not real-image evidence."""

import importlib.util
from pathlib import Path

import httpx
import pytest


def spike():
    path = Path(__file__).with_name("test_real_image.py")
    spec = importlib.util.spec_from_file_location("image_spike_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_probe_reaches_bearer_after_unauthorized_response():
    module = spike()
    seen = []

    def handler(request):
        seen.append(request.headers.get("authorization"))
        if not request.headers.get("authorization"):
            return httpx.Response(401)
        return httpx.Response(503, json={"error": "Runtime API is not enabled"})

    with httpx.Client(
        base_url="http://127.0.0.1:3000", transport=httpx.MockTransport(handler)
    ) as client:
        module.test_runtime_disabled(client)
    assert seen == ["", "Bearer " + module.TOKEN] * 2


def test_runtime_bearer_execution_and_generic_failures_remain_blockers():
    module = spike()
    for response in [httpx.Response(200, text="2"), httpx.Response(503, json={"error": "other"})]:
        seen = []

        def handler(request):
            seen.append(request.headers.get("authorization"))
            return httpx.Response(401) if not request.headers.get("authorization") else response

        with httpx.Client(
            base_url="http://127.0.0.1:3000", transport=httpx.MockTransport(handler)
        ) as client:
            with pytest.raises(AssertionError):
                module.test_runtime_disabled(client)
        assert seen == ["", "Bearer " + module.TOKEN]


def test_browser_page_url_preserves_port_separator():
    module = spike()
    with httpx.Client(base_url="http://127.0.0.1:32768") as client:
        assert (
            module._page_url(client, "Inbox/ConcurrencySpike")
            == "http://127.0.0.1:32768/Inbox/ConcurrencySpike"
        )

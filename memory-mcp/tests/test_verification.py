import ast

from pathlib import Path

import httpx
import pytest


@pytest.mark.parametrize(
    "status,ready,expected", [(200, True, 0), (503, True, 1), (200, False, 1), (401, False, 1)]
)
def test_health_requires_status_and_body(monkeypatch, status, ready, expected):
    from silverbullet_memory import health

    monkeypatch.setattr(
        health.httpx, "get", lambda *a, **kw: httpx.Response(status, json={"ready": ready})
    )
    assert health.main() == expected


def test_upstream_client_has_no_mutation_or_runtime_surface():
    import silverbullet_memory.client as client

    source = Path(client.__file__).read_text()
    tree = ast.parse(source)
    methods = {
        n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert methods == {"__init__", "_get", "inventory", "get"}
    assert "/.runtime" not in source
    assert "'PUT'" not in source and '"PUT"' not in source


def test_constant_time_compares_both_scopes(monkeypatch):
    from silverbullet_memory import security

    original = security.hmac.compare_digest
    calls = []

    def compare(a, b):
        calls.append((len(a), len(b)))
        return original(a, b)

    monkeypatch.setattr(security.hmac, "compare_digest", compare)
    for value in ["", "Bearer " + "r" * 48, "Bearer " + "w" * 48]:
        try:
            security.authenticate(value, "r" * 48, "w" * 48)
        except PermissionError:
            pass
    assert calls == [(32, 32)] * 6


def test_json_duplicate_keys_and_nonfinite_numbers_rejected():
    from silverbullet_memory.security import bounded_json

    for raw in [b'{"params":1,"params":2}', b'{"x":NaN}', b'{"x":Infinity}']:
        with pytest.raises(ValueError):
            bounded_json(raw)

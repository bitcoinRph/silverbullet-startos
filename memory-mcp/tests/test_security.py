import pytest


def test_gate_module_exists():
    from silverbullet_memory import security

    assert callable(security.validate_path)


@pytest.mark.parametrize(
    "path",
    [
        "../x.md",
        "/x.md",
        "Inbox/../x.md",
        "Inbox/.x.md",
        "CONFIG.md",
        "_plug/x.md",
        "Library/x.md",
        "Inbox/a.txt",
        "Inbox/a\x00.md",
        "Inbox/a\n.md",
        "Inbox/a%2f.md",
        "Inbox/a\\b.md",
        "Inbox//a.md",
    ],
)
def test_paths_rejected(path):
    from silverbullet_memory.security import validate_path

    with pytest.raises(ValueError):
        validate_path(path)


@pytest.mark.parametrize(
    "content",
    [
        "```space-lua\nprint(1)\n```",
        "~~~space-style\nbody{}\n~~~",
        "${1}",
        "```query\na\n```",
        "query[[from x]]",
        "```template\nx\n```",
        '<ScRiPt src="a">',
        '<img onerror ="x">',
        "---\ntags: [meta/template]\n---",
        "---\ntags:\n - meta/library\n---",
        '<a href="javascript:evil()">',
        "![x](data:text/html,x)",
    ],
)
def test_executable_content_rejected(content):
    from silverbullet_memory.security import validate_content

    with pytest.raises(ValueError):
        validate_content(content)


def test_safe_content_and_create_paths():
    from silverbullet_memory.security import validate_content, validate_path

    validate_content("---\nkind: note\nstatus: inbox\n---\n# Plain note\n[[Business/Example]]")
    assert validate_path("Inbox/a.md", create=True) == "Inbox/a.md"
    with pytest.raises(ValueError):
        validate_path("Business/a.md", create=True)


def test_scopes():
    from silverbullet_memory.security import authenticate

    assert authenticate("Bearer " + "r" * 40, "r" * 40, "w" * 40) == "read"
    assert authenticate("Bearer " + "w" * 40, "r" * 40, "w" * 40) == "write"
    for value in ["", "Bearer wrong", "Basic xxx", "Bearer " + "é" * 40]:
        with pytest.raises(PermissionError):
            authenticate(value, "r" * 40, "w" * 40)


@pytest.mark.parametrize(
    "raw",
    [
        b"[" * 20 + b"0" + b"]" * 20,
        b"[" + b"0," * 257 + b"0]",
        b'{"x":' + b"[" * 20 + b"0" + b"]" * 20 + b"}",
    ],
)
def test_preparse_limits(raw):
    from silverbullet_memory.security import bounded_json

    with pytest.raises(ValueError):
        bounded_json(raw)

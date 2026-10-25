import asyncio
import hashlib
import httpx
import pytest


def test_client_contract():
    from silverbullet_memory.client import SilverBulletClient

    seen = []

    def handler(request):
        seen.append(request)
        assert request.headers["authorization"] == "Bearer synthetic-internal"
        assert request.headers["x-sync-mode"] == "true"
        if request.url.path == "/.fs":
            return httpx.Response(
                200, json=[{"name": "Business/A.md", "lastModified": 1, "size": 4}]
            )
        return httpx.Response(
            200,
            text="note",
            headers={"ETag": '"sha256:' + hashlib.sha256(b"note").hexdigest() + '"'},
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = SilverBulletClient("http://silverbullet.test", "synthetic-internal", http)
            assert (await client.inventory())[0]["name"] == "Business/A.md"
            page = await client.get("Business/A.md")
            assert page["content"] == "note"
            assert page["etag"].startswith('"sha256:')
            for path in ["CONFIG.md", "../x.md", "Library/x.md"]:
                with pytest.raises(ValueError):
                    await client.get(path)

    asyncio.run(run())
    assert len(seen) == 2


@pytest.mark.parametrize("status", [401, 403, 404, 412, 500, 302])
def test_status_errors_are_safe(status):
    from silverbullet_memory.client import SilverBulletClient, UpstreamError

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(status, text="private-content"))
        ) as http:
            client = SilverBulletClient("http://silverbullet.test", "synthetic-internal", http)
            with pytest.raises(UpstreamError) as error:
                await client.get("Inbox/a.md")
            assert "private-content" not in str(error.value)

    asyncio.run(run())


def test_malformed_inventory_and_oversized_content():
    from silverbullet_memory.client import SilverBulletClient, UpstreamError

    async def run():
        for response in [
            httpx.Response(200, text="not-json"),
            httpx.Response(200, json={"x": "y"}),
        ]:
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response)) as http:
                with pytest.raises(UpstreamError):
                    await SilverBulletClient(
                        "http://silverbullet.test", "synthetic", http
                    ).inventory()
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 65537))
        ) as http:
            with pytest.raises(UpstreamError):
                await SilverBulletClient("http://silverbullet.test", "synthetic", http).get(
                    "Inbox/a.md"
                )

    asyncio.run(run())

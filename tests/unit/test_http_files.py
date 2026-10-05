"""Regression coverage for raw binary and multipart staging uploads."""

import asyncio
import hashlib
from types import SimpleNamespace

import httpx
import pytest
from anyio import CancelScope, lowlevel
from fastapi import FastAPI
from loguru import logger
from starlette.datastructures import UploadFile
from starlette import formparsers
from starlette.requests import ClientDisconnect, Request

from axonx.components.service.http.files import MULTIPART_OVERHEAD_BYTES, _UploadParser, create_files_router
from axonx.workspace.staging import StagedFiles


@pytest.fixture(autouse=True)
def closed_spools(monkeypatch):
    """Assert cleanup on all parser exits, including errors before FormData exists."""
    spools = []
    original = formparsers.SpooledTemporaryFile

    def temporary(*args, **kwargs):
        spool = original(*args, **kwargs)
        spools.append(spool)
        return spool

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", temporary)
    yield spools
    assert all(spool.closed for spool in spools)


@pytest.fixture
def endpoint(tmp_path):
    """Use an isolated workspace and a small limit without the full service."""
    staged = StagedFiles(tmp_path, max_upload_bytes=32)
    server = FastAPI()
    server.include_router(create_files_router(SimpleNamespace(logger=logger), staged))
    return server, staged


@pytest.mark.parametrize("payload", [b"", b"print('hello')\n", bytes(range(32))])
async def test_multipart_and_binary_store_identical_file_bytes(endpoint, tmp_path, payload):
    server, _staged = endpoint
    async with httpx.AsyncClient(transport=httpx.ASGITransport(server), base_url="http://test") as client:
        multipart = await client.post(
            "/files", files={"file": ("script.py", payload)}, data={"directory": "tmp/scripts"}
        )
        binary = await client.post(
            "/files",
            content=payload,
            headers={"x-file-name": "script.py", "x-file-directory": "tmp/scripts"},
        )
        assert multipart.status_code == binary.status_code == 200
        assert multipart.json() == binary.json()
        copied = multipart.json()["answer"]
        digest = hashlib.sha256(payload).hexdigest()
        assert copied == {"path": f"tmp/scripts/{digest}/script.py", "sha256": digest, "size": len(payload)}
        assert (tmp_path / copied["path"]).read_bytes() == payload
        response = await client.delete("/files", params={"path": copied["path"]})
        assert response.status_code == 200
        assert not (tmp_path / copied["path"]).exists()


async def test_multipart_headers_override_form_metadata_and_close_spool(endpoint, monkeypatch):
    server, _staged = endpoint
    uploads = []
    original = UploadFile.close

    async def close(upload):
        uploads.append(upload)
        await original(upload)

    monkeypatch.setattr(UploadFile, "close", close)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(server), base_url="http://test") as client:
        response = await client.post(
            "/files",
            files={"file": ("script.py", b"hello")},
            data={"directory": "tmp/form"},
            headers={"x-file-name": "renamed.py", "x-file-directory": "tmp/header"},
        )
    assert response.status_code == 200
    assert response.json()["answer"]["path"] == f"tmp/header/{hashlib.sha256(b'hello').hexdigest()}/renamed.py"
    assert len(uploads) == 1
    assert uploads[0].file.closed


async def test_large_multipart_spools_to_disk_and_preserves_bytes(endpoint, tmp_path, closed_spools):
    server, staged = endpoint
    payload = b"x" * (1024 * 1024 + 1)
    staged.max_upload_bytes = len(payload)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(server), base_url="http://test") as client:
        response = await client.post("/files", files={"file": ("large.bin", payload)})
    assert response.status_code == 200
    copied = response.json()["answer"]
    assert copied["size"] == len(payload)
    assert (tmp_path / copied["path"]).read_bytes() == payload
    assert closed_spools[0]._rolled


async def test_multipart_closes_rolled_spool_when_storage_is_cancelled(endpoint, monkeypatch, closed_spools):
    server, staged = endpoint
    payload = b"x" * (1024 * 1024 + 1)
    staged.max_upload_bytes = len(payload)
    with CancelScope() as scope:

        async def cancelled_store(*args, **kwargs):
            scope.cancel()
            await lowlevel.checkpoint()

        monkeypatch.setattr(staged, "store_stream", cancelled_store)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(server), base_url="http://test") as client:
            await client.post("/files", files={"file": ("large.bin", payload)})
    assert scope.cancelled_caught
    assert len(closed_spools) == 1
    assert closed_spools[0]._rolled
    assert closed_spools[0].closed


async def test_multipart_rejects_oversized_part_headers(endpoint, tmp_path):
    server, _staged = endpoint
    body = (
        b'--test\r\nContent-Disposition: form-data; name="file"; filename="script.py"\r\nX-Padding: '
        + b"x" * 8192
        + b"\r\n\r\nx\r\n--test--\r\n"
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(server), base_url="http://test") as client:
        response = await client.post(
            "/files", content=body, headers={"content-type": "multipart/form-data; boundary=test"}
        )
    assert response.status_code == 400
    assert not list(tmp_path.rglob("*"))


async def test_duplicate_multipart_field_is_rejected(endpoint, tmp_path):
    server, _staged = endpoint
    async with httpx.AsyncClient(transport=httpx.ASGITransport(server), base_url="http://test") as client:
        response = await client.post("/files", files=[("file", (None, "text")), ("file", ("script.py", b"x"))])
    assert response.status_code == 422
    assert not list(tmp_path.rglob("*"))


@pytest.mark.parametrize(
    ("files", "data", "headers", "status"),
    [
        ({"other": ("script.py", b"x")}, {}, {}, 422),
        ({"file": (None, "text")}, {}, {}, 422),
        ({"file": ("script.py", b"x")}, {"other": "x"}, {}, 422),
        ({"file": ("../script.py", b"x")}, {}, {}, 422),
        ({"file": ("script.py", b"x")}, {"directory": "../outside"}, {}, 422),
        ({"file": ("script.py", b"x")}, {"directory": "other"}, {}, 422),
        ({"file": ("script.py", b"x")}, {}, {"x-file-name": "../script.py"}, 422),
        ({"file": ("script.py", b"x")}, {}, {"x-file-directory": "/tmp/outside"}, 422),
        ({"file": ("script.py", b"x"), "extra": ("extra.py", b"x")}, {}, {}, 400),
        ({"file": ("script.py", b"x")}, {"directory": "tmp", "extra": "x"}, {}, 400),
        ({"file": ("script.py", b"x")}, {}, {"content-length": "invalid"}, 400),
        ({"file": ("script.py", b"x")}, {}, {"content-length": "-1"}, 400),
        ({"file": ("script.py", b"x")}, {}, {"content-length": str(MULTIPART_OVERHEAD_BYTES + 33)}, 413),
    ],
)
async def test_invalid_multipart_never_stages_files(endpoint, tmp_path, files, data, headers, status):
    server, _staged = endpoint
    async with httpx.AsyncClient(transport=httpx.ASGITransport(server), base_url="http://test") as client:
        response = await client.post("/files", files=files, data=data, headers=headers)
    assert response.status_code == status
    assert not list(tmp_path.rglob("*"))


@pytest.mark.parametrize("declared_length", [None, "1"])
@pytest.mark.parametrize("multipart", [False, True])
async def test_actual_upload_size_is_bounded_without_accurate_content_length(
    endpoint, tmp_path, declared_length, multipart
):
    server, _staged = endpoint
    if multipart:
        request = httpx.Request("POST", "http://test/files", files={"file": ("script.py", b"x" * 33)})
        body = request.read()
        headers = {"content-type": request.headers["content-type"]}
    else:
        body = b"x" * 33
        headers = {"x-file-name": "script.py"}
    if declared_length is not None:
        headers["content-length"] = declared_length

    async def chunks():
        for offset in range(0, len(body), 7):
            yield body[offset : offset + 7]

    async with httpx.AsyncClient(transport=httpx.ASGITransport(server), base_url="http://test") as client:
        response = await client.post("/files", content=chunks(), headers=headers)
    assert response.status_code == 413
    assert not list(tmp_path.rglob("*"))


@pytest.mark.parametrize(
    ("content_type", "body"),
    [
        ("multipart/form-data", b"invalid"),
        ("multipart/form-data; boundary=test", b"invalid"),
        ("multipart/form-data; boundary=test", b"--test--\r\n"),
        (
            "multipart/form-data; boundary=test",
            b'--test\r\nContent-Disposition: form-data; name="file"; filename="script.py"\r\n\r\nx',
        ),
    ],
)
async def test_malformed_or_empty_multipart_is_rejected(endpoint, tmp_path, content_type, body):
    server, _staged = endpoint
    async with httpx.AsyncClient(transport=httpx.ASGITransport(server), base_url="http://test") as client:
        response = await client.post("/files", content=body, headers={"content-type": content_type})
    assert response.status_code in {400, 422}
    assert not list(tmp_path.rglob("*"))


@pytest.mark.parametrize("failure", [asyncio.CancelledError, ClientDisconnect])
async def test_multipart_parser_closes_partial_spool_on_interrupted_request(failure):
    prefix = b'--test\r\nContent-Disposition: form-data; name="file"; filename="script.py"\r\n\r\nx'
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": prefix, "more_body": True}
        raise failure()

    request = Request({"type": "http", "headers": [(b"content-type", b"multipart/form-data; boundary=test")]}, receive)
    parser = _UploadParser(request, 32)
    with pytest.raises(failure):
        await parser.parse()
    assert len(parser._files_to_close_on_error) == 1
    assert parser._files_to_close_on_error[0].closed


async def test_multipart_request_framing_is_bounded(endpoint, tmp_path):
    server, _staged = endpoint

    async def chunks():
        yield b"x" * (MULTIPART_OVERHEAD_BYTES + 33)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(server), base_url="http://test") as client:
        response = await client.post(
            "/files", content=chunks(), headers={"content-type": "multipart/form-data; boundary=test"}
        )
    assert response.status_code == 413
    assert not list(tmp_path.rglob("*"))


async def test_multipart_preserves_conflict_response_and_openapi(endpoint, tmp_path):
    server, staged = endpoint
    copied = staged.store(b"x", "script.py")
    (tmp_path / copied.path).write_bytes(b"tampered")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(server), base_url="http://test") as client:
        response = await client.post("/files", files={"file": ("script.py", b"x")})
        schema = (await client.get("/openapi.json")).json()
    assert response.status_code == 409
    content = schema["paths"]["/files"]["post"]["requestBody"]["content"]
    assert set(content) == {"application/octet-stream", "multipart/form-data"}
    assert content["multipart/form-data"]["schema"]["required"] == ["file"]

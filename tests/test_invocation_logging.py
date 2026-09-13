"""Invocation logging tests."""

# pylint: disable=missing-function-docstring

import httpx

from axonx import Application
from axonx.components.service import HttpService
from axonx.constants import LOG_ARGUMENT_MAX_LENGTH
from axonx.utils import format_log_arguments


def test_format_log_arguments_caps_length():
    rendered = format_log_arguments({"payload": "x" * 2000})

    assert len(rendered) <= LOG_ARGUMENT_MAX_LENGTH
    assert rendered.endswith("...")


async def test_run_job_logs_name_and_bounded_arguments():
    messages = []
    app = Application(log_to_console=False, log_to_file=False, jobs={"inspect": {}})
    app.context.jobs["inspect"].logger = type(
        "RecordingLogger", (), {"info": lambda _self, message: messages.append(message)}
    )()

    async with app:
        await app.run_job("inspect", payload="x" * 2000)

    assert len(messages) == 1
    assert messages[0].startswith("Job called: name=inspect arguments=")
    assert (
        len(messages[0].removeprefix("Job called: name=inspect arguments="))
        <= LOG_ARGUMENT_MAX_LENGTH
    )
    assert messages[0].endswith("...")


async def test_plugin_endpoint_logs_name_and_upload_metadata():
    messages = []
    app = Application(log_to_console=False, log_to_file=False)
    service = HttpService()
    service.logger = type(
        "RecordingLogger", (), {"info": lambda _self, message: messages.append(message)}
    )()
    server = service.build_service(app)

    async with app:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=server), base_url="http://test"
        ) as client:
            response = await client.post(
                "/plugins",
                content=b"wheel",
                headers={
                    "x-wheel-filename": "demo.whl",
                    "x-wheel-sha256": "abc123",
                },
            )

    assert response.status_code == 404
    assert len(messages) == 1
    assert messages[0].startswith(
        "Plugin endpoint called: name=install_plugin arguments="
    )
    assert "demo.whl" in messages[0]
    assert "abc123" in messages[0]

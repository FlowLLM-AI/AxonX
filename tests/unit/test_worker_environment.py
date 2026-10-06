"""Environment inheritance contracts for local Task workers."""

from unittest.mock import AsyncMock, Mock

import pytest

from axonx.components.task_manager.local.supervisor import TaskProcessSupervisor


@pytest.mark.parametrize(
    ("parent_library_path", "environment", "expected_library_path"),
    [
        ("/parent/lib", {}, "/parent/lib"),
        ("/parent/lib", {"LD_LIBRARY_PATH": "/application/lib"}, "/application/lib"),
        ("/parent/lib", {"LD_LIBRARY_PATH": ""}, ""),
        (None, {}, None),
    ],
)
async def test_worker_library_path_inheritance(monkeypatch, parent_library_path, environment, expected_library_path):
    monkeypatch.setenv("PATH", "/parent/bin")
    monkeypatch.setenv("HOME", "/parent/home")
    monkeypatch.setenv("AXONX_TEST_UNDECLARED", "excluded")
    if parent_library_path is None:
        monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)
    else:
        monkeypatch.setenv("LD_LIBRARY_PATH", parent_library_path)
    process = Mock(pid=123)
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr("axonx.components.task_manager.local.supervisor.asyncio.create_subprocess_exec", spawn)
    supervisor = TaskProcessSupervisor(0, Mock(), AsyncMock())
    monkeypatch.setattr(supervisor, "_monitor", AsyncMock())

    await supervisor.spawn([], environment, "base#demo#test", "demo", "run")
    try:
        child_environment = spawn.call_args.kwargs["env"]
        expected = {"PATH": "/parent/bin", "HOME": "/parent/home"}
        if expected_library_path is not None:
            expected["LD_LIBRARY_PATH"] = expected_library_path
        assert child_environment == expected
    finally:
        await supervisor.shutdown()

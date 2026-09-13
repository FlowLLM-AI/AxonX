"""Plugin wheel build and installation behavior."""

# pylint: disable=missing-function-docstring

from pathlib import Path
from types import SimpleNamespace

from axonx.plugin.artifact import PluginArtifact, build_wheel, install_artifact


def test_build_wheel_only_reuses_explicit_cache(monkeypatch, tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    wheel = output / "demo-0.1-py3-none-any.whl"
    wheel.write_bytes(b"old")

    assert build_wheel(tmp_path, output, use_cache=True) == wheel

    def run(command, **_kwargs):
        build_output = Path(command[command.index("--wheel-dir") + 1])
        (build_output / wheel.name).write_bytes(b"new")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("axonx.plugin.artifact.subprocess.run", run)
    assert build_wheel(tmp_path, output) == wheel
    assert wheel.read_bytes() == b"new"


def test_install_artifact_force_reinstalls_plugin_without_dependencies(
    monkeypatch,
    tmp_path,
):
    commands = []
    monkeypatch.setattr(
        "axonx.plugin.artifact.subprocess.run",
        lambda command, **_kwargs: commands.append(command)
        or SimpleNamespace(returncode=0, stderr="", stdout=""),
    )
    artifact = PluginArtifact(
        distribution="demo",
        version="0.1",
        plugin_names=("demo",),
        tasks={},
        requirements=(),
        wheel=tmp_path / "demo.whl",
        sha256="digest",
        components={},
        jobs={},
    )

    install_artifact(artifact)

    assert commands[0][-4:-1] == ["--upgrade", "--force-reinstall", "--no-deps"]

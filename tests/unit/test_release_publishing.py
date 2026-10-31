"""Exercise release workflow failure handling without contacting package registries."""

import json
import os
import runpy
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def version_workspace(tmp_path):
    for relative in (
        "axonx/_version.py",
        "axonx_studio/pyproject.toml",
        "axonx_studio/package.json",
        "axonx_studio/package-lock.json",
        "scripts/package_studio.py",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    (tmp_path / "axonx_studio/_version.py").symlink_to("../axonx/_version.py")
    return tmp_path


def run_version_script(root, *args):
    return subprocess.run(
        [sys.executable, str(root / "scripts/package_studio.py"), *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("version", ["1.2.3", "1.2.3-rc.1"])
def test_version_bump_needs_only_the_canonical_source(version_workspace, version):
    root = version_workspace
    studio = root / "axonx_studio"
    before = {path: path.read_bytes() for path in studio.iterdir() if not path.is_symlink()}
    (root / "axonx/_version.py").write_text(f'__version__ = "{version}"\n')
    checked = run_version_script(root, "--expected-version", f"v{version}")
    assert checked.returncode == 0 and checked.stdout.strip() == version, checked.stderr
    assert runpy.run_path(str(studio / "_version.py"))["__version__"] == version
    assert {path: path.read_bytes() for path in before} == before
    assert "version" not in tomllib.loads((studio / "pyproject.toml").read_text())["project"]
    package = json.loads((studio / "package.json").read_text())
    lock = json.loads((studio / "package-lock.json").read_text())
    assert all("version" not in metadata for metadata in (package, lock, lock["packages"][""]))
    mismatched = run_version_script(root, "--expected-version", "v9.9.9")
    assert mismatched.returncode != 0 and "Release version mismatch" in mismatched.stderr


@pytest.mark.parametrize("version", ["1.2.3rc1", "1.2.3-dev.1", "01.2.3"])
def test_shared_version_rejects_noncanonical_formats(version_workspace, version):
    root = version_workspace
    (root / "axonx/_version.py").write_text(f'__version__ = "{version}"\n')
    result = run_version_script(root)
    assert result.returncode != 0 and "shared Python/npm version" in result.stderr


@pytest.fixture(
    params=[
        "dist/axonx",
        "dist/python",
    ],
)
def publishing_job(request):
    package_dir = request.param
    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["publish-pypi"]
    assert job["permissions"]["id-token"] == "write"
    assert not job.get("continue-on-error", False)
    steps = job["steps"]
    check = next(step for step in steps if step.get("name") == "Check package metadata")
    signing = next(step for step in steps if step.get("id") == "attestations")
    publish = steps[-1]
    assert [step for step in steps if step.get("continue-on-error")] == [signing]
    assert signing["timeout-minutes"] == 2
    assert publish["env"]["ATTESTATIONS_OUTCOME"] == "${{ steps.attestations.outcome }}"
    assert steps.index(check) < steps.index(signing) < steps.index(publish)
    return publish, package_dir


@pytest.mark.parametrize("outcome", ["success", "failure"])
@pytest.mark.parametrize("upload_exit", [0, 23])
def test_publish_continues_without_attestations_but_preserves_upload_errors(
    tmp_path, publishing_job, outcome, upload_exit
):
    publish, package_dir = publishing_job

    distributions = tmp_path / package_dir
    distributions.mkdir(parents=True)
    for filename in ("sample-1.0.0-py3-none-any.whl", "sample-1.0.0.tar.gz"):
        (distributions / filename).write_text("package")
    # A failed signer may leave a partial attestation beside the distributions.
    (distributions / "sample-1.0.0.tar.gz.publish.attestation").write_text("{}")
    args_file = tmp_path / "upload-args.txt"
    env = os.environ | {
        "ATTESTATIONS_OUTCOME": outcome,
        "PACKAGE_DIR": package_dir,
        "UPLOAD_ARGS": str(args_file),
        "UPLOAD_EXIT": str(upload_exit),
    }
    stub = """
python() {
    printf '%s\\n' "$@" > "${UPLOAD_ARGS}"
    return "${UPLOAD_EXIT}"
}
"""
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", stub + publish["run"]],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == upload_exit
    upload = args_file.read_text(encoding="utf-8").splitlines()
    assert upload[:3] == ["-m", "twine", "upload"]
    assert "--non-interactive" in upload
    assert ("--attestations" in upload) == (outcome == "success")
    assert "--skip-existing" not in upload
    assert ("::warning::" in result.stdout) == (outcome == "failure")
    assert {argument for argument in upload[3:] if not argument.startswith("--")} == {
        str(filename.relative_to(tmp_path)) for filename in distributions.iterdir()
    }

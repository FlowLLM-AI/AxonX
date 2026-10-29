"""Exercise release workflow failure handling without contacting package registries."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(
    params=[
        ("release-python.yml", "publish", "dist/axonx"),
        ("release-axonx-studio.yml", "publish-python", "dist/python"),
    ],
)
def publishing_job(request):
    filename, job_name, package_dir = request.param
    workflow = yaml.safe_load((ROOT / ".github/workflows" / filename).read_text(encoding="utf-8"))
    job = workflow["jobs"][job_name]
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

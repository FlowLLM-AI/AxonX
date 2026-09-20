from axonx.task.storage import artifact_record


def test_artifact_record_uses_the_shared_file_size_field(tmp_path):
    artifact = tmp_path / "result.bin"
    artifact.write_bytes(b"artifact")

    record = artifact_record(artifact, tmp_path)

    assert record["path"] == "result.bin"
    assert record["size"] == len(b"artifact")
    assert "bytes" not in record
    assert len(record["sha256"]) == 64

"""Tests for ArtifactStore."""

import os
import pytest

from attractor.artifacts import ArtifactStore


class TestArtifactStore:
    def test_store_and_retrieve(self):
        store = ArtifactStore()
        aid = store.store("result", {"key": "value"})
        assert store.retrieve(aid) == {"key": "value"}

    def test_list_artifacts(self):
        store = ArtifactStore()
        store.store("a", "data_a")
        store.store("b", "data_b")
        arts = store.list_artifacts()
        assert len(arts) == 2
        names = {a.name for a in arts}
        assert names == {"a", "b"}

    def test_remove(self):
        store = ArtifactStore()
        aid = store.store("temp", "data")
        assert store.remove(aid) is True
        assert store.retrieve(aid) is None
        assert store.remove(aid) is False

    def test_retrieve_missing(self):
        store = ArtifactStore()
        assert store.retrieve("nonexistent") is None

    def test_file_backed_large_artifact(self, tmp_path):
        store = ArtifactStore(storage_dir=str(tmp_path))
        large_data = "x" * 200_000  # > 100KB threshold
        aid = store.store("big", large_data)

        # Should be file-backed
        artifact = store._artifacts[aid]
        assert artifact.file_path != ""
        assert os.path.exists(artifact.file_path)

        # Retrieve still works
        retrieved = store.retrieve(aid)
        assert retrieved == large_data

    def test_remove_deletes_file(self, tmp_path):
        store = ArtifactStore(storage_dir=str(tmp_path))
        large_data = "y" * 200_000
        aid = store.store("big", large_data)
        file_path = store._artifacts[aid].file_path
        assert os.path.exists(file_path)

        store.remove(aid)
        assert not os.path.exists(file_path)

    def test_small_artifact_not_file_backed(self, tmp_path):
        store = ArtifactStore(storage_dir=str(tmp_path))
        aid = store.store("small", "tiny")
        assert store._artifacts[aid].file_path == ""
        assert store.retrieve(aid) == "tiny"

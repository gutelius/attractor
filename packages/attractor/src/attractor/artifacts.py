"""Artifact store for pipeline outputs."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

_FILE_THRESHOLD = 100 * 1024  # 100KB


@dataclass
class Artifact:
    id: str
    name: str
    content_type: str = "text/plain"
    data: Any = None
    file_path: str = ""


class ArtifactStore:
    """Stores and retrieves pipeline artifacts, file-backing large ones."""

    def __init__(self, storage_dir: str = "") -> None:
        self._artifacts: dict[str, Artifact] = {}
        self._storage_dir = storage_dir

    def store(self, name: str, data: Any, content_type: str = "text/plain") -> str:
        """Store an artifact. Returns artifact ID."""
        artifact_id = str(uuid.uuid4())[:8]
        artifact = Artifact(id=artifact_id, name=name, content_type=content_type)

        serialized = json.dumps(data, default=str)
        size = len(serialized)

        if size > _FILE_THRESHOLD and self._storage_dir:
            os.makedirs(os.path.join(self._storage_dir, "artifacts"), exist_ok=True)
            file_path = os.path.join(self._storage_dir, "artifacts", f"{artifact_id}.json")
            with open(file_path, "w") as f:
                f.write(serialized)
            artifact.file_path = file_path
        else:
            artifact.data = data

        self._artifacts[artifact_id] = artifact
        return artifact_id

    def retrieve(self, artifact_id: str) -> Any:
        """Retrieve an artifact by ID."""
        artifact = self._artifacts.get(artifact_id)
        if artifact is None:
            return None
        if artifact.file_path:
            with open(artifact.file_path) as f:
                return json.load(f)
        return artifact.data

    def list_artifacts(self) -> list[Artifact]:
        """List all stored artifacts."""
        return list(self._artifacts.values())

    def remove(self, artifact_id: str) -> bool:
        """Remove an artifact."""
        artifact = self._artifacts.pop(artifact_id, None)
        if artifact is None:
            return False
        if artifact.file_path and os.path.exists(artifact.file_path):
            os.remove(artifact.file_path)
        return True

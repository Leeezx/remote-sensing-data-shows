"""Regression tests for production image contents."""

from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def dockerfile_copy_lines() -> set[str]:
    """Every COPY directive in the backend image, normalized for comparison."""
    return {
        line.strip()
        for line in (REPOSITORY_ROOT / "Dockerfile.backend").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.lstrip().startswith("COPY ")
    }


def test_backend_image_copies_reclamation_artifacts():
    assert (
        "COPY --chown=app:app data/reclamation/ ./data/reclamation/"
        in dockerfile_copy_lines()
    )


@pytest.mark.parametrize(
    "artifact_directory",
    ("data/reclamation", "data/water_demand"),
)
def test_backend_image_copies_every_analysis_map_artifact(artifact_directory):
    """Both drill-down modules read checked-in artifacts, never mounted volumes.

    Runtime bind mounts only cover rasters, vectors and statistics, so these
    directories must be baked into the image or the pages fail at runtime.
    """
    assert (
        f"COPY --chown=app:app {artifact_directory}/ ./{artifact_directory}/"
        in dockerfile_copy_lines()
    )
    assert (REPOSITORY_ROOT / artifact_directory).is_dir()


@pytest.mark.parametrize(
    "artifact_directory",
    ("data/reclamation", "data/water_demand"),
)
def test_dockerignore_does_not_exclude_analysis_map_artifacts(artifact_directory):
    """An .dockerignore entry would silently drop the COPY above."""
    patterns = {
        line.strip()
        for line in (REPOSITORY_ROOT / ".dockerignore").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    assert artifact_directory not in patterns
    assert f"{artifact_directory}/" not in patterns

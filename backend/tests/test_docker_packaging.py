"""Regression tests for production image contents."""

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_backend_image_copies_reclamation_artifacts():
    dockerfile_lines = {
        line.strip()
        for line in (REPOSITORY_ROOT / "Dockerfile.backend").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.lstrip().startswith("COPY ")
    }

    assert (
        "COPY --chown=app:app data/reclamation/ ./data/reclamation/"
        in dockerfile_lines
    )

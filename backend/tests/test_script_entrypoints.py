"""Every script documented for operators must run from the repository root.

The README and the deployment guides tell operators to run scripts as
``python scripts/<name>.py``. Running a file that way puts ``scripts/`` on
``sys.path`` instead of the repository root, so any script importing the
``backend`` package needs an explicit bootstrap. Unit tests import the modules
through the ``scripts`` package with pytest's rootdir already importable, which
is why this class of breakage previously slipped through.
"""

from pathlib import Path
import subprocess
import sys

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

# Scripts documented for direct execution from the repository root, mapped to
# the arguments that make them exit successfully without touching real data.
DOCUMENTED_SCRIPTS = {
    "check_deployment_data.py": (),
    "build_water_demand_data.py": ("--help",),
    "build_reclamation_data.py": ("--help",),
    "build_irrigation_runtime_stats.py": ("--help",),
}

IMPORT_FAILURES = (
    "ModuleNotFoundError",
    "ImportError",
    "No module named",
)


@pytest.mark.parametrize("script_name", sorted(DOCUMENTED_SCRIPTS))
def test_documented_script_resolves_application_imports(script_name):
    """Running the script as a file must not fail on `backend`/`scripts` imports.

    Data-dependent commands may legitimately exit non-zero on a workstation that
    has no runtime rasters, so only import breakage is treated as a failure.
    """
    script = REPOSITORY_ROOT / "scripts" / script_name
    assert script.is_file(), script

    completed = subprocess.run(
        [sys.executable, str(script), *DOCUMENTED_SCRIPTS[script_name]],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
    )

    for marker in IMPORT_FAILURES:
        assert marker not in completed.stderr, (
            f"{script_name} cannot resolve application imports when run as a file:\n"
            f"{completed.stderr}"
        )
    assert "Traceback (most recent call last)" not in completed.stderr, (
        f"{script_name} raised when run as a file:\n{completed.stderr}"
    )


@pytest.mark.parametrize(
    "script_name",
    (
        "check_deployment_data.py",
        "build_water_demand_data.py",
        "build_reclamation_data.py",
        "build_irrigation_runtime_stats.py",
    ),
)
def test_scripts_bootstrap_the_repository_root(script_name):
    """The bootstrap must add the repository root, not the scripts directory."""
    source = (REPOSITORY_ROOT / "scripts" / script_name).read_text(encoding="utf-8")

    assert "PROJECT_ROOT = Path(__file__).resolve().parents[1]" in source
    assert "sys.path.insert(0, str(PROJECT_ROOT))" in source

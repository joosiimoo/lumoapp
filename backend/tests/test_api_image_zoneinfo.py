from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend" / "docker" / "check_zoneinfo.sh"


def test_api_image_resolves_iana_timezone() -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker is required to verify the API image timezone database")
    completed = subprocess.run(
        ["sh", str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    assert completed.returncode == 0, output
    assert "America/Mexico_City" in completed.stdout

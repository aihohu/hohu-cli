import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("encoding", ["cp936", "utf-8"])
@pytest.mark.parametrize("errors", ["strict", "surrogateescape"])
@pytest.mark.parametrize("entry", ["module", "launcher"])
@pytest.mark.parametrize("valid_repo", [True, False])
def test_create_with_encoded_output(tmp_path, encoding, errors, entry, valid_repo):
    source = tmp_path / "source"
    if valid_repo:
        subprocess.run(["git", "init", str(source)], check=True, capture_output=True)
        (source / "README.md").write_text("fixture", encoding="utf-8")
        subprocess.run(["git", "-C", str(source), "add", "README.md"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(source),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "-m",
                "Fixture",
            ],
            check=True,
            capture_output=True,
        )
    env = os.environ.copy()
    env["PYTHONUTF8"] = "0"
    env["PYTHONIOENCODING"] = f"{encoding}:{errors}"
    if entry == "launcher":
        launcher = Path(sys.executable).parent / (
            "hohu.exe" if sys.platform == "win32" else "hohu"
        )
        assert launcher.is_file(), "Install the CLI in the test environment"
        command = [str(launcher)]
    else:
        command = [sys.executable, "-m", "hohu.main"]
    result = subprocess.run(
        [
            *command,
            "create",
            "demo",
            "--component",
            "backend",
            "--non-interactive",
            "--repo",
            str(source),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=False,
    )
    output = (result.stdout + result.stderr).decode(encoding)
    assert "UnicodeEncodeError" not in output, output
    assert result.returncode == (0 if valid_repo else 1), output
    if valid_repo:
        assert (tmp_path / "demo/hohu-admin/README.md").read_text() == "fixture"
    else:
        assert "does not appear to be a git repository" in output, output
    if encoding == "utf-8":
        assert "🚚" in output


def test_version_output_is_safe_for_windows_cp936_console() -> None:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp936"

    result = subprocess.run(
        [sys.executable, "-m", "hohu.main", "--version"],
        capture_output=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0, result.stderr.decode("cp936", errors="replace")
    assert "HoHu CLI" in result.stdout.decode("cp936")

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from click import unstyle


@pytest.mark.parametrize("encoding", ["cp936", "utf-8"])
@pytest.mark.parametrize("errors", ["strict", "surrogateescape"])
@pytest.mark.parametrize("entry", ["module", "launcher"])
@pytest.mark.parametrize("source_state", ["valid", "missing", "directory"])
def test_create_with_encoded_output(tmp_path, encoding, errors, entry, source_state):
    home = tmp_path / "home"
    config = home / ".hohu" / "config.json"
    config.parent.mkdir(parents=True)
    config.write_text('{"language": "en"}', encoding="utf-8")
    env = os.environ.copy()
    env.update(
        HOME=str(home),
        USERPROFILE=str(home),
        GIT_CONFIG_GLOBAL=str(home / ".gitconfig"),
        GIT_CONFIG_NOSYSTEM="1",
        PYTHONUTF8="0",
        PYTHONIOENCODING=f"{encoding}:{errors}",
    )
    source = tmp_path / "source"
    if source_state == "valid":
        subprocess.run(
            ["git", "init", str(source)], check=True, capture_output=True, env=env
        )
        (source / "README.md").write_text("fixture", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(source), "add", "README.md"], check=True, env=env
        )
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
            env=env,
        )
    elif source_state == "directory":
        source.mkdir()
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
    output = unstyle((result.stdout + result.stderr).decode(encoding))
    assert "UnicodeEncodeError" not in output, output
    assert result.returncode == (0 if source_state == "valid" else 1), output
    if source_state == "valid":
        assert (tmp_path / "demo/hohu-admin/README.md").read_text() == "fixture"
    else:
        assert "Failed to clone repository (Backend):" in output, output
        assert "fatal:" in output, output
        assert not (tmp_path / "demo/hohu-admin").exists()
        marker = json.loads(
            (tmp_path / "demo/.hohu/project.json").read_text(encoding="utf-8")
        )
        assert "Backend" not in marker.get("repositories", {})
        assert not list((tmp_path / "demo/.hohu/tmp").iterdir())
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

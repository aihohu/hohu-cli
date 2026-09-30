import os
import subprocess
import sys


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

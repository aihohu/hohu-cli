"""Verify transport fallback, directory ownership, and bounded Git execution."""

import os
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from hohu.config.components import RepositorySource, get_component_repo
from hohu.utils import repository
from hohu.utils.repository import RepositoryCloner, RepositoryError


@pytest.mark.parametrize("failure_stage", ["probe", "clone"])
def test_network_failure_switches_and_reuses_gitee(
    tmp_path, git_transport, failure_stage
):
    execute = git_transport.side_effect
    failed_checkouts = []

    def transport(args, *, timeout):
        if any("github.com" in arg for arg in args):
            if failure_stage == "probe" or "clone" in args:
                if "clone" in args:
                    checkout = Path(args[-1])
                    checkout.mkdir()
                    (checkout / "partial").write_text("partial")
                    failed_checkouts.append(checkout)
                raise RepositoryError("Connection reset", network=True)
        return execute(args, timeout=timeout)

    git_transport.side_effect = transport
    cloner = RepositoryCloner(RepositorySource.auto)
    backend = cloner.clone("Backend", tmp_path / "hohu-admin")
    frontend = cloner.clone("Frontend", tmp_path / "hohu-admin-web")
    mobile = cloner.clone("App", tmp_path / "hohu-admin-app")
    assert {backend["source"], frontend["source"], mobile["source"]} == {"gitee"}
    assert all(not path.exists() for path in failed_checkouts)
    assert list((tmp_path / ".hohu/tmp").iterdir()) == []
    github_calls = [
        call.args[0]
        for call in git_transport.call_args_list
        if any("github.com" in arg for arg in call.args[0])
    ]
    assert len(github_calls) == (1 if failure_stage == "probe" else 2)
    assert (tmp_path / "hohu-admin/README.md").read_text() == "fixture"
    assert not (tmp_path / "hohu-admin/partial").exists()


@pytest.mark.parametrize("source", [RepositorySource.github, RepositorySource.gitee])
def test_explicit_source_does_not_fallback(tmp_path, git_transport, source):
    git_transport.side_effect = RepositoryError("Connection reset", network=True)
    with pytest.raises(RepositoryError):
        RepositoryCloner(source).clone("Backend", tmp_path / "hohu-admin")
    assert git_transport.call_count == 1
    assert git_transport.call_args.args[0][-2] == get_component_repo("Backend", source)


def test_custom_failure_does_not_use_official_mirror(tmp_path, git_transport):
    git_transport.side_effect = RepositoryError("Connection reset", network=True)
    with pytest.raises(RepositoryError):
        RepositoryCloner(RepositorySource.auto).clone(
            "Backend", tmp_path / "hohu-admin", "https://example.invalid/private.git"
        )
    assert git_transport.call_count == 1
    assert "clone" in git_transport.call_args.args[0]
    assert list((tmp_path / ".hohu/tmp").iterdir()) == []


def test_non_network_failure_does_not_fallback(tmp_path, git_transport):
    git_transport.side_effect = RepositoryError("Permission denied")
    with pytest.raises(RepositoryError, match="Permission denied"):
        RepositoryCloner(RepositorySource.auto).clone(
            "Backend", tmp_path / "hohu-admin"
        )
    assert git_transport.call_count == 1


def test_official_main_is_selected_even_when_remote_head_differs(
    tmp_path, git_transport
):
    execute = git_transport.side_effect

    def transport(args, *, timeout):
        if "ls-remote" in args:
            return (
                "ref: refs/heads/feature/temporary\tHEAD\n"
                + "b" * 40
                + "\tHEAD\n"
                + "a" * 40
                + "\trefs/heads/main"
            )
        return execute(args, timeout=timeout)

    git_transport.side_effect = transport
    RepositoryCloner(RepositorySource.gitee).clone(
        "Frontend", tmp_path / "hohu-admin-web"
    )
    command = next(
        call.args[0] for call in git_transport.call_args_list if "clone" in call.args[0]
    )
    assert command[command.index("--branch") + 1] == "main"


def test_both_sources_report_their_failures(tmp_path, git_transport):
    git_transport.side_effect = [
        RepositoryError("primary timed out", network=True),
        RepositoryError("mirror not synchronized"),
    ]
    with pytest.raises(RepositoryError) as error:
        RepositoryCloner(RepositorySource.auto).clone(
            "Backend", tmp_path / "hohu-admin"
        )
    assert "primary timed out" in str(error.value)
    assert "mirror not synchronized" in str(error.value)
    assert not (tmp_path / "hohu-admin").exists()


@pytest.mark.parametrize(
    "output", ["", "a" * 40 + "\tHEAD", "ref: refs/heads/main\tHEAD"]
)
def test_empty_or_broken_default_branch_is_not_success(tmp_path, git_transport, output):
    git_transport.return_value = output
    git_transport.side_effect = None
    with pytest.raises(RepositoryError) as error:
        RepositoryCloner(RepositorySource.auto).clone(
            "Backend", tmp_path / "hohu-admin"
        )
    assert not error.value.network
    assert git_transport.call_count == 1
    assert not (tmp_path / "hohu-admin").exists()


def test_existing_destination_is_preserved(tmp_path, git_transport):
    target = tmp_path / "hohu-admin"
    target.mkdir()
    (target / "user.txt").write_text("keep")
    with pytest.raises(RepositoryError):
        repository._clone("repo", target, "custom")
    assert (target / "user.txt").read_text() == "keep"
    git_transport.assert_not_called()


def test_destination_created_during_clone_is_preserved(tmp_path, git_transport):
    execute = git_transport.side_effect
    target = tmp_path / "hohu-admin"

    def transport(args, *, timeout):
        output = execute(args, timeout=timeout)
        if "clone" in args:
            target.mkdir()
            (target / "user.txt").write_text("keep")
        return output

    git_transport.side_effect = transport
    with pytest.raises(RepositoryError):
        repository._clone("repo", target, "custom")
    assert (target / "user.txt").read_text() == "keep"
    assert list((tmp_path / ".hohu/tmp").iterdir()) == []


def test_invalid_checkout_is_cleaned(tmp_path, git_transport):
    execute = git_transport.side_effect

    def transport(args, *, timeout):
        return "HEAD" if "rev-parse" in args else execute(args, timeout=timeout)

    git_transport.side_effect = transport
    with pytest.raises(RepositoryError):
        repository._clone("repo", tmp_path / "hohu-admin", "custom")
    assert not (tmp_path / "hohu-admin").exists()
    assert list((tmp_path / ".hohu/tmp").iterdir()) == []


def test_official_branch_mismatch_is_not_published(tmp_path, git_transport):
    execute = git_transport.side_effect

    def transport(args, *, timeout):
        return (
            "feature/wrong"
            if "symbolic-ref" in args
            else execute(args, timeout=timeout)
        )

    git_transport.side_effect = transport
    with pytest.raises(RepositoryError) as error:
        RepositoryCloner(RepositorySource.github).clone(
            "Backend", tmp_path / "hohu-admin"
        )
    assert not error.value.network
    assert not (tmp_path / "hohu-admin").exists()
    assert list((tmp_path / ".hohu/tmp").iterdir()) == []


def test_custom_default_branch_is_not_forced_to_main(tmp_path, git_transport):
    execute = git_transport.side_effect

    def transport(args, *, timeout):
        return "develop" if "symbolic-ref" in args else execute(args, timeout=timeout)

    git_transport.side_effect = transport
    record = RepositoryCloner(RepositorySource.auto).clone(
        "Backend", tmp_path / "hohu-admin", "https://example.invalid/custom.git"
    )
    assert record["branch"] == "develop"
    command = next(
        call.args[0] for call in git_transport.call_args_list if "clone" in call.args[0]
    )
    assert "--branch" not in command


def test_transient_windows_sharing_conflict_is_retried(
    tmp_path, git_transport, monkeypatch
):
    rename = Path.rename
    calls = []
    sleep = Mock()
    monkeypatch.setattr(repository.time, "sleep", sleep)

    def retry_rename(path, destination):
        calls.append(path)
        if len(calls) == 1:
            error = PermissionError("temporary sharing conflict")
            error.winerror = 32
            raise error
        return rename(path, destination)

    monkeypatch.setattr(Path, "rename", retry_rename)
    repository._clone("repo", tmp_path / "hohu-admin", "custom")
    assert (tmp_path / "hohu-admin/README.md").read_text() == "fixture"
    sleep.assert_called_once_with(0.25)
    assert git_transport.call_count == 3


@pytest.mark.parametrize("winerror,expected_retries", [(32, 20), (5, 20)])
def test_publish_retry_is_bounded_and_local(
    tmp_path, git_transport, monkeypatch, winerror, expected_retries
):
    error = PermissionError("sharing or access error")
    error.winerror = winerror
    monkeypatch.setattr(Path, "rename", Mock(side_effect=error))
    sleep = Mock()
    monkeypatch.setattr(repository.time, "sleep", sleep)
    RepositoryCloner(RepositorySource.auto).clone("Backend", tmp_path / "hohu-admin")
    assert (tmp_path / "hohu-admin/README.md").read_text() == "fixture"
    assert sleep.call_count == expected_retries
    assert all("gitee.com" not in str(call) for call in git_transport.call_args_list)
    assert list((tmp_path / ".hohu/tmp").iterdir()) == []


def test_other_publish_errors_do_not_copy_or_switch_source(
    tmp_path, git_transport, monkeypatch
):
    error = PermissionError("invalid local operation")
    error.winerror = 87
    monkeypatch.setattr(Path, "rename", Mock(side_effect=error))
    copy = Mock()
    monkeypatch.setattr(repository.shutil, "copytree", copy)
    with pytest.raises(PermissionError):
        RepositoryCloner(RepositorySource.auto).clone(
            "Backend", tmp_path / "hohu-admin"
        )
    copy.assert_not_called()
    assert all("gitee.com" not in str(call) for call in git_transport.call_args_list)


def test_failed_copy_cleans_only_owned_destination(tmp_path, monkeypatch):
    checkout = tmp_path / ".hohu/tmp/checkout"
    checkout.mkdir(parents=True)
    foreign = tmp_path / "existing"
    foreign.mkdir()
    (foreign / "keep").write_text("keep")

    def fail_copy(_source, target, **_kwargs):
        (target / "partial").write_text("partial")
        raise OSError("disk full")

    monkeypatch.setattr(repository.shutil, "copytree", fail_copy)
    with pytest.raises(OSError):
        repository._copy_checkout(checkout, tmp_path / "hohu-admin")
    assert not (tmp_path / "hohu-admin").exists()
    assert (foreign / "keep").read_text() == "keep"
    with pytest.raises(FileExistsError):
        repository._copy_checkout(checkout, foreign)
    assert (foreign / "keep").read_text() == "keep"


def test_local_metadata_timeout_is_not_network_failure(git_process, monkeypatch):
    process, _ = git_process
    process.communicate.side_effect = [subprocess.TimeoutExpired("git", 8), (b"", b"")]
    monkeypatch.setattr(repository.subprocess, "run", Mock())
    monkeypatch.setattr(repository.os, "killpg", Mock(), raising=False)
    with pytest.raises(RepositoryError) as error:
        repository._run_git(["-C", "checkout", "rev-parse", "HEAD"], timeout=8)
    assert not error.value.network


def test_owned_readonly_cleanup_does_not_change_symlink_targets(tmp_path):
    target = tmp_path / "outside"
    target.write_text("keep")
    link = tmp_path / "link"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("File symlinks require OS support")
    before = target.stat().st_mode
    error = PermissionError("cannot remove link")
    with pytest.raises(PermissionError):
        repository._remove_readonly(Mock(), str(link), (PermissionError, error, None))
    assert target.stat().st_mode == before
    assert target.read_text() == "keep"


def test_owned_readonly_cleanup_retries_only_permission_errors(tmp_path):
    path = tmp_path / "owned"
    path.write_text("owned")
    function = Mock()
    error = PermissionError("readonly")
    repository._remove_readonly(function, str(path), (PermissionError, error, None))
    function.assert_called_once_with(str(path))
    with pytest.raises(OSError, match="disk error"):
        repository._remove_readonly(
            function, str(path), (OSError, OSError("disk error"), None)
        )


def test_temporary_symlink_cannot_escape_project(tmp_path, git_transport):
    project, outside = tmp_path / "project", tmp_path / "outside"
    (project / ".hohu").mkdir(parents=True)
    outside.mkdir()
    try:
        (project / ".hohu/tmp").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlinks require OS support")
    with pytest.raises(RepositoryError):
        repository._clone("repo", project / "hohu-admin", "custom")
    assert list(outside.iterdir()) == []
    git_transport.assert_not_called()


@pytest.mark.parametrize(
    "message,expected",
    [
        ("Could not resolve host: github.com", True),
        ("Connection reset by peer", True),
        ("fatal: early EOF", True),
        ("RPC failed; HTTP 503", True),
        ("schannel: SEC_E_NO_CREDENTIALS", True),
        ("Authentication failed", False),
        ("Permission denied", False),
        ("No space left on device", False),
        ("RPC failed; requested URL returned error: 403", False),
        ("Repository not found", False),
        ("Unexpected local failure", False),
    ],
)
def test_transport_error_classification(message, expected):
    assert repository.is_network_failure(message) is expected


def test_credentials_are_not_persisted_or_displayed(tmp_path, git_transport):
    url = "https://username:secret@example.invalid/repo.git?token=private"
    record = repository._clone(url, tmp_path / "hohu-admin", "custom")
    assert git_transport.call_count == 3
    assert "secret" not in record["repository"]
    assert "private" not in record["repository"]
    assert "username" not in record["repository"]


@pytest.fixture
def git_process(monkeypatch):
    process = Mock()
    process.returncode = 0
    process.pid = 12345
    process.poll.return_value = None
    process.communicate.return_value = (b"output", b"")
    popen = Mock(return_value=process)
    monkeypatch.setattr(repository.shutil, "which", lambda name: "/git")
    monkeypatch.setattr(repository.subprocess, "Popen", popen)
    return process, popen


def test_git_execution_does_not_parse_shell_or_prompt(git_process):
    _, popen = git_process
    assert (
        repository._run_git(["clone", "--", "repo; touch injected", "path"], timeout=8)
        == "output"
    )
    assert popen.call_args.args[0] == [
        "/git",
        "clone",
        "--",
        "repo; touch injected",
        "path",
    ]
    assert popen.call_args.kwargs["shell"] is False
    env = popen.call_args.kwargs["env"]
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GCM_INTERACTIVE"] == "never"
    assert "http.sslVerify=false" not in str(popen.call_args)


def test_git_stderr_classification_and_redaction(git_process):
    process, _ = git_process
    process.returncode = 128
    process.communicate.return_value = (
        b"",
        b"Connection reset: https://user:secret@example.invalid/repo",
    )
    with pytest.raises(RepositoryError) as error:
        repository._run_git(["clone", "repo"], timeout=8)
    assert error.value.network
    assert "secret" not in str(error.value)


@pytest.mark.parametrize(
    "interruption", [subprocess.TimeoutExpired("git", 8), KeyboardInterrupt()]
)
def test_timeout_and_cancel_stop_owned_process_tree(
    git_process, monkeypatch, interruption
):
    process, _ = git_process
    process.communicate.side_effect = [interruption, (b"", b"")]
    stop_windows = Mock()
    stop_posix = Mock()
    monkeypatch.setattr(repository.subprocess, "run", stop_windows)
    monkeypatch.setattr(repository.os, "killpg", stop_posix, raising=False)
    expected = (
        RepositoryError
        if isinstance(interruption, subprocess.TimeoutExpired)
        else KeyboardInterrupt
    )
    with pytest.raises(expected):
        repository._run_git(["ls-remote", "repo"], timeout=8)
    if os.name == "nt":
        assert stop_windows.call_args.args[0] == [
            "taskkill",
            "/PID",
            "12345",
            "/T",
            "/F",
        ]
    else:
        assert stop_posix.call_args.args[0] == 12345
    assert process.communicate.call_args.kwargs["timeout"] == 5


def test_missing_git_is_not_retried(monkeypatch):
    monkeypatch.setattr(repository.shutil, "which", lambda name: None)
    with pytest.raises(RepositoryError) as error:
        repository._run_git(["ls-remote", "repo"], timeout=8)
    assert not error.value.network

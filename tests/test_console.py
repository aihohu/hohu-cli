"""Verify output fallback preserves stream contracts."""

import io

import pytest

from hohu.utils.console import configure_output_streams


@pytest.mark.parametrize("encoding", ["cp936", "utf-8"])
@pytest.mark.parametrize("errors", ["strict", "replace"])
def test_preserve_encoding_and_explicit_error_policy(monkeypatch, encoding, errors):
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding=encoding, errors=errors)
    monkeypatch.setattr("sys.stdout", stream)
    monkeypatch.setattr("sys.stderr", stream)
    configure_output_streams()
    configure_output_streams()
    assert stream.encoding == encoding
    expected = (
        "backslashreplace" if encoding == "cp936" and errors == "strict" else errors
    )
    assert stream.errors == expected
    stream.write("中文 🚚")
    stream.flush()
    output = buffer.getvalue().decode(encoding)
    assert "中文" in output
    if encoding == "utf-8":
        assert "🚚" in output


def test_capture_streams_without_reconfigure_are_supported(monkeypatch):
    stream = io.StringIO()
    monkeypatch.setattr("sys.stdout", stream)
    monkeypatch.setattr("sys.stderr", None)
    configure_output_streams()
    stream.write("🚚")
    assert stream.getvalue() == "🚚"

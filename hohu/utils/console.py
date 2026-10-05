"""Keep CLI output writable on legacy encoded streams."""

import codecs
import sys


def configure_output_streams() -> None:
    """Escape unsupported characters without changing the receiver's encoding."""
    for stream in (sys.stdout, sys.stderr):
        encoding = getattr(stream, "encoding", None)
        reconfigure = getattr(stream, "reconfigure", None)
        if not encoding or not callable(reconfigure):
            continue
        if codecs.lookup(encoding).name == "utf-8":
            continue
        # Surrogate handlers still reject ordinary unencodable Unicode characters.
        if getattr(stream, "errors", None) in {
            "strict",
            "surrogateescape",
            "surrogatepass",
        }:
            reconfigure(errors="backslashreplace")

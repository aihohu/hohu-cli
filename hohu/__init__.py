from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("hohu")
except PackageNotFoundError:
    __version__ = "unknown"

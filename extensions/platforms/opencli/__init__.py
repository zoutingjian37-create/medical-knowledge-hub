"""Thin integration with the Apache-2.0 OpenCLI collection engine."""

from .adapter import OPENCLI_ADAPTER_VERSION, OpenCLIAdapter
from .runner import OpenCLIRunner, OpenCLIStatus

__all__ = [
    "OPENCLI_ADAPTER_VERSION",
    "OpenCLIAdapter",
    "OpenCLIRunner",
    "OpenCLIStatus",
]

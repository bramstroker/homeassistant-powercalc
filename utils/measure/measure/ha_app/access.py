"""Access policy shared by the app factory and standalone entry point."""

from ipaddress import ip_address
import os


def trusted_ingress_only_enabled() -> bool:
    """Require ingress unless local access was explicitly enabled."""
    return os.environ.get("MEASURE_TRUSTED_INGRESS_ONLY", "true").lower() != "false"


def is_loopback_address(host: str | None) -> bool:
    """Accept literal loopback addresses without trusting DNS or proxy headers."""
    if host is None:
        return False
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False

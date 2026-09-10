"""Shared profile metadata and output helpers.

This package deliberately has no Home Assistant or GitHub dependencies. Both the
interactive CLI and the browser contribution flow use these models before choosing
how a prepared profile is delivered.
"""

from measure.profile.models import ProfileAuthor, ProfileMetadata

__all__ = ["ProfileAuthor", "ProfileMetadata"]

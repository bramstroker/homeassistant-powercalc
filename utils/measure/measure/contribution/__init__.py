"""Engine for contributing measured power profiles to the upstream profile library.

Flow: ``ProfilePreparer`` validates the measurement artifacts and renders the files
for a preview, ``ContributionJobCoordinator`` persists that preview as a job in the
``ContributionJobStore`` and later submits it through ``GitHubClient`` (fork, branch,
commit, pull request). This package is UI-agnostic; ``measure.ha_app.contribution``
wraps it with the HTTP-facing auth flows, drafts, and app-level state.
"""

from __future__ import annotations

from measure.contribution.coordinator import (
    ContributionJobCoordinator,
    ContributionJobExpiredError,
    ContributionJobStore,
)
from measure.contribution.credentials import CredentialStore
from measure.contribution.github import GitHubClient
from measure.contribution.models import (
    ContributionAuthor,
    ContributionError,
    ContributionErrorCode,
    ContributionJob,
    ContributionJobStatus,
    ContributionMetadata,
    ContributionPreparedFile,
    ContributionPreview,
    ContributionSubmission,
)
from measure.contribution.prepare import ProfilePreparer

__all__ = [
    "ContributionAuthor",
    "ContributionError",
    "ContributionErrorCode",
    "ContributionJob",
    "ContributionJobCoordinator",
    "ContributionJobExpiredError",
    "ContributionJobStatus",
    "ContributionJobStore",
    "ContributionMetadata",
    "ContributionPreparedFile",
    "ContributionPreview",
    "ContributionSubmission",
    "CredentialStore",
    "GitHubClient",
    "ProfilePreparer",
]

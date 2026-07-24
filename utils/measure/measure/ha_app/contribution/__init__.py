"""HTTP-facing layer over ``measure.contribution`` for the Home Assistant app.

Adds what the API needs on top of the core engine: GitHub auth (PAT and OAuth
device flow), draft/preview responses for the frontend, and the app-level
``ContributionState`` persisted per install by ``ContributionApiCoordinator``.
"""

from __future__ import annotations

from measure.ha_app.contribution.coordinator import ContributionApiCoordinator
from measure.ha_app.contribution.models import (
    SUPPORTED_MEASURE_TYPES,
    ConnectPatRequest,
    ContributionApiError,
    ContributionApiErrorCode,
    ContributionAuthMethod,
    ContributionAuthStatus,
    ContributionFile,
    ContributionIdentity,
    ContributionPreviewRequest,
    ContributionPreviewResponse,
    ContributionService,
    ContributionServiceFactory,
    ContributionState,
    ContributionStatus,
    ContributionSubmissionResult,
    ContributionSubmitRequest,
    DeviceFlowPollResponse,
    DeviceFlowStart,
    DeviceFlowStartResponse,
)
from measure.ha_app.contribution.service import SharedContributionService, create_contribution_service

__all__ = [
    "SUPPORTED_MEASURE_TYPES",
    "ConnectPatRequest",
    "ContributionApiCoordinator",
    "ContributionApiError",
    "ContributionApiErrorCode",
    "ContributionAuthMethod",
    "ContributionAuthStatus",
    "ContributionFile",
    "ContributionIdentity",
    "ContributionPreviewRequest",
    "ContributionPreviewResponse",
    "ContributionService",
    "ContributionServiceFactory",
    "ContributionState",
    "ContributionStatus",
    "ContributionSubmissionResult",
    "ContributionSubmitRequest",
    "DeviceFlowPollResponse",
    "DeviceFlowStart",
    "DeviceFlowStartResponse",
    "SharedContributionService",
    "create_contribution_service",
]

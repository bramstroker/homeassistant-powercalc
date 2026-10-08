"""GitHub authentication flows for the measurement app."""

from pydantic import SecretStr

from measure.contribution.credentials import CredentialKind, CredentialStore, StoredCredential
from measure.contribution.github import (
    REQUIRED_OAUTH_SCOPES,
    GitHubApiError,
    GitHubClient,
    missing_required_scopes,
)
from measure.ha_app.contribution.models import (
    ContributionApiError,
    ContributionApiErrorCode,
    ContributionAuthMethod,
    ContributionAuthStatus,
    ContributionIdentity,
    DeviceFlowPollResponse,
    DeviceFlowPollStatus,
    DeviceFlowStart,
)


class ContributionAuth:
    """Authenticate GitHub users and persist their granted credentials."""

    def __init__(self, credential_store: CredentialStore) -> None:
        self._credential_store = credential_store

    def auth_status(self) -> ContributionAuthStatus:
        credential = self._credential_store.load()
        if credential is None:
            return ContributionAuthStatus(authenticated=False, connected=False)
        return ContributionAuthStatus(
            authenticated=True,
            connected=True,
            method=ContributionAuthMethod.OAUTH_DEVICE
            if credential.kind == CredentialKind.OAUTH
            else ContributionAuthMethod.PAT,
            identity=ContributionIdentity(login=credential.github_username or ""),
            username=credential.github_username,
            scopes=list(credential.scopes),
            permissions_verified=credential.permissions_verified,
        )

    def connect_pat(self, token: SecretStr) -> ContributionAuthStatus:
        raw_token = token.get_secret_value()
        try:
            user = GitHubClient(raw_token).fetch_authenticated_user()
        except GitHubApiError as error:
            raise ContributionApiError(ContributionApiErrorCode.AUTH_UNAVAILABLE, str(error)) from error
        permission_granted = not missing_required_scopes(user.scopes)
        if user.scopes_reported and not permission_granted:
            raise ContributionApiError(
                ContributionApiErrorCode.AUTH_UNAVAILABLE,
                "The GitHub token must grant public repository and workflow access",
            )
        self._credential_store.save(
            StoredCredential(
                kind=CredentialKind.PAT,
                token=raw_token,
                github_username=user.login,
                scopes=user.scopes,
                permissions_verified=permission_granted,
            ),
        )
        return self.auth_status()

    def disconnect(self) -> ContributionAuthStatus:
        self._credential_store.clear()
        return self.auth_status()

    def start_device_flow(self, client_id: str) -> DeviceFlowStart:
        try:
            data = GitHubClient().start_device_flow(client_id, REQUIRED_OAUTH_SCOPES)
        except GitHubApiError as error:
            raise ContributionApiError(ContributionApiErrorCode.AUTH_UNAVAILABLE, str(error)) from error
        complete_uri = data.get("verification_uri_complete")
        return DeviceFlowStart(
            device_code=str(data["device_code"]),
            user_code=str(data["user_code"]),
            verification_uri=str(data["verification_uri"]),
            verification_uri_complete=str(complete_uri) if complete_uri is not None else None,
            expires_in=int(data["expires_in"]),
            interval=int(data["interval"]),
            message=f"Enter code {data['user_code']} at {data['verification_uri']}",
        )

    def poll_device_flow(self, client_id: str, device_code: str) -> DeviceFlowPollResponse:
        try:
            data = GitHubClient().poll_device_flow(client_id, device_code)
        except GitHubApiError as error:
            raise ContributionApiError(ContributionApiErrorCode.AUTH_UNAVAILABLE, str(error)) from error
        oauth_error = data.get("error")
        if oauth_error == "authorization_pending":
            return DeviceFlowPollResponse(
                status=DeviceFlowPollStatus.PENDING,
                message=str(data.get("error_description") or "Authorization pending"),
            )
        if oauth_error == "slow_down":
            return DeviceFlowPollResponse(
                status=DeviceFlowPollStatus.SLOW_DOWN,
                message=str(data.get("error_description") or "Authorization pending"),
                retry_after=_positive_integer(data.get("interval")),
            )
        if oauth_error in {"expired_token", "access_denied"}:
            return DeviceFlowPollResponse(
                status=DeviceFlowPollStatus.EXPIRED if oauth_error == "expired_token" else DeviceFlowPollStatus.DENIED,
                message=str(data.get("error_description") or oauth_error),
            )
        token = data.get("access_token")
        if not isinstance(token, str) or not token:
            raise ContributionApiError(
                ContributionApiErrorCode.AUTH_UNAVAILABLE,
                "GitHub Device Flow did not return an access token",
            )
        try:
            user = GitHubClient(token).fetch_authenticated_user()
        except GitHubApiError as auth_error:
            raise ContributionApiError(ContributionApiErrorCode.AUTH_UNAVAILABLE, str(auth_error)) from auth_error
        response_scopes = tuple(scope for scope in str(data.get("scope", "")).split() if scope)
        # Record what GitHub actually granted. Claiming the required scopes here would
        # mark the credential verified while submission later fails on a missing scope.
        granted = user.scopes or response_scopes
        self._credential_store.save(
            StoredCredential(
                kind=CredentialKind.OAUTH,
                token=token,
                github_username=user.login,
                scopes=granted,
                permissions_verified=not missing_required_scopes(granted),
            ),
        )
        return DeviceFlowPollResponse(status=DeviceFlowPollStatus.AUTHORIZED, auth=self.auth_status())


def _positive_integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdecimal():
            parsed = int(stripped)
            return parsed if parsed > 0 else None
    return None

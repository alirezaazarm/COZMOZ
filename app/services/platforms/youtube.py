from __future__ import annotations
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Mapping, MutableMapping, Sequence
from urllib.parse import urlencode
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as UserCredentials
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import Flow

logger = logging.getLogger(__name__)


# We need write access to replies. This is broader than readonly but is the relevant
# documented scope for reading/writing YouTube comments and channel-owned data.
YOUTUBE_FORCE_SSL_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"

# Current documented quota costs for methods used by this service. These are kept in one
# place so scheduling/observability code can reason about daily budget without hardcoding
# numbers in multiple modules. The 10,000-unit default bucket is a project-level quota,
# not a per-channel allocation.
QUOTA_COSTS: dict[str, int] = {
    "channels.list": 1,
    "playlistItems.list": 1,
    "videos.list": 1,
    "commentThreads.list": 1,
    "comments.list": 1,
    "comments.insert": 50,
    "comments.delete": 50,
    "comments.update": 50,
    "comments.setModerationStatus": 50,
}
DEFAULT_DAILY_QUOTA_UNITS = 10_000

# API / OAuth endpoints.
GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"
YOUTUBE_API_SERVICE = "youtube"
YOUTUBE_API_VERSION = "v3"


class YouTubeServiceError(Exception):
    """Base exception for service-layer errors."""


class YouTubeOAuthError(YouTubeServiceError):
    """OAuth configuration, callback, token, or authorization error."""


class YouTubeAPIError(YouTubeServiceError):
    """Non-retryable or exhausted YouTube API error."""

    def __init__(self, message: str, *, status_code: int | None = None, reason: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.reason = reason


class YouTubeRateLimitError(YouTubeAPIError):
    """HTTP/API rate-limit or quota exhaustion response."""


@dataclass(frozen=True)
class YouTubeOAuthConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: tuple[str, ...] = (YOUTUBE_FORCE_SSL_SCOPE,)

    @classmethod
    def from_env(cls) -> "YouTubeOAuthConfig":
        client_id = os.getenv("YOUTUBE_CLIENT_ID")
        client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
        redirect_uri = os.getenv("YOUTUBE_REDIRECT_URI")
        if not client_id or not client_secret or not redirect_uri:
            raise YouTubeOAuthError(
                "Missing YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, or YOUTUBE_REDIRECT_URI"
            )
        return cls(client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri)


@dataclass
class OAuthTokens:
    """Persistable OAuth token payload.

    Only refresh_token needs long-term persistence for normal server-side operation.
    access_token is short-lived and can be refreshed when needed.
    """

    access_token: str
    refresh_token: str | None
    token_type: str = "Bearer"
    expires_in: int | None = None
    expires_at: float | None = None
    scope: str | None = None
    refresh_token_expires_in: int | None = None
    refresh_token_expires_at: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_google_response(cls, payload: Mapping[str, Any], *, existing_refresh_token: str | None = None) -> "OAuthTokens":
        now = time.time()
        expires_in = payload.get("expires_in")
        refresh_expires_in = payload.get("refresh_token_expires_in")
        refresh_token = payload.get("refresh_token") or existing_refresh_token
        return cls(
            access_token=str(payload["access_token"]),
            refresh_token=refresh_token,
            token_type=str(payload.get("token_type", "Bearer")),
            expires_in=int(expires_in) if expires_in is not None else None,
            expires_at=now + int(expires_in) if expires_in is not None else None,
            scope=payload.get("scope"),
            refresh_token_expires_in=int(refresh_expires_in) if refresh_expires_in is not None else None,
            refresh_token_expires_at=now + int(refresh_expires_in) if refresh_expires_in is not None else None,
            extra={k: v for k, v in payload.items() if k not in {
                "access_token", "refresh_token", "token_type", "expires_in", "scope", "refresh_token_expires_in"
            }},
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "OAuthTokens":
        return cls(
            access_token=str(data["access_token"]),
            refresh_token=data.get("refresh_token"),
            token_type=str(data.get("token_type", "Bearer")),
            expires_in=data.get("expires_in"),
            expires_at=data.get("expires_at"),
            scope=data.get("scope"),
            refresh_token_expires_in=data.get("refresh_token_expires_in"),
            refresh_token_expires_at=data.get("refresh_token_expires_at"),
            extra=dict(data.get("extra", {})),
        )

    def to_mapping(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
            "expires_at": self.expires_at,
            "scope": self.scope,
            "refresh_token_expires_in": self.refresh_token_expires_in,
            "refresh_token_expires_at": self.refresh_token_expires_at,
            "extra": dict(self.extra),
        }
        return data


@dataclass(frozen=True)
class OAuthCallbackResult:
    tokens: OAuthTokens
    granted_scopes: tuple[str, ...]


@dataclass(frozen=True)
class YouTubeAPISettings:
    max_retries: int = 4
    initial_retry_delay: float = 0.75
    max_retry_delay: float = 8.0
    request_timeout: float | None = None  # googleapiclient uses urllib; kept for config compatibility.
    user_agent: str = "youtube-saas-service/1.0"


class YouTubeService:
    """YouTube Data API v3 service optimized for low quota consumption.

    The class is intentionally stateless with respect to tenants. Construct one instance
    per API operation/worker using the tenant's OAuth credentials. Persist the refresh
    token outside this class (e.g. encrypted MongoDB field).

    Example:
        service = YouTubeService.from_token_dict(token_dict)
        channel = service.get_authenticated_channel()
        videos = list(service.iter_channel_videos(channel["id"]))
        comments = list(service.iter_video_comments(videos[0]["id"], max_pages=2))
        service.reply_to_comment(comments[0]["id"], "Thanks!")
    """

    def __init__(
        self,
        *,
        credentials: Credentials | Mapping[str, Any],
        api_settings: YouTubeAPISettings | None = None,
        api_key: str | None = None,
    ) -> None:
        self.settings = api_settings or YouTubeAPISettings()
        self.api_key = api_key
        self._credentials = self._coerce_credentials(credentials)
        self._youtube: Resource | None = None
        self._uploads_playlist_cache: dict[str, str] = {}

    @classmethod
    def from_token_dict(
        cls,
        token_data: Mapping[str, Any],
        *,
        oauth_config: YouTubeOAuthConfig | None = None,
        api_settings: YouTubeAPISettings | None = None,
        api_key: str | None = None,
    ) -> "YouTubeService":
        config = oauth_config or YouTubeOAuthConfig.from_env()
        credentials = UserCredentials(
            token=token_data.get("access_token") or token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=GOOGLE_TOKEN_ENDPOINT,
            client_id=config.client_id,
            client_secret=config.client_secret,
            scopes=token_data.get("scope", "").split() or list(config.scopes),
        )
        if token_data.get("expires_at"):
            from datetime import timedelta
            credentials.expiry = datetime.fromtimestamp(float(token_data["expires_at"]), tz=timezone.utc)
        return cls(credentials=credentials, api_settings=api_settings, api_key=api_key)

    @classmethod
    def from_refresh_token(
        cls,
        refresh_token: str,
        *,
        oauth_config: YouTubeOAuthConfig | None = None,
        api_settings: YouTubeAPISettings | None = None,
        api_key: str | None = None,
    ) -> "YouTubeService":
        config = oauth_config or YouTubeOAuthConfig.from_env()
        credentials = UserCredentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=GOOGLE_TOKEN_ENDPOINT,
            client_id=config.client_id,
            client_secret=config.client_secret,
            scopes=list(config.scopes),
        )
        return cls(credentials=credentials, api_settings=api_settings, api_key=api_key)

    @staticmethod
    def _coerce_credentials(credentials: Credentials | Mapping[str, Any]) -> Credentials:
        if isinstance(credentials, Mapping):
            config = YouTubeOAuthConfig.from_env()
            return UserCredentials(
                token=credentials.get("access_token") or credentials.get("token"),
                refresh_token=credentials.get("refresh_token"),
                token_uri=GOOGLE_TOKEN_ENDPOINT,
                client_id=config.client_id,
                client_secret=config.client_secret,
                scopes=credentials.get("scope", "").split() or list(config.scopes),
            )
        return credentials

    @staticmethod
    def _parse_http_error(error: HttpError) -> tuple[int | None, str | None, str]:
        status = getattr(error.resp, "status", None)
        reason: str | None = None
        message = str(error)
        try:
            content = error.content.decode("utf-8") if isinstance(error.content, (bytes, bytearray)) else str(error.content)
            payload = json.loads(content)
            errors = payload.get("error", {}).get("errors", [])
            if errors:
                reason = errors[0].get("reason")
                message = errors[0].get("message") or payload.get("error", {}).get("message") or message
            else:
                message = payload.get("error", {}).get("message") or message
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
        return status, reason, message

    @staticmethod
    def _is_retryable_http_error(error: HttpError) -> bool:
        status = getattr(error.resp, "status", None)
        if status in {408, 429, 500, 502, 503, 504}:
            return True
        try:
            content = error.content.decode("utf-8") if isinstance(error.content, (bytes, bytearray)) else str(error.content)
            payload = json.loads(content)
            reason = ((payload.get("error", {}).get("errors") or [{}])[0]).get("reason")
            return reason in {"backendError", "internalError", "rateLimitExceeded", "userRateLimitExceeded"}
        except Exception:
            return False

    def _ensure_credentials(self) -> None:
        if not self._credentials:
            raise YouTubeOAuthError("YouTube credentials are missing")
        if not self._credentials.valid:
            if getattr(self._credentials, "refresh_token", None):
                request = Request()
                self._credentials.refresh(request)
            else:
                raise YouTubeOAuthError("Access token is invalid/expired and no refresh token is available")

    def _client(self) -> Resource:
        self._ensure_credentials()
        if self._youtube is None:
            self._youtube = build(
                YOUTUBE_API_SERVICE,
                YOUTUBE_API_VERSION,
                credentials=self._credentials,
                developerKey=self.api_key,
                cache_discovery=False,
            )
        return self._youtube

    def _execute(self, request: Any) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                return request.execute(num_retries=0)
            except HttpError as exc:
                last_error = exc
                if not self._is_retryable_http_error(exc) or attempt >= self.settings.max_retries:
                    status, reason, message = self._parse_http_error(exc)
                    if status == 429 or reason in {"quotaExceeded", "dailyLimitExceeded", "userRateLimitExceeded", "rateLimitExceeded"}:
                        raise YouTubeRateLimitError(message, status_code=status, reason=reason) from exc
                    raise YouTubeAPIError(message, status_code=status, reason=reason) from exc
                delay = min(
                    self.settings.max_retry_delay,
                    self.settings.initial_retry_delay * (2 ** attempt),
                )
                delay *= 0.75 + (uuid.uuid4().int % 500) / 1000.0  # light jitter, no extra API call.
                logger.warning("Retrying YouTube API request after %s (attempt %s/%s)", exc, attempt + 1, self.settings.max_retries)
                time.sleep(delay)
            except Exception as exc:
                last_error = exc
                if attempt >= self.settings.max_retries:
                    raise YouTubeAPIError(f"Unexpected YouTube API client error: {exc}") from exc
                delay = min(self.settings.max_retry_delay, self.settings.initial_retry_delay * (2 ** attempt))
                time.sleep(delay)
        raise YouTubeAPIError(f"YouTube API request failed: {last_error}") from last_error

    # -------------------------------------------------------------------------
    # OAuth
    # -------------------------------------------------------------------------

    @staticmethod
    def build_oauth_flow(config: YouTubeOAuthConfig | None = None) -> Flow:
        config = config or YouTubeOAuthConfig.from_env()
        client_config = {
            "web": {
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "auth_uri": GOOGLE_AUTH_ENDPOINT,
                "token_uri": GOOGLE_TOKEN_ENDPOINT,
                "redirect_uris": [config.redirect_uri],
            }
        }
        flow = Flow.from_client_config(client_config, scopes=list(config.scopes), redirect_uri=config.redirect_uri)
        return flow

    @staticmethod
    def generate_oauth_state() -> str:
        """Generate a cryptographically random OAuth state value.

        The caller must store it server-side (session/DB/cache) and validate the exact
        value on callback. The state must not contain secrets or access tokens.
        """
        import secrets
        return secrets.token_urlsafe(32)

    @classmethod
    def get_authorization_url(
        cls,
        *,
        state: str,
        config: YouTubeOAuthConfig | None = None,
        login_hint: str | None = None,
        prompt: str | None = None,
    ) -> str:
        """Build Google OAuth URL.

        Caller must generate/store a cryptographically random state value associated with
        the signed-in SaaS user/session and validate it on callback.

        ``prompt=consent`` is useful when you explicitly need a new refresh token, but
        should not be forced for every reconnect because Google may otherwise issue
        unnecessary new grants/tokens.
        """
        config = config or YouTubeOAuthConfig.from_env()
        params: dict[str, str] = {
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "response_type": "code",
            "scope": " ".join(config.scopes),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "state": state,
        }
        if login_hint:
            params["login_hint"] = login_hint
        if prompt:
            params["prompt"] = prompt
        return f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"

    @classmethod
    def exchange_authorization_code(
        cls,
        code: str,
        *,
        config: YouTubeOAuthConfig | None = None,
        existing_refresh_token: str | None = None,
    ) -> OAuthCallbackResult:
        """Exchange callback code for OAuth tokens using Google's official client library."""
        config = config or YouTubeOAuthConfig.from_env()
        flow = cls.build_oauth_flow(config)
        try:
            flow.fetch_token(code=code)
        except Exception as exc:
            raise YouTubeOAuthError(f"Failed to exchange YouTube OAuth code: {exc}") from exc

        creds = flow.credentials
        granted_scopes = tuple(creds.scopes or config.scopes)
        # google-auth-oauthlib does not expose expires_in directly, but expiry is available.
        expires_at = creds.expiry.timestamp() if creds.expiry else None
        tokens = OAuthTokens(
            access_token=creds.token,
            refresh_token=creds.refresh_token or existing_refresh_token,
            token_type="Bearer",
            expires_at=expires_at,
            scope=" ".join(granted_scopes),
        )
        return OAuthCallbackResult(tokens=tokens, granted_scopes=granted_scopes)

    @classmethod
    def refresh_tokens(
        cls,
        refresh_token: str,
        *,
        config: YouTubeOAuthConfig | None = None,
        previous_tokens: OAuthTokens | None = None,
    ) -> OAuthTokens:
        config = config or YouTubeOAuthConfig.from_env()
        credentials = UserCredentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=GOOGLE_TOKEN_ENDPOINT,
            client_id=config.client_id,
            client_secret=config.client_secret,
            scopes=list(config.scopes),
        )
        try:
            credentials.refresh(Request())
        except Exception as exc:
            raise YouTubeOAuthError(f"Failed to refresh YouTube OAuth token: {exc}") from exc

        payload: dict[str, Any] = {
            "access_token": credentials.token,
            "token_type": "Bearer",
            "scope": " ".join(credentials.scopes or config.scopes),
        }
        expires_in = None
        if credentials.expiry:
            expires_in = max(0, int(credentials.expiry.timestamp() - time.time()))
            payload["expires_in"] = expires_in
        return OAuthTokens.from_google_response(payload, existing_refresh_token=(previous_tokens.refresh_token if previous_tokens else refresh_token))

    @classmethod
    def revoke_token(cls, token: str) -> None:
        """Revoke an access/refresh token. OAuth operation; no YouTube Data API quota."""
        import requests

        try:
            response = requests.post(
                GOOGLE_REVOKE_ENDPOINT,
                params={"token": token},
                timeout=15,
            )
        except requests.RequestException as exc:
            raise YouTubeOAuthError(f"Failed to reach Google token revocation endpoint: {exc}") from exc
        if response.status_code not in {200, 204}:
            raise YouTubeOAuthError(
                f"Google token revocation failed: HTTP {response.status_code}: {response.text[:500]}"
            )

    # -------------------------------------------------------------------------
    # Authentication / channel identity
    # -------------------------------------------------------------------------

    def get_authenticated_channels(self) -> list[dict[str, Any]]:
        """Return channels available to the authenticated account in one quota call."""
        request = self._client().channels().list(
            part="id,snippet,contentDetails,statistics,brandingSettings",
            mine=True,
            maxResults=50,
        )
        payload = self._execute(request)
        return list(payload.get("items", []))

    def get_authenticated_channel(self) -> dict[str, Any]:
        """Return the single channel or raise when multiple channels need explicit selection."""
        channels = self.get_authenticated_channels()
        if not channels:
            raise YouTubeAPIError("Authenticated Google account has no accessible YouTube channel")
        if len(channels) > 1:
            raise YouTubeAPIError(
                "Multiple YouTube channels are accessible. Use get_authenticated_channels() and let the user select one."
            )
        return channels[0]

    def get_channel_info(self, channel_id: str) -> dict[str, Any]:
        """Fetch a specific public channel by ID; one quota call."""
        self._validate_id(channel_id, "channel_id")
        request = self._client().channels().list(
            part="id,snippet,contentDetails,statistics,brandingSettings",
            id=channel_id,
            maxResults=1,
        )
        payload = self._execute(request)
        items = payload.get("items", [])
        if not items:
            raise YouTubeAPIError(f"Channel not found: {channel_id}", status_code=404)
        return items[0]

    def get_uploads_playlist_id(self, channel_id: str) -> str:
        """Get uploads playlist ID from channel.contentDetails; cached per service instance."""
        self._validate_id(channel_id, "channel_id")
        cached = self._uploads_playlist_cache.get(channel_id)
        if cached:
            return cached
        channel = self.get_channel_info(channel_id)
        try:
            playlist_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]
            self._uploads_playlist_cache[channel_id] = playlist_id
            return playlist_id
        except KeyError as exc:
            raise YouTubeAPIError(f"Uploads playlist not available for channel: {channel_id}") from exc

    # -------------------------------------------------------------------------
    # Videos/content - no search.list
    # -------------------------------------------------------------------------

    def iter_channel_video_ids(
        self,
        channel_id: str,
        *,
        page_token: str | None = None,
        max_results: int = 50,
    ) -> Iterator[str]:
        """Yield video IDs using the channel's uploads playlist.

        This is the quota-efficient channel discovery route. Each playlistItems.list
        request returns up to 50 items. No search.list calls are used.
        """
        playlist_id = self.get_uploads_playlist_id(channel_id)
        for item in self._iter_playlist_items(playlist_id, page_token=page_token, max_results=max_results):
            video_id = item.get("contentDetails", {}).get("videoId") or item.get("snippet", {}).get("resourceId", {}).get("videoId")
            if video_id:
                yield video_id

    def _iter_playlist_items(
        self,
        playlist_id: str,
        *,
        page_token: str | None = None,
        max_results: int = 50,
    ) -> Iterator[dict[str, Any]]:
        self._validate_id(playlist_id, "playlist_id")
        max_results = self._clamp(max_results, 1, 50)
        token = page_token
        while True:
            request = self._client().playlistItems().list(
                part="snippet,contentDetails",
                playlistId=playlist_id,
                maxResults=max_results,
                pageToken=token,
            )
            payload = self._execute(request)
            for item in payload.get("items", []):
                yield item
            token = payload.get("nextPageToken")
            if not token:
                break

    def list_channel_videos_page(
        self,
        channel_id: str | None = None,
        *,
        uploads_playlist_id: str | None = None,
        page_token: str | None = None,
        max_results: int = 50,
    ) -> dict[str, Any]:
        """Return one upload-playlist page, preserving nextPageToken for caller-controlled sync."""
        if uploads_playlist_id:
            playlist_id = uploads_playlist_id
        elif channel_id:
            playlist_id = self.get_uploads_playlist_id(channel_id)
        else:
            raise ValueError("Provide either channel_id or uploads_playlist_id")
        request = self._client().playlistItems().list(
            part="snippet,contentDetails",
            playlistId=playlist_id,
            maxResults=self._clamp(max_results, 1, 50),
            pageToken=page_token,
        )
        payload = self._execute(request)
        return {
            "items": payload.get("items", []),
            "next_page_token": payload.get("nextPageToken"),
            "prev_page_token": payload.get("prevPageToken"),
            "total_results": payload.get("pageInfo", {}).get("totalResults"),
            "results_per_page": payload.get("pageInfo", {}).get("resultsPerPage"),
            "playlist_id": playlist_id,
        }

    def get_video_details(self, video_ids: Sequence[str]) -> list[dict[str, Any]]:
        """Batch video metadata/statistics in requests of <=50 IDs.

        IMPORTANT: one videos.list call can retrieve up to 50 video IDs, so callers should
        always use this batching method instead of one request per video.
        """
        ids = self._dedupe_ids(video_ids, "video_id")
        if not ids:
            return []
        results: list[dict[str, Any]] = []
        for chunk in self._chunks(ids, 50):
            request = self._client().videos().list(
                part="snippet,contentDetails,statistics,status",
                id=",".join(chunk),
                maxResults=len(chunk),
            )
            payload = self._execute(request)
            results.extend(payload.get("items", []))
        return results

    def get_video_detail(self, video_id: str) -> dict[str, Any]:
        items = self.get_video_details([video_id])
        if not items:
            raise YouTubeAPIError(f"Video not found: {video_id}", status_code=404)
        return items[0]

    def get_videos_by_ids(self, video_ids: Sequence[str]) -> list[dict[str, Any]]:
        """Alias with a semantically clear name for batch reads."""
        return self.get_video_details(video_ids)

    def iter_channel_videos(
        self,
        channel_id: str,
        *,
        include_details: bool = True,
        stop_after_known_ids: set[str] | None = None,
        max_pages: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Iterate channel uploads, optionally stopping when known IDs are encountered.

        Best practice for incremental sync:
            known = latest_video_ids_from_db
            iterate with stop_after_known_ids=known

        The first upload page is newest-first. Stop at the first already-seen ID; this avoids
        walking the entire historical playlist on every poll.
        """
        playlist_id = self.get_uploads_playlist_id(channel_id)
        token: str | None = None
        pages = 0
        while True:
            request = self._client().playlistItems().list(
                part="snippet,contentDetails",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=token,
            )
            payload = self._execute(request)
            page_items = payload.get("items", [])
            new_items: list[dict[str, Any]] = []
            hit_known = False
            for item in page_items:
                video_id = item.get("contentDetails", {}).get("videoId") or item.get("snippet", {}).get("resourceId", {}).get("videoId")
                if not video_id:
                    continue
                if stop_after_known_ids and video_id in stop_after_known_ids:
                    hit_known = True
                    break
                new_items.append(item)
            if include_details and new_items:
                details = self.get_video_details([
                    item["contentDetails"]["videoId"] for item in new_items if item.get("contentDetails", {}).get("videoId")
                ])
                by_id = {item["id"]: item for item in details}
                for playlist_item in new_items:
                    video_id = playlist_item.get("contentDetails", {}).get("videoId")
                    yield by_id.get(video_id, playlist_item)
            else:
                yield from new_items

            pages += 1
            if hit_known or max_pages is not None and pages >= max_pages:
                return
            token = payload.get("nextPageToken")
            if not token:
                return

    def iter_all_channel_videos(
        self,
        channel_id: str,
        *,
        include_details: bool = True,
    ) -> Iterator[dict[str, Any]]:
        """Full historical scan; intended for initial indexing, not frequent polling."""
        yield from self.iter_channel_videos(channel_id, include_details=include_details)

    # -------------------------------------------------------------------------
    # Comments
    # -------------------------------------------------------------------------

    def list_video_comments_page(
        self,
        video_id: str,
        *,
        page_token: str | None = None,
        max_results: int = 100,
        order: str = "time",
        text_format: str = "plainText",
    ) -> dict[str, Any]:
        """Fetch one page of top-level comment threads for a video.

        maxResults=100 and order=time are used so the newest page contains the newest
        comments, which is important for incremental synchronization.
        """
        self._validate_id(video_id, "video_id")
        if order not in {"time", "relevance"}:
            raise ValueError("order must be 'time' or 'relevance'")
        if text_format not in {"plainText", "html"}:
            raise ValueError("text_format must be 'plainText' or 'html'")
        request = self._client().commentThreads().list(
            part="snippet,replies",
            videoId=video_id,
            order=order,
            maxResults=self._clamp(max_results, 1, 100),
            textFormat=text_format,
            pageToken=page_token,
        )
        payload = self._execute(request)
        return {
            "items": payload.get("items", []),
            "next_page_token": payload.get("nextPageToken"),
            "total_results": payload.get("pageInfo", {}).get("totalResults"),
            "results_per_page": payload.get("pageInfo", {}).get("resultsPerPage"),
        }

    def iter_video_comments(
        self,
        video_id: str,
        *,
        page_token: str | None = None,
        max_pages: int | None = None,
        stop_at_comment_ids: set[str] | None = None,
        include_replies: bool = True,
        order: str = "time",
        text_format: str = "plainText",
    ) -> Iterator[dict[str, Any]]:
        """Yield top-level comment threads, newest first.

        For polling, pass IDs already stored in DB in stop_at_comment_ids. The method stops
        as soon as it reaches one of them, which is far cheaper than paginating history.
        """
        token = page_token
        pages = 0
        while True:
            page = self.list_video_comments_page(
                video_id,
                page_token=token,
                max_results=100,
                order=order,
                text_format=text_format,
            )
            hit_known = False
            for thread in page["items"]:
                top_comment = thread.get("snippet", {}).get("topLevelComment", {})
                comment_id = top_comment.get("id")
                if stop_at_comment_ids and comment_id in stop_at_comment_ids:
                    hit_known = True
                    break
                if not include_replies:
                    thread = dict(thread)
                    snippet = dict(thread.get("snippet", {}))
                    snippet.pop("replies", None)
                    thread["snippet"] = snippet
                yield thread

            pages += 1
            if hit_known or max_pages is not None and pages >= max_pages:
                return
            token = page.get("next_page_token")
            if not token:
                return

    def list_comment_replies_page(
        self,
        comment_id: str,
        *,
        page_token: str | None = None,
        max_results: int = 100,
        text_format: str = "plainText",
    ) -> dict[str, Any]:
        """Fetch actual reply comments. Use only when full replies are needed.

        commentThreads.list may include a subset/summary of replies; comments.list is needed
        to retrieve all replies in a thread.
        """
        self._validate_id(comment_id, "comment_id")
        request = self._client().comments().list(
            part="snippet",
            parentId=comment_id,
            maxResults=self._clamp(max_results, 1, 100),
            textFormat=text_format,
            pageToken=page_token,
        )
        payload = self._execute(request)
        return {
            "items": payload.get("items", []),
            "next_page_token": payload.get("nextPageToken"),
            "total_results": payload.get("pageInfo", {}).get("totalResults"),
            "results_per_page": payload.get("pageInfo", {}).get("resultsPerPage"),
        }

    def iter_comment_replies(
        self,
        comment_id: str,
        *,
        max_pages: int | None = None,
        text_format: str = "plainText",
    ) -> Iterator[dict[str, Any]]:
        token: str | None = None
        pages = 0
        while True:
            page = self.list_comment_replies_page(
                comment_id,
                page_token=token,
                max_results=100,
                text_format=text_format,
            )
            yield from page["items"]
            pages += 1
            if max_pages is not None and pages >= max_pages:
                return
            token = page.get("next_page_token")
            if not token:
                return

    def get_comment(self, comment_id: str) -> dict[str, Any]:
        """Fetch a single comment by ID; useful to confirm a reply target before posting."""
        self._validate_id(comment_id, "comment_id")
        request = self._client().comments().list(part="snippet", id=comment_id, maxResults=1, textFormat="plainText")
        payload = self._execute(request)
        items = payload.get("items", [])
        if not items:
            raise YouTubeAPIError(f"Comment not found: {comment_id}", status_code=404)
        return items[0]

    def sync_new_video_comments(
        self,
        video_id: str,
        *,
        known_comment_ids: set[str] | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        """Convenience method for the common incremental polling operation."""
        return list(
            self.iter_video_comments(
                video_id,
                stop_at_comment_ids=known_comment_ids or set(),
                max_pages=max_pages,
                include_replies=True,
                order="time",
                text_format="plainText",
            )
        )

    # -------------------------------------------------------------------------
    # Replies / moderation
    # -------------------------------------------------------------------------

    def reply_to_comment(self, comment_id: str, text: str) -> dict[str, Any]:
        """Create a reply to an existing comment (comments.insert, 50 quota units)."""
        self._validate_id(comment_id, "comment_id")
        text = text.strip()
        if not text:
            raise ValueError("Reply text cannot be empty")
        if len(text) > 10000:
            raise ValueError("Reply text is too long for a safe API request")

        body = {
            "snippet": {
                "parentId": comment_id,
                "textOriginal": text,
            }
        }
        request = self._client().comments().insert(part="snippet", body=body)
        return self._execute(request)

    def delete_comment(self, comment_id: str) -> None:
        """Delete a comment/reply owned/managed by the authorized account."""
        self._validate_id(comment_id, "comment_id")
        request = self._client().comments().delete(id=comment_id)
        self._execute(request)

    def update_top_level_comment(self, comment_id: str, text: str) -> dict[str, Any]:
        """Update an existing top-level comment owned by the channel."""
        self._validate_id(comment_id, "comment_id")
        text = text.strip()
        if not text:
            raise ValueError("Comment text cannot be empty")
        request = self._client().comments().update(
            part="snippet",
            body={
                "id": comment_id,
                "snippet": {
                    "textOriginal": text,
                },
            },
        )
        return self._execute(request)

    def set_comment_moderation_status(
        self,
        comment_ids: Sequence[str],
        *,
        status: str,
        ban_author: bool = False,
    ) -> None:
        """Set moderation status for up to 50 comments in one request.

        WARNING: this operation costs substantially more quota than ordinary reads/replies;
        keep it out of the hot path unless moderation is actually needed.
        """
        valid_statuses = {"heldForReview", "published", "rejected"}
        if status not in valid_statuses:
            raise ValueError(f"status must be one of {sorted(valid_statuses)}")
        ids = self._dedupe_ids(comment_ids, "comment_id")
        if not ids:
            return
        if len(ids) > 50:
            raise ValueError("YouTube accepts at most 50 comment IDs per moderation request")
        request = self._client().comments().setModerationStatus(
            id=",".join(ids),
            moderationStatus=status,
            banAuthor=ban_author,
        )
        self._execute(request)

    # -------------------------------------------------------------------------
    # Quota-aware helpers / operational safety
    # -------------------------------------------------------------------------

    def get_quota_strategy(self) -> dict[str, Any]:
        """Return documented strategy metadata for the application's scheduling layer."""
        return {
            "avoid_search_list_for_channel_sync": True,
            "batch_video_ids_per_request": 50,
            "comment_page_size": 100,
            "playlist_page_size": 50,
            "incremental_comments": "poll newest-first and stop at first known comment ID",
            "incremental_videos": "poll uploads playlist newest-first and stop at first known video ID",
            "reply_method": "comments.insert (50 quota units per reply)",
            "default_daily_quota_units": DEFAULT_DAILY_QUOTA_UNITS,
            "do_not_fetch_full_reply_history": True,
            "do_not_poll_each_comment_individually": True,
        }

    @staticmethod
    def estimate_quota(
        *,
        reply_count: int = 0,
        comment_list_requests: int = 0,
        comment_reply_list_requests: int = 0,
        playlist_list_requests: int = 0,
        video_list_requests: int = 0,
        channel_list_requests: int = 0,
        daily_budget: int = DEFAULT_DAILY_QUOTA_UNITS,
    ) -> dict[str, int | float | bool]:
        """Estimate YouTube Data API quota for a workload before scheduling it.

        This is intentionally a local calculation; YouTube does not expose a simple
        per-request 'remaining quota' field through Data API responses. It is useful for
        keeping a scheduler under the project's known daily budget.
        """
        values = {
            "reply_count": reply_count,
            "comment_list_requests": comment_list_requests,
            "comment_reply_list_requests": comment_reply_list_requests,
            "playlist_list_requests": playlist_list_requests,
            "video_list_requests": video_list_requests,
            "channel_list_requests": channel_list_requests,
        }
        if any(not isinstance(v, int) or v < 0 for v in values.values()):
            raise ValueError("quota workload counts must be non-negative integers")
        if not isinstance(daily_budget, int) or daily_budget <= 0:
            raise ValueError("daily_budget must be a positive integer")
        total = (
            reply_count * QUOTA_COSTS["comments.insert"]
            + comment_list_requests * QUOTA_COSTS["commentThreads.list"]
            + comment_reply_list_requests * QUOTA_COSTS["comments.list"]
            + playlist_list_requests * QUOTA_COSTS["playlistItems.list"]
            + video_list_requests * QUOTA_COSTS["videos.list"]
            + channel_list_requests * QUOTA_COSTS["channels.list"]
        )
        return {
            "estimated_units": total,
            "daily_budget": daily_budget,
            "remaining_units": daily_budget - total,
            "within_budget": total <= daily_budget,
            "budget_utilization_pct": round((total / daily_budget) * 100, 2),
        }

    def health_check(self) -> dict[str, Any]:
        """Low-cost auth/API health check using channels.list(mine=true)."""
        channels = self.get_authenticated_channels()
        return {
            "ok": True,
            "channel_count": len(channels),
            "channels": [
                {"id": c.get("id"), "title": c.get("snippet", {}).get("title")}
                for c in channels
            ],
        }

    def export_access_token(self) -> str | None:
        """Expose current access token for rare integrations; never log/store this."""
        return getattr(self._credentials, "token", None)

    def export_refresh_token(self) -> str | None:
        """Expose stored refresh token for persistence if using a custom credentials wrapper."""
        return getattr(self._credentials, "refresh_token", None)

    # -------------------------------------------------------------------------
    # Internal utilities
    # -------------------------------------------------------------------------

    @staticmethod
    def _validate_id(value: str, name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")

    @staticmethod
    def _clamp(value: int, minimum: int, maximum: int) -> int:
        if not isinstance(value, int):
            raise TypeError("max_results must be an integer")
        return max(minimum, min(maximum, value))

    @classmethod
    def _dedupe_ids(cls, ids: Iterable[str], name: str) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in ids:
            cls._validate_id(value, name)
            value = value.strip()
            if value not in seen:
                seen.add(value)
                result.append(value)
        return result

    @staticmethod
    def _chunks(items: Sequence[str], size: int) -> Iterator[list[str]]:
        for start in range(0, len(items), size):
            yield list(items[start:start + size])


__all__ = [
    "GOOGLE_AUTH_ENDPOINT",
    "GOOGLE_TOKEN_ENDPOINT",
    "GOOGLE_REVOKE_ENDPOINT",
    "QUOTA_COSTS",
    "DEFAULT_DAILY_QUOTA_UNITS",
    "YOUTUBE_FORCE_SSL_SCOPE",
    "OAuthCallbackResult",
    "OAuthTokens",
    "YouTubeAPIError",
    "YouTubeAPISettings",
    "YouTubeOAuthConfig",
    "YouTubeOAuthError",
    "YouTubeRateLimitError",
    "YouTubeService",
    "YouTubeServiceError",
]

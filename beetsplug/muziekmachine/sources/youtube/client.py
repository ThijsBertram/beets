from __future__ import annotations
from typing import Any, Dict, Iterable, Mapping, Optional, List

import os
import json
from dataclasses import dataclass

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from beetsplug.muziekmachine.sources.base.client import SourceClient, RetryPolicy
from beetsplug.muziekmachine.sources.base.errors import (
    ClientAuthError, ClientConfigError, ClientConnectionError,
    ClientRequestError, ClientNotFoundError, ClientCapabilityError
)
from beetsplug.muziekmachine.domain.models import SourceRef, CollectionStub


@dataclass(frozen=True)
class _YTConfig:
    api_name: str = "youtube"
    api_version: str = "v3"
    scopes: str = "https://www.googleapis.com/auth/youtube"
    # Where OAuth client secrets live (downloaded from Google Cloud console)
    client_secrets_file: str = "auth/client_secret.json"
    # Where we cache the user token (refresh token etc.)
    token_path: str = "auth/yt_credentials.json"


class YouTubeClient(SourceClient):
    """
    Transport-only YouTube client (no mapping/adapter logic).
    Lists playlists, iterates playlist items, fetches single videos by id.
    """

    source = "youtube"

    def __init__(
        self,
        *,
        client_secrets_file: str,
        token_path: str = "auth/yt_credentials.json",
        scopes: List[str] = ['https://www.googleapis.com/auth/youtube'],
        retry_policy: Optional[RetryPolicy] = None,
        api_name: str = "youtube",
        api_version: str = "v3",
    ) -> None:
        super().__init__(retry_policy=retry_policy)
        self._cfg = _YTConfig(
            api_name=api_name,
            api_version=api_version,
            scopes=scopes or _YTConfig.scopes,
            client_secrets_file=client_secrets_file,
            token_path=token_path,
        )
        self.api = None
        self.creds: Optional[Credentials] = None

    # ── lifecycle ────────────────────────────────────────────────────────────
    def connect(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._cfg.token_path) or ".", exist_ok=True)
            creds: Optional[Credentials] = None

            if os.path.exists(self._cfg.token_path):
                try:
                    creds = Credentials.from_authorized_user_file(self._cfg.token_path, self._cfg.scopes)
                    if creds and creds.expired and creds.refresh_token:
                        creds.refresh(Request())
                except Exception:
                    creds = None

            if not creds:
                flow = InstalledAppFlow.from_client_secrets_file(self._cfg.client_secrets_file, self._cfg.scopes)
                creds = flow.run_local_server(port=0)
                with open(self._cfg.token_path, "w") as fh:
                    fh.write(creds.to_json())

            self.creds = creds
            self.api = build(self._cfg.api_name, self._cfg.api_version, credentials=self.creds)
        except FileNotFoundError as e:
            raise ClientConfigError(f"Missing OAuth client secrets: {e}") from e
        except HttpError as e:
            raise ClientAuthError(str(e)) from e
        except Exception as e:
            raise ClientConnectionError(str(e)) from e

    def close(self) -> None:
        self.api = None
        self.creds = None

    # ── capabilities (metadata writes optional; playlists are write-capable, track meta is not) ──
    def capabilities(self) -> set[str]:
        # For track metadata we’ll treat YouTube as read-only.
        return set()

    # ── collections (playlists) ──────────────────────────────────────────────
    def iter_collections(self, **kwargs) -> Iterable[CollectionStub]:
        """
        Yield the user's playlists as CollectionStub.
        """
        assert self.api is not None, "YouTubeClient not connected"
        request = self.api.playlists().list(
            part="id,snippet,contentDetails,status",
            mine=True,
            maxResults=50,
        )
        while request:
            try:
                resp = request.execute()
                for p in resp.get("items", []):
                    yield CollectionStub(
                        id=p["id"],
                        name=p["snippet"]["title"],
                        description=p["snippet"].get("description") or "",
                        raw=p,
                    )
                request = self.api.playlists().list_next(request, resp)
            except HttpError as e:
                raise ClientRequestError(str(e)) from e

    # ── items (videos within a playlist) ─────────────────────────────────────
    def iter_items(self, collection: CollectionStub | None = None, **kwargs) -> Iterable[Dict[str, Any]]:
        """
        Yield raw playlist-items for a given playlist.
        If no collection is provided, iterate all collections and aggregate items.
        """
        assert self.api is not None, "YouTubeClient not connected"

        if collection is None:
            for coll in self.iter_collections():
                yield from self.iter_items(coll, **kwargs)
            return

        request = self.api.playlistItems().list(
            part="contentDetails,snippet,status",
            playlistId=collection.id,
            maxResults=50,
        )
        while request:
            try:
                resp = request.execute()
                for it in resp.get("items", []):
                    yield it
                request = self.api.playlistItems().list_next(request, resp)
            except HttpError as e:
                raise ClientRequestError(str(e)) from e

    # ── fetch single video by id ─────────────────────────────────────────────
    def get_item(self, ref: SourceRef, **kwargs) -> Mapping[str, Any]:
        assert self.api is not None, "YouTubeClient not connected"
        if ref.source != "youtube" or not ref.external_id:
            raise ClientConfigError("YouTube get_item requires SourceRef(source='youtube', external_id=<video_id>)")
        try:
            resp = self.api.videos().list(part="snippet,contentDetails,status", id=ref.external_id, maxResults=1).execute()
            items = resp.get("items", [])
            if not items:
                raise ClientNotFoundError(f"YouTube video not found: {ref.external_id}")
            # Normalize shape to look like a playlist item enough for adapter/mapper to cope.
            video = items[0]
            return {
                "contentDetails": {"videoId": video["id"], "duration": video.get("contentDetails", {}).get("duration")},
                "snippet": {
                    "title": video["snippet"]["title"],
                    "channelTitle": video["snippet"].get("channelTitle"),
                    "description": video["snippet"].get("description"),
                },
                "status": video.get("status", {}),
            }
        except HttpError as e:
            if getattr(e, "resp", None) and getattr(e.resp, "status", None) == 404:
                raise ClientNotFoundError(f"YouTube video not found: {ref.external_id}") from e
            if getattr(e, "resp", None) and getattr(e.resp, "status", None) in (401, 403):
                raise ClientAuthError(str(e)) from e
            raise ClientRequestError(str(e)) from e

    # ── write (patch) — read-only for track metadata in this pipeline ───────
    def apply(self, ref: SourceRef, diff, **kwargs) -> None:
        raise ClientCapabilityError("YouTube is read-only for track metadata in this pipeline.")

    def iter_items_in_collection(self, coll):
        raise NotImplementedError
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from beetsplug.muziekmachine.domain.models import CollectionStub, SourceRef
from beetsplug.muziekmachine.sources.base.client import RetryPolicy, SourceClient
from beetsplug.muziekmachine.sources.base.errors import (
    ClientAuthError,
    ClientCapabilityError,
    ClientConfigError,
    ClientConnectionError,
    ClientNotFoundError,
    ClientRequestError,
)


@dataclass(frozen=True)
class _YTConfig:
    api_name: str = "youtube"
    api_version: str = "v3"
    scopes: str = "https://www.googleapis.com/auth/youtube"
    client_secrets_file: str = "auth/client_secret.json"
    token_path: str = "auth/yt_credentials.json"


class YouTubeClient(SourceClient):
    source = "youtube"

    def __init__(
        self,
        *,
        client_secrets_file: str,
        token_path: str = "auth/yt_credentials.json",
        scopes: List[str] = ["https://www.googleapis.com/auth/youtube"],
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

    def capabilities(self) -> set[str]:
        return set()

    def iter_collections(self, **kwargs) -> Iterable[CollectionStub]:
        assert self.api is not None, "YouTubeClient not connected"
        request = self.api.playlists().list(part="id,snippet,contentDetails,status", mine=True, maxResults=50)
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

    def find_collections(self, query: str) -> Iterable[CollectionStub]:
        q = (query or "").strip().lower()
        for coll in self.iter_collections():
            if q in (coll.name or "").lower() or q == (coll.id or ""):
                yield coll

    def iter_items(self, collection: CollectionStub | None = None, **kwargs) -> Iterable[Dict[str, Any]]:
        assert self.api is not None, "YouTubeClient not connected"
        if collection is None:
            for coll in self.iter_collections():
                yield from self.iter_items(coll, **kwargs)
            return

        request = self.api.playlistItems().list(
            part="id,contentDetails,snippet,status",
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

    def iter_items_in_collection(self, coll):
        return self.iter_items(coll)

    def get_item(self, ref: SourceRef, **kwargs) -> Mapping[str, Any]:
        assert self.api is not None, "YouTubeClient not connected"
        if ref.source != "youtube" or not ref.external_id:
            raise ClientConfigError("YouTube get_item requires SourceRef(source='youtube', external_id=<video_id>)")
        try:
            resp = self.api.videos().list(part="snippet,contentDetails,status", id=ref.external_id, maxResults=1).execute()
            items = resp.get("items", [])
            if not items:
                raise ClientNotFoundError(f"YouTube video not found: {ref.external_id}")
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

    def search_song_candidates(self, songdata: Any, limit: int = 10) -> Iterable[Dict[str, Any]]:
        assert self.api is not None, "YouTubeClient not connected"
        title = getattr(songdata, "title", "")
        artist = getattr(songdata, "main_artist", "") or ""
        query = f"{title} {artist}".strip()
        try:
            req = self.api.search().list(part="snippet", q=query, type="video", maxResults=limit)
            resp = req.execute()
            for item in resp.get("items", []):
                yield {
                    "contentDetails": {"videoId": item.get("id", {}).get("videoId")},
                    "snippet": item.get("snippet", {}),
                }
        except HttpError as e:
            raise ClientRequestError(str(e)) from e

    def create_collection(self, name: str, description: str = "", public: bool = False) -> CollectionStub:
        assert self.api is not None, "YouTubeClient not connected"
        body = {
            "snippet": {"title": name, "description": description or ""},
            "status": {"privacyStatus": "public" if public else "private"},
        }
        try:
            raw = self.api.playlists().insert(part="snippet,status", body=body).execute()
            return CollectionStub(
                id=raw["id"],
                name=raw.get("snippet", {}).get("title") or name,
                description=(raw.get("snippet", {}).get("description") or ""),
                raw=raw,
            )
        except HttpError as e:
            raise ClientRequestError(str(e)) from e

    def delete_collection(self, playlist_id: str) -> None:
        assert self.api is not None, "YouTubeClient not connected"
        try:
            self.api.playlists().delete(id=playlist_id).execute()
        except HttpError as e:
            raise ClientRequestError(str(e)) from e

    def sync_collection_members(self, playlist_id: str, desired_video_ids: list[str]) -> None:
        assert self.api is not None, "YouTubeClient not connected"
        stub = CollectionStub(id=playlist_id, name="", raw={}, description="")
        current_items = list(self.iter_items(stub))
        current_ids = [((item.get("contentDetails") or {}).get("videoId")) for item in current_items]

        for item in current_items:
            item_id = item.get("id")
            vid = (item.get("contentDetails") or {}).get("videoId")
            if item_id and vid and vid not in desired_video_ids:
                self.api.playlistItems().delete(id=item_id).execute()

        for vid in desired_video_ids:
            if vid not in current_ids:
                body = {
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": vid},
                    }
                }
                self.api.playlistItems().insert(part="snippet", body=body).execute()

    def apply(self, ref: SourceRef, diff, **kwargs) -> None:
        raise ClientCapabilityError("YouTube is read-only for track metadata in this pipeline.")

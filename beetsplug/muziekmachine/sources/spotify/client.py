from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth

from beetsplug.muziekmachine.sources.base.client import RetryPolicy, SourceClient
from beetsplug.muziekmachine.sources.base.errors import (
    ClientAuthError,
    ClientCapabilityError,
    ClientConfigError,
    ClientConnectionError,
    ClientNotFoundError,
    ClientRequestError,
)
from beetsplug.muziekmachine.domain.models import CollectionStub, SourceRef


class SpotifyClient(SourceClient):
    source = "spotify"

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scope: str = "playlist-read-private playlist-modify-private playlist-modify-public",
        retry_policy: Optional[RetryPolicy] = None,
    ) -> None:
        super().__init__(retry_policy=retry_policy)
        self._cfg = dict(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
        )
        self.api: Optional[spotipy.Spotify] = None
        self.session = None

    def connect(self) -> None:
        if not all(self._cfg.values()):
            raise ClientConfigError("Missing Spotify OAuth config.")

        self.session = requests.Session()
        try:
            self.api = spotipy.Spotify(
                auth_manager=SpotifyOAuth(
                    client_id=self._cfg["client_id"],
                    client_secret=self._cfg["client_secret"],
                    redirect_uri=self._cfg["redirect_uri"],
                    scope=self._cfg["scope"],
                    requests_session=self.session,
                )
            )
        except Exception as e:
            raise ClientConnectionError(str(e)) from e

    def close(self) -> None:
        if self.session:
            self.session.close()
        self.api = None

    def capabilities(self) -> set[str]:
        return set()

    def iter_collections(self, **kwargs) -> Iterable[CollectionStub]:
        assert self.api is not None, "SpotifyClient not connected"
        offset = kwargs.get("offset", 0)
        limit = kwargs.get("limit", 50)

        while True:
            try:
                page = self.api.current_user_playlists(limit=limit, offset=offset)
                for p in page["items"]:
                    yield CollectionStub(
                        id=p["id"],
                        name=p["name"],
                        raw=p,
                        description=p.get("description") or "",
                    )
                if not page.get("next"):
                    break
                offset += limit
            except Exception as e:
                raise ClientRequestError(str(e)) from e

    def find_collections(self, query: str) -> Iterable[CollectionStub]:
        q = (query or "").strip().lower()
        for coll in self.iter_collections():
            if q in (coll.name or "").lower() or q == (coll.id or ""):
                yield coll

    def iter_items(self, collection: CollectionStub | None = None, **kwargs):
        assert self.api is not None, "SpotifyClient not connected"

        if not collection:
            for coll in self.iter_collections():
                yield from self.iter_items(coll, **kwargs)
            return

        playlist_id = collection.id
        limit = kwargs.get("limit", 100)
        offset = kwargs.get("offset", 0)
        while True:
            try:
                page = self.api.playlist_tracks(playlist_id, limit=limit, offset=offset)
                for item in page["items"]:
                    yield item
                if not page.get("next"):
                    break
                offset += limit
            except Exception as e:
                raise ClientRequestError(str(e)) from e

    def iter_items_in_collection(self, collection: CollectionStub | None = None):
        return self.iter_items(collection)

    def get_item(self, ref: SourceRef, **kwargs) -> Mapping[str, Any]:
        assert self.api is not None, "SpotifyClient not connected"
        if ref.source != "spotify" or not ref.external_id:
            raise ClientConfigError(
                "Spotify get_item requires SourceRef(source='spotify', external_id=<track_id>)"
            )

        try:
            track = self.api.track(ref.external_id)
            return {"track": track}
        except spotipy.exceptions.SpotifyException as e:
            if e.http_status == 404:
                raise ClientNotFoundError(f"Spotify track not found: {ref.external_id}") from e
            if e.http_status in (401, 403):
                raise ClientAuthError(str(e)) from e
            raise ClientRequestError(str(e)) from e

    def search_song_candidates(self, songdata: Any, limit: int = 10) -> Iterable[Dict[str, Any]]:
        assert self.api is not None, "SpotifyClient not connected"
        title = getattr(songdata, "title", "")
        artist = getattr(songdata, "main_artist", "") or ""
        query = f"track:{title} artist:{artist}".strip()
        try:
            resp = self.api.search(q=query, type="track", limit=limit)
            for item in resp.get("tracks", {}).get("items", []):
                yield {"track": item}
        except Exception as e:
            raise ClientRequestError(str(e)) from e

    def create_collection(self, name: str, description: str = "", public: bool = False) -> CollectionStub:
        assert self.api is not None, "SpotifyClient not connected"
        try:
            user = self.api.current_user()
            raw = self.api.user_playlist_create(
                user=user["id"],
                name=name,
                public=public,
                description=description or "",
            )
            return CollectionStub(
                id=raw["id"],
                name=raw["name"],
                description=raw.get("description") or "",
                raw=raw,
            )
        except Exception as e:
            raise ClientRequestError(str(e)) from e

    def sync_collection_members(self, playlist_id: str, desired_track_ids: list[str]) -> None:
        assert self.api is not None, "SpotifyClient not connected"
        try:
            uris = [f"spotify:track:{track_id}" for track_id in desired_track_ids]
            self.api.playlist_replace_items(playlist_id, uris)
        except Exception as e:
            raise ClientRequestError(str(e)) from e

    def delete_collection(self, playlist_id: str) -> None:
        assert self.api is not None, "SpotifyClient not connected"
        try:
            self.api.current_user_unfollow_playlist(playlist_id)
        except Exception as e:
            raise ClientRequestError(str(e)) from e

    def apply(self, ref: SourceRef, diff, **kwargs) -> None:
        raise ClientCapabilityError("Spotify is read-only in this pipeline.")

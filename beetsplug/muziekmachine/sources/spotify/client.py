from __future__ import annotations
from typing import Any, Dict, Iterable, Mapping, Optional

import requests

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from beetsplug.muziekmachine.sources.base import SourceClient, RetryPolicy
from beetsplug.muziekmachine.sources.base.errors import *
from beetsplug.muziekmachine.domain.models import SourceRef




class SpotifyClient(SourceClient):
    """

    Args:
        SourceClient (_type_): _description_

    Raises:
        ClientConfigError: _description_
        ClientConnectionError: _description_
        e: _description_
        ClientRequestError: _description_
        ClientRequestError: _description_

    Yields:
        _type_: _description_
    """

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

        self.source = "spotify"
        self.api: Optional[spotipy.Spotify] = None
        self.session = None

    def connect(self) -> None:

        if not all(self._cfg.values()):
                raise ClientConfigError("Missing Spotify OAuth config.")        

        self.session = requests.Session()

        try:
            self.api = spotipy.Spotify(
                auth_manager=SpotifyOAuth(
                    client_id=self._cfg['client_id'],
                    client_secret=self._cfg['client_secret'],
                    redirect_uri=self._cfg['redirect_uri'],
                    scope="playlist-read-private playlist-modify-private playlist-modify-public",
                    requests_session = self.session
                )
            )
        except Exception as e:
            raise ClientConnectionError(str(e)) from e 
    
    def close(self) -> None:
        
        try:
            if self.session:
                self.session.close()
        except Exception as e:
            raise e

        self.api = None

        
        return
    
    def capabilities(self) -> None:
        return
    
    def iter_collections(self, **kwargs) -> Iterable[Dict[str, Any]]:
        """


        Returns:
            Iterable[Dict[str, Any]]: _description_
        """
        
        assert self.api is not None, "SpotifyClient not connected"

        offset = kwargs.get("offset", 0)
        limit = kwargs.get("limit", 50)

        while True:
            try:
                page = self.api.current_user_playlists(limit=limit, offset=offset)

                for p in page["items"]:
                    yield {
                        "playlist_id": p["id"],
                        "playlist_name": p["name"],
                        "playlist_description": p.get("description") or "",
                        "snapshot_id": p.get("snapshot_id")
                    }

                if not page.get("next"):
                    break
                    
                offset += limit
            except Exception as e:
                raise ClientRequestError(str(e)) from e 
    
    def iter_items(self, collection: Mapping[str, Any], **kwargs):
        """ Iterates over all spotify TRACKS within a spotify PLAYLIST

        Args:
            collection (Mapping[str, Any]): _description_
        """
        assert self.api is not None, "SpotifyClient not connected"

        playlist_id = collection["playlist_id"]
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
           
    def get_item(self, ref: SourceRef, **kwargs) -> None:

        assert self.api is not None, "SpotifyClient not connected"

        if ref.source != "spotify" or not ref.id:
            raise ClientConfigError("Spotify get_item requires SourceRef(source='spotify', id=<track_id>)")

        try:
            track = self.api.track(ref.id)
            return {"track": track}
        except spotipy.exceptions.SpotifyException as e:
            if e.http_status == 404:
                raise ClientNotFoundError(f"Spotify track not found: {ref.id}") from e
            if e.http_status in (401, 403):
                raise ClientAuthError(str(e)) from e
            raise

    # write (patch) — not supported now
    def apply(self, ref: SourceRef, diff, **kwargs) -> None:
        raise ClientCapabilityError("Spotify is read-only in this pipeline.")
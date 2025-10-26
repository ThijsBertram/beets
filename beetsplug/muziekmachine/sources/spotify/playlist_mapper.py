from typing import Any, Dict, List
from beetsplug.muziekmachine.domain.models import PlaylistData, SongPointer, CollectionStub

class SpotifyPlaylistMapper:
    def to_playlistdata(self, stub: CollectionStub) -> PlaylistData:

        raw = stub.raw

        pd = PlaylistData(
            name=stub.name,
            description=stub.description or None,
            owner=(raw.get("owner") or {}).get("display_name") or (raw.get("owner") or {}).get("id"),
            is_public=raw.get("public"),
            spotify_id=raw["id"],
            members=[],
        )
        return pd
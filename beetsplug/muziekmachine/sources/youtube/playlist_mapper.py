from __future__ import annotations
from typing import Any, Dict

from beetsplug.muziekmachine.domain.models import PlaylistData, CollectionStub


class YouTubePlaylistMapper:
    def to_playlistdata(self, stub: CollectionStub) -> PlaylistData:
        raw = stub.raw or {}
        snippet = raw.get("snippet", {})
        return PlaylistData(
            name=stub.name,
            description=stub.description or None,
            owner=None,                       # YouTube may expose channel on snippet; fill if you like
            is_public=(raw.get("status") or {}).get("privacyStatus") == "public",
            youtube_id=raw.get("id"),
            members=[],
        )

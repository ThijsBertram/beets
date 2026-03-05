from typing import Any, Dict, List
from beetsplug.muziekmachine.domain.models import PlaylistData, SongPointer, CollectionStub

class BeetsPlaylistMapper:
    def to_playlistdata(self, stub: CollectionStub, raw_items: List[Dict[str, Any]] | None = None) -> PlaylistData:
        
        raw = stub.raw

        pd = PlaylistData(
            name=stub.name,
            description=stub.description or None,
            is_public=raw.get('is_public'),
            last_edited_at=raw.get('last_edited_at') or None,
            playlist_type=raw.get('type') or None,
            filesystem_id=raw.get('path') or None,
            beets_id=stub.id,
            spotify_id=raw.get('spotify_id') or None,
            youtube_id=raw.get('youtube_id') or None,
            rekordbox_id=raw.get('rekordbox_id') or None,
            members=[],
        )
        return pd
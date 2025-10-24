from typing import Any, Dict, List
from beetsplug.muziekmachine.domain.models import PlaylistData, SongPointer

class SpotifyPlaylistMapper:
    def to_playlistdata(self, raw_pl: Dict[str, Any], raw_items: List[Dict[str, Any]] | None = None) -> PlaylistData:
        pd = PlaylistData(
            name=raw_pl["name"],
            description=raw_pl.get("description") or None,
            owner=(raw_pl.get("owner") or {}).get("display_name") or (raw_pl.get("owner") or {}).get("id"),
            is_public=raw_pl.get("public"),
            spotify_id=raw_pl["id"],
            members=[],
        )
        if raw_items:
            for item in raw_items:
                t = item["track"]
                # we don't have canonical song_id here yet; fill SourceRef-ish payload for later matching
                pd.members.append(
                    SongPointer(song_id=None, source_ref={"source":"spotify","id":t["id"]})
                )
        return pd
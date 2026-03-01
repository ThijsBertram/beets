from __future__ import annotations
from typing import Any, Dict, List
from beets.library import Item

from beetsplug.muziekmachine.domain.models import SongData     
from beetsplug.muziekmachine.domain.models import PlaylistData, SongPointer

class BeetsMapper:
    def to_songdata(self, item: Item) -> SongData:
        # Map only what matters; extend as needed
        return SongData(
            title=item.title,
            path=str(item.path) if getattr(item, "path", None) else None,
            main_artist=getattr(item, "main_artist", None) or getattr(item, "artist", None),
            artists=item.artists,
            genre=getattr(item, "genre", None),
            subgenre=getattr(item, "subgenre", None),
            remixer=getattr(item, "remixer", None),
            remix_type=getattr(item, "remix_type", None),
            last_edited_ISO=getattr(item, "last_edited_ISO", None),
            youtube_id=getattr(item, "youtube_id", None),
            spotify_id=getattr(item, "spotify_id", None),
            soundcloud_id=getattr(item, "soundcloud_id", None),
            rekordbox_id=getattr(item, "rekordbox_id", None),
            rekordbox_path=getattr(item, "rekordbox_path", None),
            rekordbox_bpm=getattr(item, "rekordbox_bpm", None),
            rekordbox_tonality=getattr(item, "rekordbox_tonality", None),
            rekordbox_comments=getattr(item, "rekordbox_comments", None),
            rekordbox_rating=getattr(item, "rekordbox_rating", None),            
            rekordbox_cateogry=getattr(item, "rekordbox_cateogry", None),                              
        )

    def to_playlist(self, row: Dict[str, Any], items: List[Item] | None = None) -> PlaylistData:
        pd = PlaylistData(
            name=row["name"],
            description=row.get("description") or None,
            beets_id=str(row["id"]),
            spotify_id=row.get("spotify_id"),
            youtube_id=row.get("youtube_id"),
            rekordbox_id=row.get("rekordbox_id"),
            filesystem_id=row.get("path"),
            members=[],
        )
        if items:
            for it in items:
                pd.members.append(SongPointer(song_id=None, source_ref={"source":"beets","id":str(it.id)}))
        return pd
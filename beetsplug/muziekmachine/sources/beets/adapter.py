from __future__ import annotations
from typing import Any, Mapping, Optional
from beets.library import Item

from beetsplug.muziekmachine.sources.base.adapter import SourceAdapter
from beetsplug.muziekmachine.sources.beets.mapper import BeetsMapper
from beetsplug.muziekmachine.domain.models import SourceRef

class BeetsAdapter(SourceAdapter):
    source = "beets"

    def __init__(self, client, mapper: BeetsMapper | None = None) -> None:
        super().__init__(client, mapper or BeetsMapper())

    def make_ref(self, raw: Item) -> SourceRef:
        return SourceRef(source="beets", external_id=str(raw.id), path=str(raw.path) if raw.path else None)

    def render_current(self, raw: Item) -> Mapping[str, Any]:
        # use same keys that 'render_desired' will produce
        return {
            "title": raw.title,
            "artist": raw.artist,
            "album": getattr(raw, "album", None),
            "bpm": getattr(raw, "bpm", None),
            "key": getattr(raw, "initial_key", None) or getattr(raw, "key", None),
            "genre": getattr(raw, "genre", None),
            "comments": getattr(raw, "comments", None) or getattr(raw, "comment", None),
            "path": str(raw.path) if raw.path else None,
        }

    def render_desired(self, songdata: Any, ref: Optional[SourceRef] = None) -> Mapping[str, Any]:
        return {
            "title": songdata.title,
            "artist": songdata.main_artist or (songdata.artists[0] if songdata.artists else None),
            "album": getattr(songdata, "album", None),
            "bpm": getattr(songdata, "bpm", None),
            "key": getattr(songdata, "key", None),
            "genre": getattr(songdata, "genre", None),
            "comments": getattr(songdata, "comment", None),
            "path": getattr(songdata, "audiofile_path", None),
        }

    def capabilities(self) -> set[str]:
        # Keep aligned with client.capabilities()
        return {"title","artist","album","bpm","key","genre","comments","path"}
    

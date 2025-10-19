# domain/models.py (snippet)
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any, Literal

SourceName = Literal["spotify", "youtube", "rekordbox", "beets", "filesystem", "soundcloud", "string"]

@dataclass(frozen=True)
class SourceRef:
    source: SourceName
    # One of these will be used depending on the source:
    external_id: Optional[str] = None      # e.g. spotify track id, youtube video id
    collection_id: Optional[str] = None    # e.g. playlist id (when items live under a collection)
    path: Optional[str] = None             # filesystem path or Rekordbox "Location"
    extra: Optional[Dict[str, Any]] = None # room for odd cases (TrackID, snapshot, etc.)

    # Helper constructors (ergonomic sugar):
    @staticmethod
    def spotify_track(track_id: str) -> "SourceRef":
        return SourceRef(source="spotify", external_id=track_id)

    @staticmethod
    def youtube_video(video_id: str) -> "SourceRef":
        return SourceRef(source="youtube", external_id=video_id)

    @staticmethod
    def rekordbox_track(track_id: Optional[str] = None, location: Optional[str] = None) -> "SourceRef":
        return SourceRef(
            source="rekordbox",
            external_id=track_id,   # TrackID in the XML
            path=location,          # file Location in the XML (URL-ish path)
        )

    @staticmethod
    def beets_item(item_id: str) -> "SourceRef":
        return SourceRef(source="beets", external_id=item_id)

    @staticmethod
    def fs_path(path: str) -> "SourceRef":
        return SourceRef(source="filesystem", path=path)

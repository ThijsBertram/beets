from __future__ import annotations
from typing import Any, Dict, Mapping, Optional

from beetsplug.muziekmachine.sources.base.adapter import SourceAdapter
from beetsplug.muziekmachine.domain.models import SourceRef
from beetsplug.muziekmachine.sources.youtube.mapper import YouTubeMapper


def _iso8601_duration_to_seconds(dur: Optional[str]) -> Optional[int]:
    # Minimal ISO 8601 duration parser for PT#M#S (YouTube-like).
    # Return None if unknown or unparsable.
    if not dur or not dur.startswith("PT"):
        return None
    # Extremely small parser: PT#H#M#S (all optional)
    import re
    h = m = s = 0
    m_obj = re.search(r"(\d+)M", dur)
    s_obj = re.search(r"(\d+)S", dur)
    h_obj = re.search(r"(\d+)H", dur)
    if h_obj: h = int(h_obj.group(1))
    if m_obj: m = int(m_obj.group(1))
    if s_obj: s = int(s_obj.group(1))
    return h * 3600 + m * 60 + s


class YouTubeAdapter(SourceAdapter):
    """Bridge YouTube raw <-> SongData projections + SourceRef."""
    source = "youtube"

    def __init__(self, client, mapper: YouTubeMapper | None = None) -> None:
        super().__init__(client, mapper or YouTubeMapper())

    def make_ref(self, raw: Dict[str, Any]) -> SourceRef:
        # playlistItems shape
        video_id = None
        if "contentDetails" in raw and raw["contentDetails"].get("videoId"):
            video_id = raw["contentDetails"]["videoId"]
        # videos() shape
        if not video_id:
            video_id = raw.get("id") or (raw.get("contentDetails", {}).get("videoId"))
        return SourceRef(source="youtube", external_id=video_id)

    def render_current(self, raw: Dict[str, Any]) -> Mapping[str, Any]:
        # Normalize for diffing (read-only for metadata, but good for reports)
        snippet = raw.get("snippet", {})
        content = raw.get("contentDetails", {})
        return {
            "title": snippet.get("title"),
            "channel": snippet.get("channelTitle"),
            "duration_sec": _iso8601_duration_to_seconds(content.get("duration")),
        }

    def render_desired(self, songdata: Any, ref: Optional[SourceRef] = None) -> Mapping[str, Any]:
        return {
            "title": songdata.title,
            "channel": getattr(songdata, "main_artist", None),  # not perfect, but useful for insight reports
            "duration_sec": getattr(songdata, "duration_sec", None),
        }

    def capabilities(self) -> set[str]:
        # Treat YouTube video metadata as read-only in this pipeline.
        return set()

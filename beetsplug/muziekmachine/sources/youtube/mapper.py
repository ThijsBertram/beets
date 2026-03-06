from __future__ import annotations

import re
from typing import Any, Dict, Optional

from beetsplug.muziekmachine.domain.models import PlaylistData, SongData

_TOPIC_SUFFIX_RE = re.compile(r"\s*-\s*Topic\s*$", flags=re.IGNORECASE)


class YouTubeMapper:
    """
    Pure raw->SongData (no I/O). Handles both playlistItem-shaped rows and video-shaped rows.
    """

    def _extract_video_fields(self, raw: Dict[str, Any]) -> Dict[str, Optional[str]]:
        # Accept both playlistItems().list and videos().list shapes
        snippet = raw.get("snippet", {})
        content = raw.get("contentDetails", {})

        title = snippet.get("title")
        channel = snippet.get("channelTitle")
        video_id = content.get("videoId") or raw.get("id")

        return {"title": title, "channel": channel, "youtube_id": video_id}

    def to_songdata(self, raw: Dict[str, Any]) -> SongData:
        fields = self._extract_video_fields(raw)
        title = fields["title"] or ""
        channel = fields["channel"] or ""
        youtube_id = fields["youtube_id"]

        # If the channel is "Artist - Topic", prepend artist into title as "Artist - Title"
        if channel and _TOPIC_SUFFIX_RE.search(channel):
            artist = _TOPIC_SUFFIX_RE.sub("", channel).strip()
            # If title does not already contain " - ", make it "Artist - Title"
            if " - " not in title:
                title = f"{artist} - {title}"

        # Simple heuristic parser:
        # Prefer "Artist - Title"; if not present, treat entire string as title with unknown artist
        main_artist = None
        artists = []
        title_norm = title
        if " - " in title:
            a, t = title.split(" - ", 1)
            main_artist = a.strip() or None
            artists = [a.strip()] if a.strip() else []
            title_norm = t.strip()
        else:
            title_norm = title.strip()

        # Dedup small substrings in artists list (defensive; often just one)
        substrings = {a for a in artists for other in artists if a != other and a in other}
        artists = sorted([a for a in artists if a not in substrings])

        return SongData(
            title=title_norm,
            artists=artists,
            main_artist=main_artist or (artists[0] if artists else None),
            youtube_id=youtube_id,
        )

    def to_playlistdata(self, raw_playlist: Dict[str, Any]) -> PlaylistData:
        snippet = raw_playlist.get("snippet", {})
        status = raw_playlist.get("status", {})
        return PlaylistData(
            name=snippet.get("title") or "",
            description=snippet.get("description") or None,
            owner=snippet.get("channelTitle") or None,
            is_public=status.get("privacyStatus") == "public",
            youtube_id=raw_playlist.get("id"),
            members=[],
        )

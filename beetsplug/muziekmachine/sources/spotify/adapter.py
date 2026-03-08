from __future__ import annotations
from typing import Any, Dict, Mapping, Optional

from beetsplug.muziekmachine.domain.models import SourceRef

from typing import Any, Dict, Mapping, Optional

from beetsplug.muziekmachine.sources.base.adapter import SourceAdapter
from beetsplug.muziekmachine.domain.models import SourceRef


class SpotifyAdapter(SourceAdapter):
    """Bridge Spotify raw <-> SongData projections + SourceRef."""
    source = "spotify"

    def make_ref(self, raw: Dict[str, Any], extra_keys: Optional[Dict[str, Any]] = None) -> SourceRef:
        track = raw if "track" not in raw else raw["track"]
        payload = {
            "source": "spotify",
            "external_id": track["id"],
        }

        if extra_keys:
            payload.update(extra_keys)

        return SourceRef(**payload)

    def render_current(self, raw: Dict[str, Any]) -> Mapping[str, Any]:
        track = raw if "track" not in raw else raw["track"]
        return {
            "title": track["name"],
            "artists": tuple(a["name"] for a in track["artists"]),
            "duration_sec": int(round((track.get("duration_ms") or 0) / 1000)),
        }

    def render_desired(self, songdata: Any, ref: Optional[SourceRef] = None) -> Mapping[str, Any]:
        # We can still "compare" against desired state even if we won't write back.
        return {
            "title": songdata.title,
            "artists": tuple(songdata.artists),
            "duration_sec": getattr(songdata, "duration_sec", None),
        }

    def capabilities(self) -> set[str]:
        # Spotify is read-only for metadata in this pipeline (we won't patch)
        return set()

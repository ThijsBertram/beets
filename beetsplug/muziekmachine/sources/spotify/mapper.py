from __future__ import annotations

import re
from typing import Any, Dict

from beetsplug.muziekmachine.domain.models import PlaylistData, SongData


# TO DO:
#   - logic for getting remix is off? (works only for 'Remix' not for 'Dub' etc?)


class SpotifyMapper:
    def to_playlistdata(self, raw: Dict[str, Any]) -> PlaylistData:
        owner = raw.get("owner") or {}
        return PlaylistData(
            name=raw.get("name") or "",
            description=raw.get("description") or None,
            owner=owner.get("display_name") or owner.get("id"),
            is_public=raw.get("public"),
            spotify_id=raw.get("id"),
            members=[],
        )

    def to_songdata(self, raw: Dict[str, Any]) -> SongData:
        track = raw["track"]

        # title
        title = track["name"].split(" - ")[0]

        # ARTISTS
        artists = [artist["name"] for artist in track["artists"]]

        # main
        main_artist = artists[0]
        # feat
        _ = re.search(r"\(feat\. (.*?)\)", title)
        feat_artist, title = (_.group(1).strip(), title[: _.start()] + title[_.end() :].strip()) if _ else ("", title)
        # remix
        remixer = track["name"].split(" - ")[1].replace(" Remix", "") if len(track["name"].split(" - ")) > 1 else ""

        # remove duplicates and substrings
        substrings = {a for a in artists for other in artists if a != other and a in other}
        artists = [a for a in artists if a not in substrings]
        artists = sorted(artists)

        spotify_id = track["id"]

        return SongData(
            title=title,
            artists=artists,
            main_artist=main_artist,
            remixer=remixer,
            remix_type="Remix" if remixer else "",
            feat_artist=feat_artist,
            spotify_id=spotify_id,
        )

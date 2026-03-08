from __future__ import annotations

from dataclasses import dataclass, field
import datetime
from typing import Any, Dict, Literal, Optional, Tuple

from beets.library import Item
from fuzzywuzzy import fuzz
from pydantic import BaseModel, Field, field_validator

SourceName = Literal[
    "spotify",
    "youtube",
    "rekordbox",
    "beets",
    "filesystem",
    "soundcloud",
    "string",
]


@dataclass(frozen=True)
class SourceRef:
    source: SourceName
    external_id: Optional[str] = None
    collection_id: Optional[str] = None
    collection_name: Optional[str] = None
    path: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> Optional[str]:
        """Backward-compatible alias; prefer external_id."""
        return self.external_id

    @staticmethod
    def spotify(track_id: str) -> "SourceRef":
        return SourceRef(source="spotify", external_id=track_id)

    @staticmethod
    def youtube(video_id: str) -> "SourceRef":
        return SourceRef(source="youtube", external_id=video_id)

    @staticmethod
    def rekordbox(track_id: Optional[str] = None, location: Optional[str] = None) -> "SourceRef":
        return SourceRef(source="rekordbox", external_id=track_id, path=location)

    @staticmethod
    def beets(item_id: str) -> "SourceRef":
        return SourceRef(source="beets", external_id=item_id)

    @staticmethod
    def filesystem(path: str) -> "SourceRef":
        return SourceRef(source="filesystem", path=path)

    @staticmethod
    def string(input_str: str) -> "SourceRef":
        return SourceRef(source="string", extra={"input": input_str})


@dataclass(frozen=True)
class CollectionStub:
    id: str
    name: str
    raw: Dict[str, Any]
    description: Optional[str] = ""


class SongData(BaseModel):
    """Canonical song representation used across all sources."""

    # core identity
    title: str
    main_artist: Optional[str] = None
    artists: Tuple[str, ...] = ()

    # textual/music metadata
    feat_artist: Optional[str] = None
    album: Optional[str] = None
    genre: Optional[str] = None
    subgenre: Optional[str] = None
    remixer: Optional[str] = None
    remix_type: Optional[str] = None
    bpm: Optional[float] = None
    key: Optional[str] = None
    comment: Optional[str] = None

    # location / timestamps
    path: Optional[str] = None
    last_edited_ISO: Optional[str] = Field(default_factory=lambda: datetime.datetime.now().isoformat())

    # source IDs
    youtube_id: Optional[str] = None
    spotify_id: Optional[str] = None
    soundcloud_id: Optional[str] = None
    rekordbox_id: Optional[str] = None
    rekordbox_path: Optional[str] = None

    # rekordbox-specific metadata
    rekordbox_bpm: Optional[float] = None
    rekordbox_tonality: Optional[str] = None
    rekordbox_comments: Optional[str] = None
    rekordbox_rating: Optional[str] = None
    rekordbox_cateogry: Optional[str] = None

    # contextual source metadata
    playlist: Dict[str, Any] = Field(default_factory=dict)

    @property
    def audiofile_path(self) -> Optional[str]:
        """Backward-compatible alias for older adapter code."""
        return self.path

    @field_validator("artists", mode="before")
    @classmethod
    def split_artists(cls, value):
        if value is None:
            return ()

        if isinstance(value, str):
            parsed = [artist.strip().lower() for artist in value.split(",") if artist.strip()]
            return tuple(sorted(parsed))

        if isinstance(value, list):
            parsed = [str(artist).strip().lower() for artist in value if str(artist).strip()]
            return tuple(sorted(parsed))

        if isinstance(value, tuple):
            parsed = [str(artist).strip().lower() for artist in value if str(artist).strip()]
            return tuple(sorted(parsed))

        return value

    @classmethod
    def from_string(cls, data: str) -> "SongData":
        return cls(title=data.strip(), main_artist=None, artists=())

    @classmethod
    def from_youtube(cls, data: dict) -> "SongData":
        return cls(
            title=(data.get("title") or "").strip(),
            main_artist=(data.get("main_artist") or None),
            artists=data.get("artists") or (),
            youtube_id=data.get("youtube_id"),
        )

    @classmethod
    def from_spotify(cls, data: dict) -> "SongData":
        return cls(
            title=(data.get("title") or "").strip(),
            main_artist=(data.get("main_artist") or None),
            artists=data.get("artists") or (),
            spotify_id=data.get("spotify_id"),
        )

    @classmethod
    def from_beets(cls, data: Item) -> "SongData":
        return cls(
            title=getattr(data, "title", "") or "",
            main_artist=getattr(data, "artist", None),
            artists=getattr(data, "artists", ()) or (),
            path=str(getattr(data, "path", "") or "") or None,
            genre=getattr(data, "genre", None),
            comment=getattr(data, "comments", None) or getattr(data, "comment", None),
            spotify_id=getattr(data, "spotify_id", None),
            youtube_id=getattr(data, "youtube_id", None),
        )

    def __eq__(self, other):
        if not isinstance(other, SongData):
            return NotImplemented

        title_alike = fuzz.ratio((self.title or "").lower(), (other.title or "").lower()) >= 97
        self_artists = " ".join(self.artists or ()).lower()
        other_artists = " ".join(other.artists or ()).lower()
        artists_alike = fuzz.ratio(self_artists, other_artists) >= 97
        return title_alike and artists_alike

    def __hash__(self):
        return hash((self.artists, self.title))


@dataclass(frozen=True)
class PlaylistRef:
    source: SourceName
    playlist_id: Optional[str] = None
    path: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> Optional[str]:
        """Backward-compatible alias; prefer playlist_id."""
        return self.playlist_id


@dataclass(frozen=True)
class SongPointer:
    """Reference to playlist members.

    Prefer canonical `song_id`; otherwise store an unresolved source reference.
    """

    song_id: Optional[str] = None
    source_ref: Optional[Dict[str, Any]] = None


@dataclass
class PlaylistData:
    """Canonical playlist representation used across all sources."""

    # core metadata
    name: str
    description: Optional[str] = None
    owner: Optional[str] = None
    is_public: Optional[bool] = None

    # ordered membership
    members: list[SongPointer] = field(default_factory=list)

    # source identifiers
    spotify_id: Optional[str] = None
    youtube_id: Optional[str] = None
    rekordbox_id: Optional[str] = None
    beets_id: Optional[str] = None
    filesystem_id: Optional[str] = None

    # extra metadata
    last_edited_at: Optional[str] = None
    playlist_type: Optional[str] = None


@dataclass
class PullSourceResult:
    source: SourceName
    playlists_scanned: int = 0
    songs_seen: int = 0
    songs_mapped: int = 0
    duplicates_observed: int = 0
    mapping_failures: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class PullSongsBatch:
    result: PullSourceResult
    entries: list[tuple[SongData, SourceRef]] = field(default_factory=list)


@dataclass
class PullPlaylistsBatch:
    result: PullSourceResult
    playlists: list[PlaylistData] = field(default_factory=list)

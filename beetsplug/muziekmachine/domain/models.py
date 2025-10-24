# domain/models.py (snippet)
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any, Literal

from pydantic import BaseModel, field_validator
from typing import List, Optional, Tuple, Dict
from beets.library import DateType
import datetime
from fuzzywuzzy import fuzz
from typing import Dict, List

from beets.library import Item

from beetsplug.ssp import SongStringParser

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
    def spotify(track_id: str) -> "SourceRef":
        return SourceRef(source="spotify", external_id=track_id)

    @staticmethod
    def youtube(video_id: str) -> "SourceRef":
        return SourceRef(source="youtube", external_id=video_id)

    @staticmethod
    def rekordbox(track_id: Optional[str] = None, location: Optional[str] = None) -> "SourceRef":
        return SourceRef(
            source="rekordbox",
            external_id=track_id,   # TrackID in the XML
            path=location,          # file Location in the XML (URL-ish path)
        )

    @staticmethod
    def beets(item_id: str) -> "SourceRef":
        return SourceRef(source="beets", external_id=item_id)

    @staticmethod
    def filesystem(path: str) -> "SourceRef":
        return SourceRef(source="filesystem", path=path)

    @staticmethod
    def string(input_str: str) -> "SourceRef":
        return SourceRef(source="string")
    




class SongData(BaseModel):
    title: str
    path: Optional[str] = ''
    main_artist: str
    artists: Tuple = ()
    genre: str = ''
    subgenre: str = ''
    remixer: str = ''
    remix_type: str = ''
    last_edited_ISO: str = datetime.datetime.now().isoformat()
    # PLATFORMS
    youtube_id: str = ''
    spotify_id: str = ''
    soundcloud_id: str = ''
    #PLAYLIST
    playlist: dict = {}
    # REKORDBOX
    rekordbox_id: str = ''
    rekordbox_path: str = ''
    rekordbox_bpm: float = None
    rekordbox_tonality: str = ''
    rekordbox_comments: str = ''
    rekordbox_rating: str = ''
    rekordbox_cateogry: str = ''


    @classmethod
    def from_string(cls, data: str) -> "SongData":
        # LOGIC FOR CREATING SONGDATA FROM STRING
        return
    
    @classmethod
    def from_youtube(cls, data: dict) -> "SongData":
        return
    
    @classmethod
    def from_spotify(cls, data: dict) -> "SongData":
        return

    @classmethod
    def from_beets(cls, data: Item) -> "SongData":
        return

    def __eq__(self, other):
        if isinstance(other, SongData):
            # Match based on TITLE and ARTIST
            title_alike = 1 if fuzz.ratio(self.title.lower(), other.title.lower()) >= 97 else 0 
            artists_alike = 1 if fuzz.ratio(' '.join(self.artists).lower(), ' '.join(other.artists).lower()) >= 97 else 0
            alike = 1 if artists_alike and title_alike else 0

            # 
            return alike
        
    def __hash__(self):
        return hash((self.artists, self.title))
    

    @field_validator('artists', mode='before')
    def split_artists(cls, value):
        if isinstance(value, str):
            return tuple([artist.strip().lower() for artist in value.split(',')])
        elif isinstance(value, list):
            value = ','.join(value)
            value = value.split(',')

            return tuple(sorted([artist.strip().lower() for artist in value]))

        return value

    
    # @field_validator('added', mode='before')
    # def datetime_to_iso(cls, value):
    #     if isinstance(value, datetime.datetime):
    #         return value.isoformat()
    #     if isinstance(value, type(None)):
    #         return ''
    

class PlaylistData(BaseModel):
    name: str
    description: Optional[str] = ''
    path: Optional[str] = ''    
    rkbx_id: str = ''
    spotify_id: str = ''
    youtube_id: str = ''
    soundcloud_id: Optional[str] = ''
    last_edited_at: str = ''
    playlist_type: Optional[str] = ''
    songs: dict = {
        'youtube':  List[SongData],
        'spotify': List[SongData],
        'total': List[SongData],
        'rkbx': List[SongData],
        'usb': List[SongData]
    }
from pydantic import BaseModel, field_validator
from typing import List, Optional, Tuple
from beets.library import DateType
import datetime
from fuzzywuzzy import fuzz

class PlaylistData(BaseModel):
    name: str
    description: Optional[str] = ''
    spotify_id: str = ''
    youtube_id: str = ''
    soundcloud_id: Optional[str] = ''
    path: Optional[str] = ''
    last_edited_at: str = ''
    type: Optional[str] = ''
    

class SongData(BaseModel):
    title: str
    main_artist: str
    artists: Tuple = ()
    genre: str = ''
    subgenre: str = ''
    youtube_id: str = ''
    spotify_id: str = ''
    playlist_name: str = ''
    playlist_id: str = ''
    playlist_description: str = ''
    remixer: str = ''
    remix_type: str = ''
    last_edited_ISO: str = datetime.datetime.now().isoformat()

    def __eq__(self, other):
        if isinstance(other, SongData):

            # print(self.title.lower())
            # print(other.title.lower())
            # print()
            # print(' '.join(self.artists).lower())
            # print(' '.join(other.artists).lower())

            # print()
            # print()
            title_alike = 1 if fuzz.ratio(self.title.lower(), other.title.lower()) >= 97 else 0 
            artists_alike = 1 if fuzz.ratio(' '.join(self.artists).lower(), ' '.join(other.artists).lower()) >= 97 else 0
            alike = 1 if artists_alike and title_alike else 0
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
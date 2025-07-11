from pydantic import BaseModel, field_validator
from typing import List, Optional, Tuple
from beets.library import DateType
import datetime

class SongData(BaseModel):
    title: str
    main_artist: str
    artists: Tuple[str]
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
            return (self.artists, self.title) == (other.artists, other.title)
        
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
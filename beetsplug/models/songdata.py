from pydantic import BaseModel
from typing import List
from beets.library import DateType
import datetime

class SongData(BaseModel):
    title: str
    main_artist: str
    artists: List[str]
    genre: str 
    subgenre: str = ''
    youtube_id: str = ''
    spotify_id: str = ''
    playlist_name: str = ''
    playlist_id: str = ''
    playlist_description: str = ''
    remixer: str = ''
    remix_type: str = ''
    last_edited_ISO: str = datetime.datetime.now().isoformat()
import re 
from datetime import datetime, timedelta, timezone
from dateutil import parser
from typing import List
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand

from beetsplug.platforms_test.youtube import youtube_plugin
from beetsplug.platforms_test.spotify import spotify_plugin
from beetsplug.platforms_test.platform import VALID_PLATFORMS, VALID_PLAYLIST_TYPES
from beetsplug.custom_logger import CustomLogger
from beetsplug.models.songdata import SongData, PlaylistData
from beets.library import Item, DateType
from beets.dbcore.query import AndQuery, RegexpQuery, OrQuery


# TO DO

# - Parse all Audiofiles and check if an item has that PATH associated with it. Otherwise add the path to the item if it matches any item

class DataBaseUtils(BeetsPlugin):
    def __init__(self):
        super().__init__()

        self._log = CustomLogger("DataBaseUtils", default_color='blue')

    def _get_item_if_exists(self, lib, song):
        """
        Checks if song_data already exists in the DB by:
         1) platform_id queries,
         2) title/artist fallback.
        """
        item = None

        for platform in VALID_PLATFORMS:
            if getattr(song, f'{platform}_id'):   
                platform_id = getattr(song, f'{platform}_id')         
                q = f'{platform}_id:"{platform_id}"'
                item = lib.items(q).get()
                if item:
                    self._log.log("debug",f"Found item {item} using {platform} id")
                    return item
        
        # 2) Fallback: title & artist matching
        if not item:
            try:
                title = song['title']
                remixer = getattr(song, 'remixer')
                artist = getattr(song, 'main_artist')
                feat_artist = getattr(song, 'feat_artist')

                t = RegexpQuery('title', f'(?i){re.escape(title)}')
                a = RegexpQuery('artist', f'(?i){re.escape(artist)}')
                main_a = RegexpQuery('main_artist', f'(?i){re.escape(artist)}')
                r = RegexpQuery('remixer', f'(?i){re.escape(remixer)}') if remixer else None
                f = RegexpQuery('feat_artist', f'(?i){re.escape(feat_artist)}') if feat_artist else None

                artist_q = OrQuery([a, main_a])
                queries = [t, artist_q]
                if r: queries.append(r)
                if f: queries.append(f)

                c = AndQuery(queries)
                items = lib.items(c)
                item = items[0]  # If it exists
            except (IndexError, TypeError) as e:
                item = None
                self._log.log("debug",f"Item not found in db: {e}")

            return
        
    def songdata_to_item(self, lib, songdata: SongData) -> Item:
        item = self._get_item_if_exists(lib, song=songdata)
        if not item:
            print("NEEEE NIET GEVONDEN")

        return item 
    
    def item_to_songdata(self, item: Item) -> SongData:
        song = SongData(**dict(item))
        return song
    
    def add_or_update(self, lib, song: SongData):

        item = self._get_item_if_exists(lib, song)
        is_new = (item is None)
        row_id = None if is_new else item.id

        if is_new:
            songdata_dict = song.model_dump()

            # UGLY FIX THIS IN MODEL
            if isinstance(songdata_dict['artists'], tuple):
                a = songdata_dict.pop('artists')
                a = ', '.join(a)
                songdata_dict['artists'] = a

            songdata_dict['added'] = datetime.now().isoformat()

            # INSERT
            item_columns = Item().keys()
            columns_to_add = [key for key in songdata_dict.keys() if key in item_columns]
            columns = ", ".join(columns_to_add)
            placeholders = ", ".join(["?" for _ in columns_to_add])

            query = f"INSERT INTO items ({columns}) VALUES ({placeholders})"
            values = list([v for k, v in songdata_dict.items() if k in columns_to_add])

            with lib.transaction() as tx:
                tx.mutate(query, values)

        # Re-fetch to get an updated item (if new, it now exists)
        item = self._get_item_if_exists(lib, song)
        if is_new and item:
            return True
        elif not is_new and item:
            return False

        return is_new
    
    def items_to_download(self, lib, songs=None, dl_cooldown: int = 7, output='Item') -> List[SongData] | List[Item]:
        to_download = list()
        
        # get beets items
        if songs:
            all_items = [self.songdata_to_item(lib, song) for song in songs]
        else:
            all_items = lib.items()
        
        # check if file already exists
        no_path = [item for item in all_items if not item.path]

        # loop over items with no path
        for item in no_path:
            last_dl = parser.parse(item.last_download_attempt) if item.last_download_attempt else None

            # download if no attempt has been made
            if not last_dl:
                to_download.append(item)
                continue
            # download if cooldown is exceeded
            if dl_cooldown:
                if datetime.now() - last_dl > timedelta(days=dl_cooldown):
                    to_download.append(item)
            # download anyways if no cooldown period is provided
            else:
                to_download.append(item)

        if output == 'Item':
            return to_download
        elif output == 'SongData':
            to_download = [self.item_to_songdata(item) for item in to_download]
            return to_download
        else:
            raise ValueError("Not a valid value for the argument 'output'")
    
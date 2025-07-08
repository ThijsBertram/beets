from beets.plugins import BeetsPlugin
from beets.ui import Subcommand

from beetsplug.platforms_test.youtube import youtube_plugin
from beetsplug.platforms_test.spotify import spotify_plugin
from beetsplug.platforms_test.platform import VALID_PLATFORMS, VALID_PLAYLIST_TYPES
from beetsplug.custom_logger import CustomLogger
from beetsplug.models.songdata import SongData
from beets.library import Item, DateType
from beets.dbcore.query import AndQuery, RegexpQuery, OrQuery

# Varia
import re
import sqlite3
import logging
import colorlog
import datetime
from functools import wraps
from typing import List, Dict

# ANSI Escape Codes for Green Shades
GREEN_BRIGHT = '\033[92m'   # Bright Green
GREEN = '\033[38;5;154m'  # Lime Green
GREEN_DARK = '\033[32m'     # Dark Green

RED_BRIGHT = '\033[91m'     # Bright Red
RED = '\033[31m'       # Dark Red
RED_DARK = '\033[38;5;203m'  # Light Red

# ANSI Escape Codes for Blue Shades
BLUE_BRIGHT = '\033[94m'    # Bright Blue
BLUE = '\033[38;5;111m' # Sky Blue
BLUE_DARK = '\033[34m'      # Dark Blue

# ANSI Escape Codes for Cyan Shades
CYAN_BRIGHT = '\033[96m'    # Bright Cyan
CYAN = '\033[38;5;51m' # Aqua
CYAN_DARK = '\033[38;5;44m' # Teal

# ANSI Escape Codes for Yellow Shades
YELLOW_BRIGHT = '\033[93m'  # Bright Yellow
YELLOW = '\033[38;5;220m' # Golden Yellow
YELLOW_DARK = '\033[33m'    # Dark Yellow

# Reset ANSI Formatting
RESET = '\033[0m'

PLATFORM_LOG_COLOR = {
    'spotify': GREEN,
    'youtube': RED
}

class PlatformManager(BeetsPlugin):
    def __init__(self):
        super().__init__()
        # self._log = logging.getLogger('beets.platform_manager')
        self._log = CustomLogger("PlatformManager", default_color='yellow')

        # Add a simple console handler
        console_handler = logging.StreamHandler()

        # Define the CLI subcommand
        self.pull_command = Subcommand('pull')
        self.pull_command.parser.add_option(
            '--platform',
            default='all',
            dest='platform',
            choices=['all', 'spotify', 'youtube', 'a'],
            help='Specify the music platform (spotify, youtube, etc.)'
        )
        self.pull_command.parser.add_option(
            '--type',
            dest='playlist_type',
            choices=VALID_PLAYLIST_TYPES,
            default='mm',
            help="Process 'pl' playlists or 'mm' regular genre/subgenre playlists"
        )
        self.pull_command.parser.add_option(
            '--no_db',
            action='store_true',
            help='If set, do NOT add retrieved info to the database'
        )
        self.pull_command.parser.add_option(
            '--name',
            default='all',
            dest='playlist_name',
            help='Name of the playlist to retrieve'
        )

        # The CLI entrypoint is a thin wrapper around our core method
        self.pull_command.func = self.cli_pull_platform

    def commands(self):
        return [self.pull_command]

    # ──────────────────────────────────────────────────────────────────────────
    # CLI ENTRYPOINT (Thin Wrapper)
    # ──────────────────────────────────────────────────────────────────────────
    def cli_pull_platform(self, lib, opts, args):
        """
        CLI entrypoint for `beet pull` command.

        - Extracts the CLI options from `opts`
        - Calls the main `pull_platform_songs` method
        """
        platform_str = opts.platform
        playlist_name = opts.playlist_name
        playlist_type = opts.playlist_type
        no_db = opts.no_db

        self.pull_platform_songs(lib, platform_str, playlist_name, playlist_type, no_db)

    # ──────────────────────────────────────────────────────────────────────────
    # CALLABLE FROM OTHER CODE (e.g. your pipeline)
    # ──────────────────────────────────────────────────────────────────────────
    def pull_platform_songs(
        self,
        lib,
        platform_str='all',
        playlist_name='all',
        playlist_type='mm',
        no_db=False
    ):
        """
        Core logic to pull song data from the specified platform(s) and add/update
        the Beets library.

        It can be called from:
          1) The CLI subcommand (via `cli_pull_platform`).
          2) Another Python script, e.g.:
             `PlatformManager().pull_platform_songs(lib, 'spotify', 'all', 'mm', no_db=False)`
        """
        new = []
        existing = []
        # 1. Determine which PLATFORM(s) we'll process
        if platform_str == 'all':
            platforms_to_fetch = VALID_PLATFORMS
        else:
            # If user gave a single platform string, wrap it in a list
            if isinstance(platform_str, str):
                platforms_to_fetch = [platform_str]
            else:
                platforms_to_fetch = platform_str.split(',')


        # 1.1 Map each platform string to a plugin class
        platform_dict = {
            pf: self._get_plugin(pf)
            for pf in platforms_to_fetch
        }

        # 1.2 Get all playlists from each platform
        all_playlists = {pf: [] for pf in VALID_PLATFORMS}
        for name, pf_plugin_cls in platform_dict.items():
            with pf_plugin_cls() as plugin:
                all_playlists[name].extend(plugin._get_all_playlists())


        # 1.3 Filter playlists based on the playlist name, type, etc.
        #     We'll store them in a dict: {platform_name: [playlists_to_process]}
        playlists_to_process = {pf: [] for pf in VALID_PLATFORMS}
        for pf_name, pl_list in all_playlists.items():
            if not pl_list:
                continue

            # We'll need to open the plugin instance again to check `plugin.pl_to_skip`, etc.
            pf_plugin_cls = platform_dict.get(pf_name)
            if not pf_plugin_cls:
                continue

            with pf_plugin_cls() as plugin:

                # PLAYLIST INCLUSION LOGIC
                def should_include(playlist, to_exclude, playlist_name, playlist_type):
                    """Return True if a given playlist should be included."""

                    pl_to_select = [pl.lower() for pl in playlist_name.split(',')]

                    if playlist_type.lower() not in playlist['playlist_name'].lower():
                        return False

                    # 1. PL TO SKIP CONFIG
                    if playlist_name.lower() in to_exclude.lower():
                        return False

                    # 2) Special case: if ' pl ' in p['playlist_name'] AND playlist_type == 'mm', skip
                    if ' pl ' in playlist['playlist_name'] and playlist_type == 'mm':
                        return False

                    if playlist_name == 'all':
                        return True
                    else:
                        if any(pl in playlist['playlist_name'].lower() for pl in pl_to_select):
                            return True
                        else:
                            return False

                selected = [p for p in pl_list if should_include(p, 
                                                                 to_exclude=plugin.pl_to_skip, 
                                                                 playlist_name=playlist_name, 
                                                                 playlist_type=playlist_type)]   

                playlists_to_process[pf_name].extend(selected)    

        # Logging how many playlists per platform
        for pf in VALID_PLATFORMS:
            num_pl = len(playlists_to_process[pf])
            color = PLATFORM_LOG_COLOR.get(pf, '')
            self._log.log("info",f"{num_pl} playlists to process for {pf}")

        # 2. Retrieve songs for each platform and optionally add to DB
        for pf_name, playlists in playlists_to_process.items():
            if not playlists:
                continue

            pf_plugin_cls = platform_dict.get(pf_name)
            if not pf_plugin_cls:
                continue

            with pf_plugin_cls() as plugin:
                for pl in playlists:
                    # 2.1 get raw tracks
                    tracks = plugin._get_playlist_tracks(pl['playlist_id'])

                    # 2.2 parse raw tracks
                    parsed_tracks = [
                        plugin._parse_track_item(lib, item)
                        for item in tracks['items']
                    ]

                    # 2.3 add playlist & genre info
                    song_data = []
                    for track in parsed_tracks:
                        if not track:
                            continue
                        try:
                            track['platform'] = pf_name
                            track['playlist_name'] = pl['playlist_name']
                            track['playlist_id'] = pl['playlist_id']
                            track['playlist_description'] = pl['playlist_description']
                            if playlist_type == 'mm':
                                split_name = pl['playlist_name'].split(' - ')
                                track['genre'] = split_name[1] if len(split_name) > 1 else ''
                                track['subgenre'] = split_name[2] if len(split_name) > 2 else ''
                            song_data.append(SongData(**track).model_dump())
                        except Exception as e:
                            self._log.error(f"Error adding playlist info to track: {e}")

                    # Logging
                    self._log.log("info",
                        f"{len(parsed_tracks)} songs found in "
                        f"{pl['playlist_name']} on {pf_name}"
                    )

                    # 2.4 If `no_db` is False, add/update songs in DB
                    if not no_db:
                        n, e = self.add_to_db(lib, song_data)
                        new.extend(n)
                        existing.extend(e)
                        self._log.log("info",f"{len(new)}/{len(new) + len(existing)} new songs added")
        
        return new, existing

    # ──────────────────────────────────────────────────────────────────────────
    # SUPPORTING METHODS
    # ──────────────────────────────────────────────────────────────────────────
    def _get_plugin(self, platform):
        """Return the appropriate plugin class based on the platform."""
        if platform == 'spotify':
            return spotify_plugin
        elif platform == 'youtube':
            return youtube_plugin
        else:
            raise ValueError(f"Unsupported platform: {platform}")

    def add_to_db(self, lib, song_data):
        """
        Add or update the song_data in the beets library DB.
        
        Returns:
            (list_of_new_items, list_of_existing_items)
        """
        exists = []
        new = []

        for song in song_data:
            # Reformat artists
            artists = ','.join(sorted(set(song.pop('artists'))))
            song['artists'] = artists

            item = self._get_item_if_exists(lib, song)
            is_new = (item is None)
            row_id = None if is_new else item.id

            if is_new:
                song['added'] = datetime.datetime.now().timestamp()

            query, subvals = self._gen_store_item_q(song, row_id=row_id, is_new_row=is_new)
            if query:
                with lib.transaction() as tx:
                    tx.mutate(query, subvals)

            # Re-fetch to get an updated item (if new, it now exists)
            item = self._get_item_if_exists(lib, song)
            if is_new and item:
                new.append(item)
            elif not is_new and item:
                exists.append(item)

        return new, exists

    def _gen_store_item_q(self, update_data, table_name='items', row_id=None, is_new_row=False):
        """
        Builds the SQL query for inserting or updating an item in the DB.
        """
        filtered_data = {
            k: v for k, v in update_data.items()
            if v not in [None, ""] and k in Item._fields
        }

        if not filtered_data:
            return None, []

        if is_new_row:
            # INSERT
            columns = ", ".join(filtered_data.keys())
            placeholders = ", ".join(["?" for _ in filtered_data.keys()])
            query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
            values = list(filtered_data.values())
        else:
            # UPDATE
            if row_id is None:
                raise ValueError("row_id is required for updating an existing row.")
            set_clause = ", ".join([f"{k} = ?" for k in filtered_data.keys()])
            query = f"UPDATE {table_name} SET {set_clause} WHERE id = ?"
            values = list(filtered_data.values()) + [row_id]

        return query, values

    def _get_item_if_exists(self, lib, song):
        """
        Checks if song_data already exists in the DB by:
         1) platform_id queries,
         2) title/artist fallback.
        """
        item = None

        # 1) Check by platform ID
        platform_ids = {
            platform: song[f'{platform}_id']
            for platform in VALID_PLATFORMS
            if song.get(f'{platform}_id')
        }
        for platform, platform_id in platform_ids.items():
            q = f'{platform}_id:"{platform_id}"'
            item = lib.items(q).get()
            if item:
                self._log.log("debug",f"Found item {item} using {platform} id")
                return item

        # 2) Fallback: title & artist matching
        if not item:
            try:
                title = song['title']
                remixer = song.get('remixer', '')
                artist = song.get('main_artist', '')
                feat_artist = song.get('feat_artist', '')

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

            return item



# class PlatformManager(BeetsPlugin):
#     def __init__(self):
#         super().__init__()
#         self._log = logging.getLogger('beets.platform_manager')

#         # Add a simple console handler
#         console_handler = logging.StreamHandler()
#         formatter = colorlog.ColoredFormatter(
#             "%(log_color)s%(asctime)s - %(name)s - [%(levelname)s] - %(message)s",
#             datefmt='%Y-%m-%d %H:%M:%S',
#             log_colors={
#                 'DEBUG': 'cyan',
#                 'INFO': 'green',
#                 'WARNING': 'yellow',
#                 'ERROR': 'red',
#                 'CRITICAL': 'bold_red',
#             }
#         )
#         console_handler.setFormatter(formatter)
#         self._log.addHandler(console_handler)
#         self._log.propagate = False

#         # Central command definitions
#         self.pull_command = Subcommand('pull')
#         self.pull_command.parser.add_option('--platform', default='all', dest='platform', choices=['all', 'spotify', 'youtube', 'a'], help='Specify the music platform (spotify, youtube)')
#         self.pull_command.parser.add_option('--type', dest='playlist_type', choices=VALID_PLAYLIST_TYPES, default='mm', help="Process 'pl' playlists or regular genre/subgenre playlists")
#         self.pull_command.parser.add_option('--no_db', action='store_true', help='Add retrieved info to the database')
#         self.pull_command.parser.add_option('--name', default='all', dest='playlist_name', help='Name of the playlist to retrieve')
#         self.pull_command.func = self.pull_platform

#         return

#     def commands(self):
#         return [self.pull_command]
        
#     # PULL PLATFORM INTO DB
    
#     def pull_platform(self, lib, opts, args):
#         """This function pulls song_data from the specified platform and adds it to the library.

#         STEPS:
#             1. Create playlist platform set
#                 1.1 get platforms
#                 1.2 get all playlists
#                 1.3 filter playlists based on name, type, and ignore
#             2. Retrieve songs from playlists
#                 2.1 get raw tracks for playlist
#                 2.2 parse raw tracks into standardized format
#                 2.3 add playlist info to track dict
#                 2.4 add genre data based on playlist name
#             3. Add songs to database
#                 3.1 check if track exists in db
#                     3.1.1 based on youtube id
#                     3.1.2 based on spotify id
#                     3.1.3 based on title and artist
#                 3.2 if track does not exist, add to db
#                 3.3 if track exists, update track info

#         Args:
#             lib (_type_): _description_
#             opts (_type_): _description_
#             args (_type_): _description_

#         Returns:
#             _type_: _description_
#         """

#         self.lib = lib 

#         # ARGUMENTS
#         platforms = opts.platform
#         playlist_name = opts.playlist_name
#         playlist_type = opts.playlist_type
#         no_db = opts.no_db


#         # ========================
#         # 1. PLATFORM PLAYLIST SET
#         # ========================
#         # 1.1 get platforms 
#         # dict of platform_name: platform_class
#         if platforms == 'all':
#             platforms = VALID_PLATFORMS
#         else:
#             if type(platforms) == str:
#                 platforms = [platforms]
        
#         platforms = dict([(platform, self._get_plugin(platform)) for platform in platforms])

#         # 1.2 get all playlists
#         # dict of platform_name: [playlists]
#         playlists = dict([(platform, list()) for platform in VALID_PLATFORMS])

#         for name, platform in platforms.items():
#             with platform() as plugin:
#                 playlists[name].extend(plugin._get_all_playlists())

#         # 1.3 filter playlists based on name and platform
#         # dict of platform_name: [playlists_to_process]
#         playlists_to_process = dict([(platform, list()) for platform in VALID_PLATFORMS])
#         for platform_name, pl in playlists.items():
#             if playlist_name != 'all':
#                 playlists_to_process[platform_name].extend([p for p in pl if (
#                     (playlist_name.lower() in p['playlist_name'].lower()) and     # filter name
#                     (playlist_type in p['playlist_name']) and                   # filter type
#                     (playlist_name not in plugin.pl_to_skip) and                # filter ignore
#                     not (' pl ' in p['playlist_name'] and playlist_type == 'mm')  # Additional condition
#                 )])            
#             else:
#                 playlists_to_process[platform_name].extend([p for p in pl if (
#                     (playlist_type in p['playlist_name']) and                    # filter type
#                     (playlist_name not in plugin.pl_to_skip) and                   # filter ignore
#                     not (' pl ' in p['playlist_name'] and playlist_type == 'mm')  # Additional condition
#                 )])

#         for platform in VALID_PLATFORMS:
#             color = PLATFORM_LOG_COLOR[platform]
#             self._log.log("info",f"{YELLOW}{len(playlists_to_process[platform])} playlists{RESET} to process for {color}{platform}{RESET}")

#         # ========================
#         # 2. RETRIEVE SONGS
#         # ========================
#         for platform_name, playlists in playlists_to_process.items():
#             if not playlists:
#                 continue
#             platform = platforms[platform_name]

#             with platform() as plugin:
#                 for playlist in playlists:
#                     song_data = list()
#                     # get tracks for playlist
#                     tracks = plugin._get_playlist_tracks(playlist['playlist_id'])
#                     # parse track
#                     parsed_tracks = [plugin._parse_track_item(lib, item) for item in tracks['items']]
                    
#                     # add playlist info to track dict
#                     for track in parsed_tracks:
#                         if not track: 
#                             continue
#                         try:
#                             track['platform'] = platform_name
#                             track['playlist_name'] = playlist['playlist_name']
#                             track['playlist_id'] = playlist['playlist_id']
#                             track['playlist_description'] = playlist['playlist_description']
#                         # add genre data based on playlist name
#                             if playlist_type == 'mm':
#                                 split_name = playlist['playlist_name'].split(' - ')
#                                 track['genre'] = split_name[1]
#                                 track['subgenre'] = split_name[2] if len(split_name) > 2 else ''
                        
#                             song_data.append(SongData(**track).model_dump())
#                         except Exception as e:
#                             self._log.error(f"Error adding playlist info to track: {e}")
#                             continue
                    
#                     color = PLATFORM_LOG_COLOR[platform_name]
#                     self._log.log("info",f"{BLUE_BRIGHT}{len(parsed_tracks)} songs{RESET} found in {BLUE_BRIGHT}{playlist['playlist_name']}{RESET} on {color}{platform_name}{RESET}")
           
#                     if not no_db:
#                         new, existing = self.add_to_db(lib, song_data)

#                         self._log.log("info",f"{CYAN}{len(new)}{RESET} new songs added to the database{RESET}")
#                         self._log.log("info",f"{CYAN}{len(existing)}{RESET} existing songs updated in the database{RESET}")
#                         self._log.log("info",f"{CYAN}{len(new) + len(existing)}/{len(song_data)}{RESET} total songs processed{RESET}")
#                         self._log.log("info","") 

#     # SYNC PLATFORMS
    
#     def _get_plugin(self, platform):
#         """Return the appropriate plugin class based on the platform."""
#         if platform == 'spotify' :
#             return spotify_plugin
#         elif platform == 'youtube':
#             return youtube_plugin
#         else:
#             raise ValueError(f"Unsupported platform: {platform}")        
    
#     def add_to_db(self, lib, song_data):
#         """Add song_data to the database.

#         Args:
#             lib (_type_): _description_
#             song_data (_type_): _description_

#         Returns:
#             _type_: _description_
#         """

#         exists = list()
#         new = list()

#         for song in song_data:
#             # correctly format artists into a list
#             artists = ','.join(sorted(list(set(song.pop('artists')))))
#             song['artists'] = artists
            
            
#             item = self._get_item_if_exists(lib, song)

#             if item:
#                 is_new = False
#                 row_id = item.id 
#             else:
#                 is_new = True
#                 row_id = None
#                 song['added'] = datetime.datetime.now().timestamp()


#             query, subvals = self._gen_store_item_q(song, row_id=row_id, is_new_row=is_new)

#             if query:
#                 with lib.transaction() as tx:
#                     tx.mutate(query, subvals)



#             item = self._get_item_if_exists(lib, song)

#             if is_new:
#                 new.append(item)
#             else:
#                 exists.append(item)

#         return new, exists
    
#     def _gen_store_item_q(self, update_data, table_name='items', row_id=None, is_new_row=False):
#             # Assuming that the connection is already established and available as conn
#         # Filter the update_data dictionary to remove None or empty values
        
#         filtered_data = {k: v for k, v in update_data.items() if v not in [None, ""] and k in Item._fields}

#         # If no valid data is present, return early
#         if not filtered_data:
#             return None, []

#         if is_new_row:
#             # For new row insertion, construct the INSERT query
#             columns = ", ".join(filtered_data.keys())
#             placeholders = ", ".join(["?" for _ in filtered_data.keys()])
#             query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
#             values = list(filtered_data.values())
#         else:
#             # For updating an existing row, construct the UPDATE query
#             if row_id is None:
#                 raise ValueError("row_id is required for updating an existing row.")

#             set_clause = ", ".join([f"{k} = ?" for k in filtered_data.keys()])
#             query = f"UPDATE {table_name} SET {set_clause} WHERE id = ?"
#             values = list(filtered_data.values()) + [row_id]

#         return query, values


#         pass

#     def _get_item_if_exists(self, lib, song):

#         """Check if song_data exists in the database.

#         Args:
#             lib (_type_): _description_
#             song_data (_type_): _description_

#         Returns:
#             _type_: _description_
#         """

#         item = None

#         # Check if song exists in db using platform ids
#         platform_ids = dict([(platform, song[f'{platform}_id']) for platform in VALID_PLATFORMS if song[f'{platform}_id']])
#         for platform, platform_id in platform_ids.items():
#             q = f'{platform}_id:"{platform_id}"'
#             item = self.lib.items(q).get()
#             if item:
#                 self._log.log("debug",f"Found item {item} using {platform} id")
#                 return item
        
#         # Check if song exists in db using title and artist
#         if not item:
#             try:
#                 title = song['title']
#                 remixer = song.get('remixer', '')
#                 artist = song.get('main_artist', '')
#                 feat_artist = song.get('feat_artist', '')
                
#                 t = RegexpQuery('title', f'(?i){re.escape(title)}')  # Case-insensitive title match
#                 a = RegexpQuery('artist', f'(?i){re.escape(artist)}')  # Case-insensitive artists match
#                 main_a = RegexpQuery('main_artist', f'(?i){re.escape(artist)}')
#                 r = RegexpQuery('remixer', f'(?i){re.escape(remixer)}') if remixer else None
#                 f = RegexpQuery('feat_artist', f'(?i){re.escape(feat_artist)}') if feat_artist else None

#                 artist_q = OrQuery([a, main_a])
#                 queries = [t, artist_q]    
#                 queries += [r] if remixer else []
#                 queries += [f] if feat_artist else []

#                 c = AndQuery(queries)
#                 items = lib.items(c)
#                 item = items[0]
#             except (IndexError, TypeError) as e:
#                 item = None
#                 self._log.log("debug",f"Item not found in db: {e}")
            
#             # self._log.log("info",f"{YELLOW_BRIGHT}Found item {RESET}{item} using song info")
#             return item
    
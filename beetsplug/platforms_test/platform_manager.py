from beets.plugins import BeetsPlugin
from beets.ui import Subcommand

from beetsplug.platforms_test.youtube import youtube_plugin
from beetsplug.platforms_test.spotify import spotify_plugin
from beetsplug.platforms_test.platform import VALID_PLATFORMS, VALID_PLAYLIST_TYPES
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
        self._log = logging.getLogger('beets.platform_manager')

        # Add a simple console handler
        console_handler = logging.StreamHandler()
        formatter = colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s - %(name)s - [%(levelname)s] - %(message)s",
            datefmt='%Y-%m-%d %H:%M:%S',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red',
            }
        )
        console_handler.setFormatter(formatter)
        self._log.addHandler(console_handler)
        self._log.propagate = False

        # Central command definitions
        self.pull_command = Subcommand('pull')
        self.pull_command.parser.add_option('--platform', default='all', dest='platform', choices=['all', 'spotify', 'youtube', 'a'], help='Specify the music platform (spotify, youtube)')
        self.pull_command.parser.add_option('--type', dest='playlist_type', choices=VALID_PLAYLIST_TYPES, default='mm', help="Process 'pl' playlists or regular genre/subgenre playlists")
        self.pull_command.parser.add_option('--no_db', action='store_true', help='Add retrieved info to the database')
        self.pull_command.parser.add_option('--name', default='all', dest='playlist_name', help='Name of the playlist to retrieve')
        self.pull_command.func = self.pull_platform

        return

    def commands(self):
        return [self.pull_command]
        
    def pull_platform(self, lib, opts, args):
        """This function pulls song_data from the specified platform and adds it to the library.

        STEPS:
            1. Create playlist platform set
                1.1 get platforms
                1.2 get all playlists
                1.3 filter playlists based on name, type, and ignore
            2. Retrieve songs from playlists
                2.1 get raw tracks for playlist
                2.2 parse raw tracks into standardized format
                2.3 add playlist info to track dict
                2.4 add genre data based on playlist name
            3. Add songs to database
                3.1 check if track exists in db
                    3.1.1 based on youtube id
                    3.1.2 based on spotify id
                    3.1.3 based on title and artist
                3.2 if track does not exist, add to db
                3.3 if track exists, update track info

        Args:
            lib (_type_): _description_
            opts (_type_): _description_
            args (_type_): _description_

        Returns:
            _type_: _description_
        """

        self.lib = lib 

        # ARGUMENTS
        platforms = opts.platform
        playlist_name = opts.playlist_name
        playlist_type = opts.playlist_type
        no_db = opts.no_db


        # ========================
        # 1. PLATFORM PLAYLIST SET
        # ========================
        # 1.1 get platforms 
        # dict of platform_name: platform_class
        if platforms == 'all':
            platforms = VALID_PLATFORMS
        else:
            if type(platforms) == str:
                platforms = [platforms]
        
        platforms = dict([(platform, self._pull_platform_get_plugin(platform)) for platform in platforms])

        # 1.2 get all playlists
        # dict of platform_name: [playlists]
        playlists = dict([(platform, list()) for platform in VALID_PLATFORMS])

        for name, platform in platforms.items():
            with platform() as plugin:
                playlists[name].extend(plugin._get_all_playlists())

        # 1.3 filter playlists based on name and platform
        # dict of platform_name: [playlists_to_process]
        playlists_to_process = dict([(platform, list()) for platform in VALID_PLATFORMS])
        for platform_name, pl in playlists.items():
            if playlist_name != 'all':
                playlists_to_process[platform_name].extend([p for p in pl if (
                    (playlist_name.lower() in p['playlist_name'].lower()) &     # filter name
                    (playlist_type in p['playlist_name']) &                     # filter type
                    (playlist_name not in plugin.pl_to_skip)                    # filter ignore
                )])

        for platform in VALID_PLATFORMS:
            color = PLATFORM_LOG_COLOR[platform]
            self._log.info(f"{YELLOW}{len(playlists_to_process[platform])} playlists{RESET} to process for {color}{platform}{RESET}")

        # ========================
        # 2. RETRIEVE SONGS
        # ========================
        song_data = list()
        for platform_name, playlists in playlists_to_process.items():
            if not playlists:
                continue
            platform = platforms[platform_name]

            with platform() as plugin:
                for playlist in playlists:
                    
                    # get tracks for playlist
                    tracks = plugin._get_playlist_tracks(playlist['playlist_id'])
                    parsed_tracks = [plugin._parse_track_item(item) for item in tracks['items']]
                    
                    # add playlist info to track dict
                    for track in parsed_tracks:
                        try:
                            track['platform'] = platform_name
                            track['playlist_name'] = playlist['playlist_name']
                            track['playlist_id'] = playlist['playlist_id']
                            track['playlist_description'] = playlist['playlist_description']
                        # add genre data based on playlist name
                            if playlist_type == 'mm':
                                split_name = playlist['playlist_name'].split(' - ')
                                track['genre'] = split_name[1]
                                track['subgenre'] = split_name[2] if len(split_name) > 2 else ''
                        
                            song_data.append(SongData(**track).model_dump())
                        except Exception as e:
                            self._log.error(f"Error adding playlist info to track: {e}")
                            continue
                    
                    color = PLATFORM_LOG_COLOR[platform_name]
                    self._log.info(f"{BLUE_BRIGHT}{len(parsed_tracks)} songs{RESET} found in {BLUE_BRIGHT}{playlist['playlist_name']}{RESET} on {color}{platform_name}{RESET}")
           
        # ========================
        # 3. ADD SONGS TO DATABASE
        # ========================
        # 3.1 check if track exists in db
        # 3.1.1 based on youtube id
        # 3.1.2 based on spotify id
        # 3.1.3 based on title and artist
        # 3.2 if track does not exist, add to db
        # 3.3 if track exists, update track info
        if not no_db:
            new, existing = self.add_to_db(lib, song_data)

            self._log.info(f"{CYAN}{len(new)}{RESET} new songs added to the database{RESET}")
            self._log.info(f"{CYAN}{len(existing)}{RESET} existing songs updated in the database{RESET}")
            self._log.info(f"{CYAN}{len(new) + len(existing)}/{len(song_data)}{RESET} total songs processed{RESET}")
            self._log.info("")

    def _pull_platform_get_plugin(self, platform):
        """Return the appropriate plugin class based on the platform."""
        if platform == 'spotify' :
            return spotify_plugin
        elif platform == 'youtube':
            return youtube_plugin
        else:
            raise ValueError(f"Unsupported platform: {platform}")        
    
    def add_to_db(self, lib, song_data):
        """Add song_data to the database.

        Args:
            lib (_type_): _description_
            song_data (_type_): _description_

        Returns:
            _type_: _description_
        """

        exists = list()
        new = list()

        for song in song_data:
            # correctly format artists into a list
            artists = ','.join(sorted(list(set(song.pop('artists')))))
            song['artists'] = artists
            
            
            item = self._get_item_if_exists(lib, song)

            if item:
                is_new = False
                row_id = item.id 
            else:
                is_new = True
                row_id = None
                song['added'] = datetime.datetime.now().timestamp()


            query, subvals = self._gen_store_item_q(song, row_id=row_id, is_new_row=is_new)

            if query:
                with lib.transaction() as tx:
                    tx.mutate(query, subvals)



            item = self._get_item_if_exists(lib, song)

            if is_new:
                new.append(item)
            else:
                exists.append(item)

        return new, exists
    
    def _gen_store_item_q(self, update_data, table_name='items', row_id=None, is_new_row=False):
            # Assuming that the connection is already established and available as conn
        # Filter the update_data dictionary to remove None or empty values
        
        filtered_data = {k: v for k, v in update_data.items() if v not in [None, ""] and k in Item._fields}

        # If no valid data is present, return early
        if not filtered_data:
            return None, []

        if is_new_row:
            # For new row insertion, construct the INSERT query
            columns = ", ".join(filtered_data.keys())
            placeholders = ", ".join(["?" for _ in filtered_data.keys()])
            query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
            values = list(filtered_data.values())
        else:
            # For updating an existing row, construct the UPDATE query
            if row_id is None:
                raise ValueError("row_id is required for updating an existing row.")

            set_clause = ", ".join([f"{k} = ?" for k in filtered_data.keys()])
            query = f"UPDATE {table_name} SET {set_clause} WHERE id = ?"
            values = list(filtered_data.values()) + [row_id]

        return query, values


        pass

    def _get_item_if_exists(self, lib, song):

        """Check if song_data exists in the database.

        Args:
            lib (_type_): _description_
            song_data (_type_): _description_

        Returns:
            _type_: _description_
        """

        item = None

        # Check if song exists in db using platform ids
        platform_ids = dict([(platform, song[f'{platform}_id']) for platform in VALID_PLATFORMS if song[f'{platform}_id']])
        for platform, platform_id in platform_ids.items():
            q = f'{platform}_id:"{platform_id}"'
            item = self.lib.items(q).get()
            if item:
                self._log.debug(f"Found item {item} using {platform} id")
                return item
        
        # Check if song exists in db using title and artist
        if not item:
            try:
                title = song['title']
                remixer = song.get('remixer', '')
                artist = song.get('main_artist', '')
                feat_artist = song.get('feat_artist', '')
                
                t = RegexpQuery('title', f'(?i){re.escape(title)}')  # Case-insensitive title match
                a = RegexpQuery('artist', f'(?i){re.escape(artist)}')  # Case-insensitive artists match
                main_a = RegexpQuery('main_artist', f'(?i){re.escape(artist)}')
                r = RegexpQuery('remixer', f'(?i){re.escape(remixer)}') if remixer else None
                f = RegexpQuery('feat_artist', f'(?i){re.escape(feat_artist)}') if feat_artist else None

                artist_q = OrQuery([a, main_a])
                queries = [t, artist_q]    
                queries += [r] if remixer else []
                queries += [f] if feat_artist else []

                c = AndQuery(queries)
                items = lib.items(c)
                item = items[0]
            except (IndexError, TypeError) as e:
                item = None
                self._log.debug(f"Item {song['artist'] - song['title']} not found in db: {e}")
            return item
    
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
from itertools import chain
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

        # 1.1 Map each platform string to a plugin class
        self.platform_dict = {
            pf: self._get_plugin(pf)
            for pf in VALID_PLATFORMS
        }

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

    def pull_data(
            self,
            lib,
            playlist_name=None
    ):
        """This function pulls all tracks for all playlists (that are valid given the sync pattern constraint). 
        
        Keyword arguments:
        argument -- description
        Return: A dictionary that looks like this:
        {
            platform: {
                playlist_name: [tracks]
            }
        }
        """
        
        # 1.1 Map each platform string to a plugin class

        data = {pf: {} for pf in VALID_PLATFORMS}

        # 1.2 Get all playlists from each platform
        all_playlists = {pf: [] for pf in VALID_PLATFORMS}
        for name, pf_plugin_cls in self.platform_dict.items():
            with pf_plugin_cls() as plugin:
                all_playlists[name].extend(plugin._get_all_playlists())

        # 1.3 filter playlists according to 'sync_playlists' string pattern (specified in config)
        playlists_to_sync = dict([(platform_name, []) for platform_name in VALID_PLATFORMS])
        if not playlist_name:
            sync_pattern = self.config['sync_pattern'].get()
        else: sync_pattern = playlist_name
        for platform in self.platform_dict.keys():
            for playlist in all_playlists[platform]:
                if sync_pattern in playlist['playlist_name']:
                    playlists_to_sync[platform].append(playlist)

        # Get all tracks for the playlists and store them.
        for platform, playlists in playlists_to_sync.items():
            for playlist in playlists:
                with self.platform_dict[platform]() as plugin:
                    tracks = plugin._get_playlist_tracks(playlist['playlist_id'])
                    playlist_tracks = [plugin._parse_track_item(lib, track) | playlist for track in tracks]   
                    data[platform][playlist['playlist_name']] = playlist_tracks
                break    

        return data
       
    def _platform_diff(
            self,
            lib,
            data
    ):


        def collect_all_names(data: dict[str, dict[str, list]]) -> set[str]:
            names = set()
            for by_playlist in data.values():
                names.update(by_playlist.keys())
            return names

        playlist_names = collect_all_names(data)
        playlist_diffs = dict()

        for playlist in playlist_names:
            track_set = dict()
            missing = dict()

            # calculate sets per PLATFORM
            for pf in data.keys():
                # empty set if playlist does not exist
                if playlist not in data[pf].keys():
                    track_set[pf] = set()
                else:
                    song_models = [SongData(**song) for song in data[pf][playlist]]
                    # song_tuples = [(tuple(song['artists']), song['title']) for song in song_models]
                    track_set[pf] = set(song_models)
                    
            
            # calculate TOTAL set
            track_set['total'] = set(chain.from_iterable([track_set[pf] for pf in data.keys()]))
            # calculate MISSING set per platform
            for pf in data.keys():
                missing[pf] = track_set['total'].difference(track_set[pf])
            
            playlist_diffs[playlist] = missing

        return playlist_diffs

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


        # 1.2 Get all playlists from each platform
        all_playlists = {pf: [] for pf in VALID_PLATFORMS}
        for name, pf_plugin_cls in self.platform_dict.items():
            with pf_plugin_cls() as plugin:
                all_playlists[name].extend(plugin._get_all_playlists())


        # 1.3 Filter playlists based on the playlist name, type, etc.
        #     We'll store them in a dict: {platform_name: [playlists_to_process]}
        playlists_to_process = {pf: [] for pf in VALID_PLATFORMS}
        for pf_name, pl_list in all_playlists.items():
            if not pl_list:
                continue

            # We'll need to open the plugin instance again to check `plugin.pl_to_skip`, etc.
            pf_plugin_cls = self.platform_dict.get(pf_name)
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

            pf_plugin_cls = self.platform_dict.get(pf_name)
            if not pf_plugin_cls:
                continue

            with pf_plugin_cls() as plugin:
                for pl in playlists:
                    # 2.1 get raw tracks
                    tracks = plugin._get_playlist_tracks(pl['playlist_id'])

                    # 2.2 parse raw tracks
                    parsed_tracks = [
                        plugin._parse_track_item(lib, item)
                        for item in tracks
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

   
    def update_playlists(self, lib, diff):
        

        for playlist_name, sets in diff.items():
            
            
            for platform, platform_plugin in self.platform_dict.items():
                # 1. Make sure playlist exists
                with platform_plugin() as plugin:
                    plugin._create_playlist(playlist_name)

                    # 2. add songs to playlist
                    songs = sets[platform]

                    for song in songs:
                        search_results = plugin._search_song(lib, song)
                        print(search_results)
                        # match = platform_plugin._match_results(song, search_results)
                 

        return
   
   
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

            return




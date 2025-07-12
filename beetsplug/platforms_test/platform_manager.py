from beets.plugins import BeetsPlugin
from beets.ui import Subcommand

from beetsplug.platforms_test.youtube import youtube_plugin
from beetsplug.platforms_test.spotify import spotify_plugin
from beetsplug.platforms_test.platform import VALID_PLATFORMS, VALID_PLAYLIST_TYPES
from beetsplug.custom_logger import CustomLogger
from beetsplug.models.songdata import SongData, PlaylistData
from beets.library import Item, DateType
from beets.dbcore.query import AndQuery, RegexpQuery, OrQuery


# Varia
import re
import sqlite3
import time
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

    
    # ──────────────────────────────────────────────────────────────────────────
    # PULL DATA
    # ──────────────────────────────────────────────────────────────────────────    
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
                    playlist_tracks = [plugin._parse_song_item(lib, track | playlist) for track in tracks]   
                    data[platform][playlist['playlist_name']] = playlist_tracks
                break    

        return data
       
    def _platform_diff(
            self,
            lib,
            data,
            
    ):


        def collect_all_names(data: dict[str, dict[str, list]]) -> set[str]:
            names = set()
            for by_playlist in data.values():
                names.update(by_playlist.keys())
            return names

        playlist_names = collect_all_names(data)
        playlist_diffs = dict()
        playlist_total = dict()

        for playlist in playlist_names:
            track_set = dict()
            missing = dict()

            # calculate sets per PLATFORM
            for pf in data.keys():
                # empty set if playlist does not exist
                if playlist not in data[pf].keys():
                    track_set[pf] = set()
                else:
                    song_models = [song for song in data[pf][playlist]]
                    # song_tuples = [(tuple(song['artists']), song['title']) for song in song_models]
                    track_set[pf] = set(song_models)
                    
            
            # calculate TOTAL set
            track_set['total'] = set(chain.from_iterable([track_set[pf] for pf in data.keys()]))
            playlist_total[playlist] = track_set['total']

            # calculate MISSING set per platform
            for pf in data.keys():
                missing[pf] = track_set['total'].difference(track_set[pf])
            
            playlist_diffs[playlist] = missing

        return playlist_diffs, playlist_total
  
    
    # ──────────────────────────────────────────────────────────────────────────
    # PLAYLISTS
    # ──────────────────────────────────────────────────────────────────────────
    def sync_playlists(self, lib, diff, total):
        
        playlist_ids = dict()

        for playlist_name, sets in diff.items(): 
            self._log.log("info", f"STARTING SYNC: {playlist_name}")
            # print(total[playlist_name])
            total_tracks = total[playlist_name]
            # print(len(total_tracks))
            self._log.log("info", f"TOTAL TRACKS : {len(total_tracks)}")
            songs_not_found = 0

            for platform, platform_plugin in self.platform_dict.items():

                
                

                # 1. Make sure playlist exists
                with platform_plugin() as plugin:
                    playlist_id = plugin._create_playlist(playlist_name)
                    playlist_ids[f'{platform}'] = playlist_id

                    self._log.log("info", f"{len(sets[platform])} songs MISSING in playlist {playlist_name} on {platform}")

                    # 2. Loop over songs
                    songs = sets[platform]

                    for song in songs:
                        # 2.1 search song and parse result
                        search_results = plugin._search_song(lib, song)

                        if not search_results:
                            self._log.log("debug", f"No results found for song: {song} on platform {platform}")
                            continue
                        parsed_results = plugin._parse_search_results(lib, search_results)

                        # 2.2 match result against song
                        song_match = None
                        for result in parsed_results:
                            if result == song:
                                song_match = result
                                break
                        
                        # 2.3 no match: continue with next song
                        if not song_match:
                            songs_not_found += 1
                            self._log.log("debug", f"No MATCHES for song: {song} on platform {platform}")
                            continue
                        
                        
                        # 3. add song to playlist
                        plugin._add_song_to_playlist(song_match, playlist_id)

                        # 4. Update beets database entry
                        def sync_models(primary: SongData, 
                                        secondary: SongData) -> SongData:
                            p = primary.model_dump()
                            s = secondary.model_dump()
                            merged = {
                                key: p[key] if p[key] not in [None, '', [], {}, 0] else s.get(key)
                                for key in p
                            }

                            song_data = SongData(**merged)
                            return song_data

                        # 4.1 Update Items table
                        updated_song = sync_models(song_match, song)
                        self._update_song(lib, updated_song)
            
            self._log.log('debug', f"FINISHED SYNC: {playlist_name}. {songs_not_found}/{len(sets[platform])} songs NOT ADDED")
        
        
        
        for playlist_name, songs in total.items():
            self._log.log('debug', f"STARTING THE UPDATE OF PLAYLISTS IN DATABASE")

            # playlist data
            playlist_data = self._get_playlist_if_exits(lib, playlist_name)
            playlist_data['last_edited_at'] = str(datetime.datetime.now().timestamp())
            playlist_data['name'] = playlist_name
            for platform in VALID_PLATFORMS:
                playlist_data[f'{platform}_id'] = playlist_ids[platform]

            # 4.2 Update Playlist table
            playlist_data = PlaylistData(**playlist_data)
            self._update_playlist(lib, playlist_name, playlist_data)
            [
                self._update_playlist_items(lib, playlist_data, song) for song in songs
            ]
            self._log.log("debug", f"succesfully updated playlist item linking table for playlist {playlist_name}")
        return
   
    def _update_playlist(self, lib, playlist_name: str, playlist: PlaylistData):

        with lib.transaction() as tx:
            result = tx.query(
                "SELECT id from playlist WHERE name = ?",
                (playlist_name,)
            )
        
            if result:
                tx.mutate(
                    "UPDATE playlist SET spotify_id = ?, youtube_id = ?, last_edited_at = ? WHERE name = ?",
                    (playlist.spotify_id, playlist.youtube_id, playlist.last_edited_at, playlist_name)
                )
            else:
                # 2b. Insert new record
                tx.mutate(
                    "INSERT INTO playlist (name, spotify_id, youtube_id, last_edited_at) VALUES (?, ?, ?, ?)",
                    (playlist_name, playlist.spotify_id, playlist.youtube_id, playlist.last_edited_at)
            )
        
        self._log.log("debug", f"succesfully updated playlist in db: {playlist_name}")
        return

    def _update_playlist_items(self, lib, playlist: PlaylistData, song: SongData):

        with lib.transaction() as tx:

            playlist_id = dict(tx.query(
                "SELECT id FROM playlist WHERE name = ? COLLATE NOCASE",
                (playlist.name,)
            )[0])['id']


            song = self._get_item_if_exists(lib, song.model_dump())

            if not song:
                return
            
            song_id = song.id

            try:
                tx.mutate(
                    "INSERT INTO playlist_item (playlist_id, item_id) VALUES (?, ?)",
                    (playlist_id, song_id)
                )
            except sqlite3.IntegrityError as e:
                # unique constraint failed
                pass
        return

    def _get_playlist_if_exits(self, lib, playlist_name):
        with lib.transaction() as tx:
            results = tx.query(
                "SELECT * from playlist WHERE name = ?",
                (playlist_name,)
            )
            result_dicts = [dict(result) for result in results]

            if result_dicts:
                playlist_data = result_dicts[0]
                return playlist_data
            else:
                return {}

    # ──────────────────────────────────────────────────────────────────────────
    # SONGS / ITEMS TABLE
    # ──────────────────────────────────────────────────────────────────────────
    def _update_song(self, lib, song: SongData):
            """
            Add or update the song_data in the beets library DB.
            
            Returns:
                (list_of_new_items, list_of_existing_items)
            """

            song = song.model_dump()

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
                return True
            elif not is_new and item:
                return False

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



    # ──────────────────────────────────────────────────────────────────────────
    # HELPER
    # ──────────────────────────────────────────────────────────────────────────
    def _get_plugin(self, platform):
        """Return the appropriate plugin class based on the platform."""
        if platform == 'spotify':
            return spotify_plugin
        elif platform == 'youtube':
            return youtube_plugin
        else:
            raise ValueError(f"Unsupported platform: {platform}")


    
 




    def add_to_db(self, lib, songs: List[SongData]):
            """
            Add or update the song_data in the beets library DB.
            
            Returns:
                (list_of_new_items, list_of_existing_items)
            """
            exists = []
            new = []


            for song in songs:
                
                song = song.model_dump()
                
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

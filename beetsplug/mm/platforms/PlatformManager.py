# Beets
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand
from beets.library import Item
from beets import config
from beets.dbcore.query import AndQuery, RegexpQuery

from beetsplug.mm.platforms.SpotifyPlugin import spotify_plugin
from beetsplug.mm.platforms.YoutubePlugin import youtube_plugin
from beetsplug.ssp import SongStringParser

# Varia
import re
import sqlite3
import logging
import datetime
from functools import wraps
from typing import List, Dict


def escape_quotes(value):
    """Escape both single and double quotes in the value."""
    return value.replace('"', '\\"').replace("'", "\\'")

class PlatformManager(BeetsPlugin):
    
    def __init__(self):

        super().__init__()
        self._log = logging.getLogger('beets.platform_manager')
        self.ssp = SongStringParser()

        # Central command definitions
        self.add_command = Subcommand('add', help='Add tracks to a playlist on a specified platform')
        self.add_command.parser.add_option('--platform', dest='platform', choices=['spotify', 'youtube', 'sf', 'yt'], help='Specify the music platform (spotify, youtube)')
        self.add_command.parser.add_option('-p', '--playlist', dest='playlist', help='Playlist name or ID')
        self.add_command.parser.add_option('-s', '--songs', dest='songs', help='List of song dictionaries')
        self.add_command.func = self.add_to_playlist

        self.pull_command = Subcommand('pull')
        self.pull_command.parser.add_option('--platform', dest='platform', choices=['all', 'spotify', 'youtube', 'a'], help='Specify the music platform (spotify, youtube)')
        self.pull_command.parser.add_option('--type', dest='playlist_type', choices=['pl', 'mm'], default=None, help="Process 'pl' playlists or regular genre/subgenre playlists")
        self.pull_command.parser.add_option('--db', action='store_true', help='Add retrieved info to the database')
        self.pull_command.parser.add_option('--name', dest='playlist_name', help='Name of the playlist to retrieve')
        self.pull_command.func = self.pull_platform

    def commands(self):
        return [self.add_command, self.pull_command]

    def setup(self, lib):
        self.lib = lib
        with self.lib.transaction() as tx:
            tx.query("""
            CREATE TABLE IF NOT EXISTS playlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                description TEXT,
                spotify_id TEXT,
                youtube_id TEXT,
                path TEXT,
                last_edited_at DATE,
                type TEXT
            );
            """)
            tx.query("""
            CREATE TABLE IF NOT EXISTS playlist_item (
                playlist_id INTEGER,
                item_id INTEGER,
                FOREIGN KEY (playlist_id) REFERENCES playlist(id),
                FOREIGN KEY (item_id) REFERENCES items(id),
                PRIMARY KEY (playlist_id, item_id)
            );
            """)

    # MEAT

    def add_to_playlist(self, lib, opts, args):
        """Handle add command and dispatch to the correct platform plugin."""
        platform = opts.platform
        playlist = opts.playlist
        songs = opts.songs

        plugin = self.get_plugin_for_platform(platform)
        plugin.add_to_playlist(playlist, songs)

    def pull_platform(self, lib, opts, args):

        self.lib = lib 
        # return
        existing_items = list()
        new_items = list()

        # GET ARGUMENTS
        platform = opts.platform
        playlist_name = opts.playlist_name
        playlist_type = opts.playlist_type
        db = opts.db
        
        # PLATFORMS TO PULL FROM
        platforms = ['youtube', 'spotify'] if platform == ('a' or 'all') else [platform]

        # GET SONGS
        for platform in platforms:
            
            self._log.info(f'\t PULL songs FROM {platform}')

            items, song_data = self._retrieve_songs(platform, playlist_name, playlist_type)
            existing_items += items

        self._log.info(f"\t {len(existing_items)} songs PULLED from PLATFORMS")

        if db:
            print(song_data)
            added_to_db = self._insert_songs(lib, song_data)
            new_items += added_to_db
            self._log.info(f"\t {len(added_to_db)} songs PULLED from DATABASE")



        items = existing_items + new_items

        self._log.info(f"\t {len(items)} songs PULLED in TOTAL")

        return items
    
    def _retrieve_songs(self, platform, playlist_name=None, playlist_type=None, skip_existing=True) -> List[Dict]:
        """Handle retrieve command and dispatch to the correct platform plugin."""
        
        existing_items = list()
        new_song_data = list()

        # GET PLUGIN
        p = self._get_plugin_for_platform(platform)

        with p() as plugin:
            # get playlists to process based on filters
            playlists_to_process = self._get_playlists(plugin, playlist_name, playlist_type)
            for playlist in playlists_to_process:
                existing_songs = list()
                new_songs = list()

                playlist_name = playlist['playlist_name']

                self._log.info(f"\t\t {playlist_name}")


                if playlist:
                    # Get tracks
                    tracks = plugin._get_playlist_tracks(playlist['playlist_id'])
                    
                    # parse tracks
                    for item in tracks['items']:
                        id_field = f'{platform}_id'
                        if platform == 'youtube':
                            id_value = item[id_field]
                        elif platform == 'spotify':
                            id_value = item['track']['id']
                        
                        id_q = f'{id_field}:"{id_value}"'
                        exists = self.lib.items(id_q).get()

                        if skip_existing and exists:
                            existing_songs.append(exists)
                            continue

                        song_data = plugin._parse_track_item(item)
                        
                        # add playlist info to track dict
                        song_data['platform'] = platform
                        song_data['playlist_name'] = playlist_name
                        song_data['playlist_id'] = playlist['playlist_id']
                        song_data['playlist_description'] = playlist['playlist_description']
                        
                        # add genre data based on playlist name
                        if ' pl ' not in playlist_name:
                            playlist_split = playlist['playlist_name'].split(' - ')
                            if len(playlist_split) > 2:
                                _, genre, subgenre = playlist_split
                                song_data['genre'] = genre
                                song_data['subgenre'] = subgenre
                            else:
                                _, genre = playlist_split
                                song_data['genre'] = genre
                                song_data['subgenre'] = ''
                        else:
                                song_data['genre'] = ''
                                song_data['subgenre'] = ''
                        
                        new_songs.append(song_data)

                existing_items += existing_songs
                new_song_data += new_songs

                self._log.info(f"\t\t\t {len(existing_songs + new_songs)} FOUND")
                self._log.info(f"\t\t\t {len(existing_songs)} KNOWN")
                self._log.info(f"\t\t\t {len(new_songs)} UNKNOPWN") 

        return existing_items, new_song_data
        
    def _insert_songs(self, lib, songs) -> List[Item]:
        items = list()

        current_playlist = None

        for song_data in songs:
            try:
                platform = song_data.pop('platform')
                p = {key: song_data.pop(key) for key in ['playlist_id', 'playlist_name', 'playlist_description'] if key in song_data}



                # UPSERT SONG      
                item = self._store_item(lib, song_data, update_genre=True)

                if not item:
                    self._log.error(f'\t\t\t SONG PROCESSING FAILED: {song_data}')
                    continue
                # UPSERT PLAYLIST
                playlist = self._store_playlist(lib, platform, p)
                # PLAYLIST_ITEM  RELATION
                self._store_playlist_relation(lib, item.id, playlist['id'])   
                items.append(item)

                song_string = self.ssp.string_from_item(item)
                self._log.info(f"\t\t\tADDED TO LIBRARY: {song_string}")
            except sqlite3.InterfaceError:
                self._log.info(f"\t\t\tUNABLE TO ADD: {song_data}")
        return items

    # HELPER

    def _get_plugin_for_platform(self, platform):
        """Return the appropriate plugin class based on the platform."""
        if platform == 'spotify' :
            return spotify_plugin
        elif platform == 'youtube':
            return youtube_plugin
        else:
            raise ValueError(f"Unsupported platform: {platform}")

    def _get_playlists(self, plugin, playlist_name, playlist_type) -> List[Dict]:
        # FILTER PLAYLISTS
        # all
        all_playlists = plugin._get_all_playlists()
        # filter mm playlists 
        playlists_to_process = [playlist for playlist in all_playlists if playlist['playlist_name'][:2] == plugin.valid_pl_prefix]
        # filter ignore
        playlists_to_process = [playlist for playlist in playlists_to_process if playlist['playlist_name'] not in plugin.pl_to_skip]                
        # filter type
        playlists_to_process = [playlist for playlist in playlists_to_process if playlist_type in playlist['playlist_name']] if playlist_type else playlists_to_process
        # filter name
        playlists_to_process = [playlist for playlist in playlists_to_process if playlist_name.lower() in playlist['playlist_name'].lower()] if playlist_name else playlists_to_process

        return playlists_to_process
    
    # DATABASE METHODS

    def _find_item(self, lib, song):
        try:
            title = song['title']
            remixer = song.get('remixer', '')
            artists = song.get('artists', '')
            feat_artist = song.get('feat_artist', '')

            t = RegexpQuery('title', re.escape(title))
            a = RegexpQuery('artists', re.escape(artists))
            r = RegexpQuery('remixer', re.escape(remixer))
            f = RegexpQuery('feat_artist', re.escape(feat_artist))

            queries = [t, a]
            queries += [r] if remixer else []
            queries += [f] if feat_artist else []

            c = AndQuery(queries)

            items = lib.items(c)
            i = items[0]
        except (IndexError, TypeError):
            i = None

        return i

    def _find_playlist(self, lib, playlist_name):
        with lib.transaction() as tx:
            result = tx.query("SELECT * FROM playlist WHERE name = ?", (playlist_name,))
            return result[0] if result else None    
    
    def _store_item(self, lib, song_data, update_genre=True):

        song = song_data
        artists = ','.join(sorted(list(set(song.pop('artists')))))
        # artists = ','.join(song.pop('artists'))
        song['artists'] = artists
        item = self._find_item(lib, song)
        current_time = datetime.datetime.now().isoformat()

        if item:
            is_new = False
            row_id = item.id 
        else:
            is_new = True
            row_id = None

        query, subvals = self._gen_store_item_q(song, row_id=row_id, is_new_row=is_new)

        if query:
            with lib.transaction() as tx:
                tx.mutate(query, subvals)


        item = self._find_item(lib, song)

        return item
    
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
    
    def _store_playlist(self, lib, platform, playlist):

        playlist_id = playlist['playlist_id']
        playlist_name = playlist['playlist_name']
        playlist_description = playlist['playlist_description']

        existing_playlist = self._find_playlist(lib, playlist_name)

        current_time = datetime.datetime.now().isoformat()

        if existing_playlist:
            spotify_id = existing_playlist['spotify_id']
            youtube_id = existing_playlist['youtube_id']
        else:
            spotify_id = playlist_id if platform == 'spotify' else ''
            youtube_id = playlist_id if platform == 'youtube' else ''   

        with lib.transaction() as tx:
            if existing_playlist:
                # Update existing playlist
                tx.query("""
                    UPDATE playlist SET description = ?, spotify_id = ?, youtube_id = ?, path = ?, last_edited_at = ?, type = ?
                    WHERE id = ?
                """, (playlist.get('playlist_description', ''), spotify_id, youtube_id, '', current_time, 'playlist', existing_playlist['id']))
                return existing_playlist
            else:
                # Create new playlist
                tx.query("""
                    INSERT INTO playlist (name, description, spotify_id, youtube_id, path, last_edited_at, type)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (playlist['playlist_name'], playlist.get('playlist_description', ''), spotify_id, youtube_id, '', current_time, 'playlist'))
                
                existing_playlist = self._find_playlist(lib, playlist_name)
                return existing_playlist
       
    def _store_playlist_relation(self, lib, item_id, playlist_id):
        with lib.transaction() as tx:
            tx.query("""
                INSERT OR IGNORE INTO playlist_item (playlist_id, item_id)
                VALUES (?, ?)
            """, (playlist_id, item_id))


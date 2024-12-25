from beets.plugins import BeetsPlugin
from beets.ui import Subcommand

from beetsplug.platforms_test.youtube import youtube_plugin
from beetsplug.platforms_test.spotify import spotify_plugin
from beetsplug.platforms_test.platform import VALID_PLATFORMS, VALID_PLAYLIST_TYPES

# Varia
import re
import sqlite3
import logging
import datetime
from functools import wraps
from typing import List, Dict



class PlatformManager(BeetsPlugin):
    def __init__(self):
        super().__init__()
        self._log = logging.getLogger('beets.platform_manager')

        # Central command definitions
        self.pull_command = Subcommand('pull')
        self.pull_command.parser.add_option('--platform', default='all', dest='platform', choices=['all', 'spotify', 'youtube', 'a'], help='Specify the music platform (spotify, youtube)')
        self.pull_command.parser.add_option('--type', dest='playlist_type', choices=VALID_PLAYLIST_TYPES, default='mm', help="Process 'pl' playlists or regular genre/subgenre playlists")
        self.pull_command.parser.add_option('--db', action='store_true', help='Add retrieved info to the database')
        self.pull_command.parser.add_option('--name', default='all', dest='playlist_name', help='Name of the playlist to retrieve')
        self.pull_command.func = self.pull_platform

        return

    def commands(self):
        return [self.pull_command]

    def _get_plugin_for_platform(self, platform):
        """Return the appropriate plugin class based on the platform."""
        if platform == 'spotify' :
            return spotify_plugin
        elif platform == 'youtube':
            return youtube_plugin
        else:
            raise ValueError(f"Unsupported platform: {platform}")
        

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

        existing_data = list()
        new_data = list()

        # ARGUMENTS
        platforms = opts.platform
        playlist_name = opts.playlist_name
        playlist_type = opts.playlist_type
        db = opts.db

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
        
        platforms = dict([(platform, self._get_plugin_for_platform(platform)) for platform in platforms])

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
            self._log.info(f"{len(playlists_to_process[platform])} playlists to process for {platform}")

        print()
        print()
        # ========================
        # 2. RETRIEVE SONGS
        # ========================
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


                    # add genre data based on playlist name


                    print(parsed_tracks[0])

                    self._log.info(f"{len(parsed_tracks)} songs found in {playlist['playlist_name']} on {platform_name}")
           

            for track in parsed_tracks:
                print(track)

                # 1. check if track exists in db

                # 1.1 based on youtube id
                # 1.2 based on spotify id
                # 1.3 based on title and artist

                # 2. if track does not exist, add to db

                # 3. if track exists, update track info



        # if db:
        #     print(song_data)
        #     added_to_db = self._insert_songs(lib, song_data)
        #     new_items += added_to_db
        #     self._log.info(f"\t {len(added_to_db)} songs PULLED from DATABASE")

        # items = existing_items + new_items
        # self._log.info(f"\t {len(items)} songs PULLED in TOTAL")

        # for item in items:
        #     print(item)

        # for songs in song_data:
        #     print(songs)

        # return items

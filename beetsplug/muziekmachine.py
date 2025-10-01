# beetsplug/my_pipeline.py

import logging
import asyncio

from beets.plugins import BeetsPlugin
from beets.ui import Subcommand
from beets.library import Library
from beets import config

from beetsplug.soulseek.SoulseekPlugin import SoulSeekPlugin
from beetsplug.platforms_test.platform_manager import PlatformManager	
from beetsplug.custom_logger import CustomLogger
from beetsplug.mm_rekordbox import RekordboxSyncPlugin
from beetsplug.utils.database import DataBaseUtils

from beetsplug.platforms_test.platform import VALID_PLATFORMS, VALID_PLAYLIST_TYPES
from beetsplug.models.songdata import SongData, PlaylistData

# TO DO
# PRIOTIRTIES
# - RKBX: BEETS sync
# - BEETS -> Playlist -> Platform Sync
# - SLSK: simplify search query if possible.

# - refactor pull_data to return playlistData ?? 
# - Update download part to downlaod based on SongData 
#       --dl='pipe' -> Only download missing songs that have been pulled by previous pipeline stage
#       --dl='time' -> Download missing songs from library that 
#       --dl='all' -> Get all missing songs that match
# - Rkbox Sync
# - DJ dir


# UTILITY
# - get all missing songs (songs that are in playlists/platforms, but not in root audio file dir)
# - get all songs from a playlist
# - get all playlists from
#       - a platforms
#       - total
#       - string matching
#       - type

# - PLAYLIST HANDLING
#       - use PlaylistData object (see models file)
#           - playlist types: genre, playlist, dj 
#       - Playlist Utility funcitons
#           - calculate diff between platforms, usb, rkbx, beets
# - PULLING / UPDATING DATA:
#       - update genre for pulled songs if they already exist but changed playlist on the platforms 
# - SYNC OPTIONS: 
#       - upgrade _get_playlist_diff() by adding USB & RKBX playlists to get_playlist_diff()
#       - come up with a way to handle playlist differences 
    #       - Lunion Loose Union (total set, without deletion)
    #       - Sunion Strict Union (total set, with deletion if existing song in playlist not in total set)
    #       - Lplatform Loose Platform (platform set, without deletion)
    #       - Splatform Strict Platform (platform set, with deletion)
    #       - How to handle platform priority??
# - LOGGING:
#       - sync platform
# - TESTING:
#       - rekordboxsync
#       - platform sync


class MuziekMachine(BeetsPlugin):

    # ===================================================================
    # SETUP COMMAND LINE STUFF
    # ===================================================================

    def __init__(self):
        super().__init__()
        self._log = CustomLogger("MuziekMachine", default_color="purple")

        self.dbu = DataBaseUtils()
        self.pm = PlatformManager()
        self.slsk = SoulSeekPlugin()

        # ---------------------------------------------------------------
        # COMPLETE PIPELINE
        # ---------------------------------------------------------------
        # Add the CLI command
        self.pipeline_cmd = Subcommand(
            'mm-run',
            help='Run custom pipeline: pull platforms -> download songs'
        )
        # sync playlists
        self.pipeline_cmd.parser.add_option(
            '--sync', default='', choices=['', 'Union'] + VALID_PLATFORMS
        )

        # platform
        self.pipeline_cmd.parser.add_option(
            '--platform', default='all',
            help='Which platform to pull from (all, spotify, youtube, etc.)'
        )

        # playlist name
        self.pipeline_cmd.parser.add_option(
            '--playlist', default='all',
            help='Which playlist to pull from (all, liked, etc.)'
        )
        # dl
        self.pipeline_cmd.parser.add_option(
            '--dl', default='pipe', choices=['pipe', 'time', 'all'],
        )
        # sync
        self.pipeline_cmd.parser.add_option(
            '--sync_rkbx', default='',
        )

        self.pipeline_cmd.func = self._cli_entrypoint

    def commands(self):
        return [self.pipeline_cmd]

    def _cli_entrypoint(self, lib, opts, args):
        """Handles CLI input and initiates the pipeline."""

        # platform
        platform_str = opts.platform
        # playlist
        playlist_str = opts.playlist
        # dl
        dl = opts.dl
        # sync playlists
        sync = opts.sync

        self._log.log("info", "Starting pipeline...")
        self.run_pipeline(lib, platform_str, playlist_str, dl, sync)
        self._log.log("info", "Pipeline completed.")

    # ===================================================================
    # FUNCTINALITIES: the actual functions called by CLI
    # ===================================================================
    
    def get_playlist():
        return

    def run_pipeline(self, lib, platform_str, playlist_str, dl, sync):
        """Runs complete pipeline for a give (set of) playlist(s).
        The pipeline consists of the following steps. Extension/module as prefix in caps:

        1. PM: pull data from platforms
        2. PM: sync data between platforms 
        3. SLSK: download missing songs
        4. AA: analyze song audio 
        5. RKBX: Sync beets / rekordbox 
        6. DJ: update DJ folders
        
        Keyword arguments:
        argument -- description
        Return: return_description
        """
    
        pm = PlatformManager()


        # ────────────────────────────────────────────────────────
        # Stage 0.0 : Pull platform data
        # ────────────────────────────────────────────────────────
        """PlatformManager.pull_data() Summary
        This step looks up the given playlist on all platforms and gets the song data for songs in those playlists
        
        Returns:
            dict: a nested dictionary with the following structure: 
            dict{
                <platform>: {
                    <playlist>: [ SongData ]
                }
            }
            
        """
        platform_data = pm.pull_data(lib, playlist_name=playlist_str)
        pulled_songs = [item for src in platform_data.values() for lst in src.values() for item in lst]

        # UGLY, FIX NONE VALUES IN PM.PULL_DATA METHOD
        pulled_songs = [song for song in pulled_songs if song]

        # ADD NEW SONGS TO DATABASE
        new_count = sum([self.dbu.add_or_update(lib, song) for song in pulled_songs])
        # self._log.log("info", f" STAGE 1 COMPLETED: Pulled {len(new_items)} new items, {len(updated_items)} updated items from platforms: {platform_str}, plalylist: {playlist_str}.")


        # ────────────────────────────────────────────────────────
        # Stage 1 : Sync playlists 
        # ────────────────────────────────────────────────────────
        """_platform_diff Summary

        Returns:
            dict: the dict contains a set, for every playlist, with the missing songs for that given playlist. Structure: 
                {
                    <playlist>: {
                        <platform>: {SongData}
                    }
                }
            dict: A dict containing the TOTAL songs for the playlist, combined over all platforms. Structure:
                {
                    <playlist>: {SongData}
                }
            
        """
        # if sync:
        #     # 1.1 Calculate platform differences
        #     missing, total = pm._platform_diff(lib, platform_data)
        # #     # 1.2 : Update playlists
        # #     pm.sync_playlists(lib, diff, total, sync_type)

        
        # # ────────────────────────────────────────────────────────
        # # Stage 2: Download songs with SoulSeek, only for the items returned
        # # ────────────────────────────────────────────────────────

        


        if dl == 'pipe':
            to_download = self.dbu.items_to_download(lib, songs=pulled_songs, dl_cooldown=7, output='Item')
        elif dl == 'all':
            to_download = self.dbu.items_to_download(lib, dl_cooldown=None, output='Item')
        elif dl == 'time':
            to_download = self.dbu.items_to_download(lib, dl_cooldown=7, output='Item')
        else:
            self._log.log("info", "Skipping SoulSeek download stage.")          

        self._log.log("info", f"Feeding {len(to_download)} items to SoulSeek for download...")


        async def do_soulseek_download():
            results = await self.slsk.download_songs(
                lib,
                items=to_download    # Only process these items from stage 1
            )
            return results

        # Run the async method in a synchronous pipeline
        results = asyncio.run(do_soulseek_download())
        successes = [r for r in results if r['status'] == 'success']
        self._log.log("info", f"SoulSeek download stage: {len(successes)} successful downloads out of {len(results)} attempts.")
           

        # # # ────────────────────────────────────────────────────────
        # # # Stage 2: Download songs with SoulSeek, only for the items returned
        # # # ────────────────────────────────────────────────────────
        # rkbx = RekordboxSyncPlugin()
        # updated_beets, updated_rekordbox, kapot_verkeerd_items = rkbx.sync_rekordbox(lib, fields=None, xml_path=None, remove_kapot=False)


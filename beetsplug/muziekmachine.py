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


# TO DO
# - change 'sync' from string argument to just a boolean flag (sync of --sync present else not)
# - add logging for sync platform
# - 


class MuziekMachine(BeetsPlugin):
    def __init__(self):
        super().__init__()
        self._log = CustomLogger("MuziekMachine", default_color="purple")

        # Add the CLI command
        self.pipeline_cmd = Subcommand(
            'mm-run',
            help='Run custom pipeline: pull platforms -> download songs'
        )
        # sync playlists
        self.pipeline_cmd.parser.add_option(
            '--sync', default=''
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
            '--dl', default='pipeline',
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

    def run_pipeline(self, lib, platform_str, playlist_str, dl, sync):
        """Runs the pipeline in stages, chaining results from each stage."""

        # ────────────────────────────────────────────────────────
        # Stage 0.0 : Pull platform data -> returns items
        # ────────────────────────────────────────────────────────
        pm = PlatformManager()

        # NEW PULL FUNCTION FOR SYNCING PLAYLISTS
        platform_data = pm.pull_data(lib, playlist_name=playlist_str)

        # ────────────────────────────────────────────────────────
        # Stage 1 : Sync playlists 
        # ────────────────────────────────────────────────────────
        if sync:
            # 1.1 Calculate platform differences
            diff, total = pm._platform_diff(lib, platform_data)
            # 1.2 : Update playlists
            pm.sync_playlists(lib, diff, total)
            # ────────────────────────────────────────────────────────



        return        








        new_items, updated_items = pm.pull_platform_songs(
            lib,
            platform_str=platform_str,
            playlist_name=playlist_str,
            playlist_type='mm',
            no_db=False
        )

        self._log.log("info", f" STAGE 1 COMPLETED: Pulled {len(new_items)} new items, {len(updated_items)} updated items from platforms: {platform_str}, plalylist: {playlist_str}.")

        # Optionally combine them if you want a single list:
        stage1_items = new_items + updated_items

        # # ────────────────────────────────────────────────────────
        # # Stage 2: Download songs with SoulSeek, only for the items returned
        # # ────────────────────────────────────────────────────────
        soulseek = SoulSeekPlugin()
        
        if dl != 'skip':
            if not dl:
                stage1_items = None

            self._log.log("info", f"Feeding {len(stage1_items)} items to SoulSeek for download...")
            async def do_soulseek_download():
                results = await soulseek.download_songs(
                    lib,
                    genres=None,          # or 'all', but we can override with "items" param
                    items=stage1_items    # Only process these items from stage 1
                )
                return results

            # Run the async method in a synchronous pipeline
            results = asyncio.run(do_soulseek_download())
            successes = [r for r in results if r['status'] == 'success']
            self._log.log("info", f"SoulSeek download stage: {len(successes)} successful downloads out of {len(results)} attempts.")
        else:
            self._log.log("info", "Skipping SoulSeek download stage.")

        # # ────────────────────────────────────────────────────────
        # # Stage 2: Download songs with SoulSeek, only for the items returned
        # # ────────────────────────────────────────────────────────
        rkbx = RekordboxSyncPlugin()
        updated_beets, updated_rekordbox, kapot_verkeerd_items = rkbx.sync_rekordbox(lib, fields=None, xml_path=None, remove_kapot=False)


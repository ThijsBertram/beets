from __future__ import annotations
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand
from beets import config

from beetsplug.muziekmachine.sources.beets.client import BeetsClient
from beetsplug.muziekmachine.sources.beets.adapter import BeetsAdapter
from beetsplug.muziekmachine.sources.beets.mapper import BeetsMapper

from beetsplug.muziekmachine.services.ingestion import pull_source


class BeetsBeetsPlugin(BeetsPlugin):
    """Registers a CLI command to pull Spotify data using the new client+adapter+mapper."""
    name = "mm_beets"

    def __init__(self):
        super().__init__()

        self.pull_command = Subcommand('beets-pull', help='Pull Spotify playlists and map to SongData')
        self.pull_command.parser.add_option('--playlist', dest='playlist', help='Playlist name or id to pull (optional)')
        self.pull_command.func = self._cmd_pull
    
    def commands(self):
        return [self.pull_command]

    def _make_client_adapter(self, lib):

        client = BeetsClient(lib=lib)
        adapter = BeetsAdapter(client=client, mapper=BeetsMapper())
        return client, adapter

    def _cmd_pull(self, lib, opts, args):
        self.pull(opts, lib)
        return

    def pull(self, opts, lib):
        client, adapter = self._make_client_adapter(lib)

        with client:
            count = 0
            for sd, ref in pull_source(client, adapter, playlist=opts.playlist):
                # For now, just log a summary; later you’ll pass these into Matching/Merging/Sync.
                self._log.info(f"[Beets] {sd.main_artist} — {sd.title} (id={sd.spotify_id})")
                count += 1
            self._log.info(f"Pulled {count} Beets tracks.")

        return
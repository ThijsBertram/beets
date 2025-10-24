from __future__ import annotations
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand
from beets import config

from beetsplug.muziekmachine.sources.spotify.client import SpotifyClient
from beetsplug.muziekmachine.sources.spotify.adapter import SpotifyAdapter
from beetsplug.muziekmachine.sources.spotify.mapper import SpotifyMapper
# from beetsplug.muziekmachine.services.ingestion import pull_source


class SpotifyBeetsPlugin(BeetsPlugin):
    """Registers a CLI command to pull Spotify data using the new client+adapter+mapper."""
    name = "mm_spotify"

    def __init__(self):
        super().__init__()

        cmd = Subcommand('mm-spotify-pull', help='Pull Spotify playlists and map to SongData')
        cmd.parser.add_option('--playlist', dest='playlist', help='Playlist name or id to pull (optional)')
        cmd.func = self._cmd_pull
        self.commands = [cmd]

        self.client, self.adapter = self._make_client_adapter()

    def _make_client_adapter(self):
        cfg = self.config

        print("HOI")
        print(cfg)
        client = SpotifyClient(
            client_id=self.config['client_id'].get(),
            client_secret=self.config['client_secret'].get(),
            redirect_uri=self.config['redirect_uri'].get(),
        )
        adapter = SpotifyAdapter(client=client, mapper=SpotifyMapper())
        return client, adapter

    def _cmd_pull(self, lib, opts, args):
        # with self.client:
            # count = 0
            # for sd, ref in pull_source(self.client, self.adapter, playlist=opts.playlist):
            #     # For now, just log a summary; later you’ll pass these into Matching/Merging/Sync.
            #     self._log.info(u"[Spotify] %s — %s (id=%s)", sd.main_artist or "", sd.title, ref.id)
            #     count += 1
            # self._log.info("Pulled %d Spotify tracks.", count)
            # print('hoi')

        print('hoi spotify')
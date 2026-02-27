from __future__ import annotations

import argparse

from beets.plugins import BeetsPlugin
from beets.ui import Subcommand
from beets import config

from beetsplug.muziekmachine.sources.beets.client import BeetsClient
from beetsplug.muziekmachine.sources.beets.adapter import BeetsAdapter
from beetsplug.muziekmachine.sources.beets.mapper import BeetsMapper

from beetsplug.muziekmachine.services.ingestion import pull_source
from beetsplug.muziekmachine.services.playlist_ingestion import iter_collection_stubs, iter_playlist_data
from beetsplug.muziekmachine.sources.beets.playlist_adapter import BeetsPlaylistAdapter

class BeetsBeetsPlugin(BeetsPlugin):
    """Registers a CLI command to pull Spotify data using the new client+adapter+mapper."""
    name = "mm_beets"

    def __init__(self):
        super().__init__()

        self.pull_songs = Subcommand('beets-pull', help='Pull Spotify playlists and map to SongData')
        self.pull_songs.parser.add_option('--playlist', dest='playlist', help='Playlist name or id to pull (optional)')
        self.pull_songs.func = self._cmd_pull_songs

        self.pull_playlists = Subcommand('beets-pull-playlist')
        self.pull_playlists.parser.add_option('--playlist', dest='playlist')
        self.pull_playlists.func = self._cmd_pull_playlists


    def commands(self):
        return [self.pull_songs, self.pull_playlists]

    def _make_client_adapter(self, lib):

        client = BeetsClient(lib=lib)
        adapter = BeetsAdapter(client=client, mapper=BeetsMapper())
        return client, adapter

    def _cmd_pull_songs(self, lib, opts, args):
        if opts.playlist:
            playlists = [pl.strip() for pl in opts.playlist.split(',')]
        else:
            client, adapter = self._make_client_adapter()

            with client:
                playlists = client.iter_collections()
                playlists = [pl.name for pl in playlists]
                
        self._pull_songs(playlists, lib)
        return

    def _pull_songs(self, playlists, lib):
        
        client, adapter = self._make_client_adapter(lib)

        with client:
            count = 0
            for sd, ref in pull_source(client, adapter, playlist=playlists):
                # For now, just log a summary; later you’ll pass these into Matching/Merging/Sync.
                self._log.info(f"[Beets] {sd.main_artist} — {sd.title} (id={sd.spotify_id})")
                count += 1
            self._log.info(f"Pulled {count} Beets tracks.")

        return
    
    def _cmd_pull_playlists(self, lib, opts, args):

        if opts.playlist:
            playlists = [pl.strip() for pl in opts.playlist.split(',')]
        else:
            client, adapter = self._make_client_adapter(lib)

            with client:
                playlists = client.iter_collections()
                playlists = [pl.name for pl in playlists]

        self._pull_playlists(playlists, lib)        
        return
    
    def _pull_playlists(self, playlists, lib):
        client, adapter = self._make_client_adapter(lib)

        playlist_adapter = BeetsPlaylistAdapter(client)
        
        with client:
            count = 0 
            for pd in iter_playlist_data(client, playlist_adapter, selectors=playlists, include_items=False):
                self._log.info(f"[Beets] Playlist data pulled for playlist {pd.name}")
                count += 1 
        self._log.info(f"Pulled {count} Beets playlists.")
        return
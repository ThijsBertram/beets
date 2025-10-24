from beets.plugins import BeetsPlugin
from beets.ui import Subcommand
from beets import config

from beetsplug.muziekmachine.sources.spotify.adapter import SpotifyAdapter
from beetsplug.muziekmachine.sources.spotify.plugin import SpotifyBeetsPlugin

class MuziekMachine(BeetsPlugin):
    def __init__(self):
        super().__init__()

        # ===================================
        # COMMANDS
        # ===================================
        pull_spotify = Subcommand('pull-spotify', help='Pull Spotify playlists and map to SongData')
        pull_spotify.parser.add_option('--playlist', dest='playlist', help='Playlist name or id to pull (optional)')
        pull_spotify.func = self._cmd_pull_spotify
        self.commands = [pull_spotify]

        
        # ===================================
        # ADAPTERS
        # ===================================
        # self.spotify = SpotifyAdapter()
        self.spotify = SpotifyBeetsPlugin()



    def _cmd_pull_spotify(self, lib, opts, args):
        print('hoi')
        return
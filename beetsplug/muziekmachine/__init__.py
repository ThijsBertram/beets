from beets.plugins import BeetsPlugin
from beets.ui import Subcommand
from beets import config

# from beetsplug.muziekmachine.sources.spotify.adapter import SpotifyAdapter
# from beetsplug.muziekmachine.sources.spotify.mm_spotify import SpotifyBeetsPlugin
from beetsplug.muziekmachine.sources.spotify.mm_spotify import SpotifyBeetsPlugin
from beetsplug.muziekmachine.sources.beets.mm_beets import BeetsBeetsPlugin
from beetsplug.muziekmachine.sources.youtube.mm_youtube import YoutubeBeetsPlugin

# TODO
#   - PARSING FROM SONG STRINGS
#   - YOUTUBE PULL SONGS
#       * implmement parsing of string titles
#       * FIX THIS IN MAPPER
#   - YOUTUBE PULL PLAYLISTS
#       * 
#   - REKORDBOX PULL SONGS
#   - REKORDBOX PULL PLAYLISTS
#   - FILESYSTEM PULL SONGS
#   - FILESYSTEM PULL PLAYLISTS
#   - MATCHING
#   - DIFFING 
#   - SYNCING
#   - DOWNLOADING

# TODO: - CLIENT ROBUSTNESS

# TODO: - PLAYLIST FUNCTIONALITY
#           PREREQS
                # - add is_public column to playlist tablei n beets
                # - create way to add raw_items to playlistData when initializing
                # - update _make_client_adapter() to also return playlist_adapter


# TODO: -  CLIENT ROBUSTNESS
#       - RATE LIMITING & THROTTLING
#           - use raw where possible?
#           - caching?
#           - limiting with availiable requests?
#       - CREDENTIAL REFRESHING
#           - implement generic way to refresh creds

# TODO: - DIFFING / MATCHING / MERGING
#           - change render_current fields (put in config?)
#           - change capabilities for every source (put in config?)




class MuziekMachine(BeetsPlugin):
    
    def __init__(self):
        super().__init__()

        # ===================================
        # COMMANDS
        # ===================================
        self.pull_spotify = Subcommand('mm-pull', help='Pull Spotify playlists and map to SongData')
        self.pull_spotify.parser.add_option(
            '--platform', 
            dest='platform',
            default='all',
            choices=['all', 'spotify', 'youtube'],
            help='Source to be pulled (all, spotify, youtube, beets, rekordbox, filesystem)')
        # self.pull_spotify.parser.add_option('--playlist', dest='playlist', help='Playlist name or id to pull (optional)')
        self.pull_spotify.func = self._cmd_pull_spotify

        # ===================================
        # PLUGINS
        # ===================================
        self.spotify = SpotifyBeetsPlugin()
        self.beets = BeetsBeetsPlugin()
        self.youtube = YoutubeBeetsPlugin()

        self.sources = {
            'spotify': self.spotify,
            'all': [self.spotify]
        }




    def commands(self):
        return [self.pull_spotify]


    def _cmd_pull_spotify(self, lib, opts, args):
        platform = opts.platform

        # print(platform)
        # quit()

        if platform not in self.sources.keys():
            raise 'not a valid platform'
        
        print(platform)
        quit()
        

        self.spotify.pull(opts)
        return
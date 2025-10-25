from beets.plugins import BeetsPlugin
from beets.ui import Subcommand
from beets import config

# from beetsplug.muziekmachine.sources.spotify.adapter import SpotifyAdapter
# from beetsplug.muziekmachine.sources.spotify.mm_spotify import SpotifyBeetsPlugin
from beetsplug.muziekmachine.sources.spotify.mm_spotify import SpotifyBeetsPlugin
from beetsplug.muziekmachine.sources.beets.mm_beets import BeetsBeetsPlugin


#TODO: - ask chappie about adapters and their usage (rendering, capabilities)
#TODO: - ask chappie about playlist_adapter. Why not fold it into adapter class (like with mapper)
#todo                   - or at least in same adapter.py file?

#TODO: - CHANGE RENDER_CURRENT IN ADAPTERS TO ACTUALLY RENDER RELEVANT STUFF (THAT IS IN SONGDATA)
#TODO: - GET DEFINITION OF CAPABILITIES IN ADAPTERS FROM CONFIG (INSTEAD OF HARDCODED) 
#TODO: - REFACTOR:
#TODO:      - BEETS 
#TODO:      - SPOTIFY (PLAYLISTS)
#TODO:      - YOUTUBE
#TODO:      - REKORDBOX




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
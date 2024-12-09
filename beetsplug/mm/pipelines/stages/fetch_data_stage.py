from beetsplug.mm.platforms.SpotifyPlugin import spotify_plugin
from beetsplug.mm.platforms.YoutubePlugin import youtube_plugin
from beetsplug.mm.platforms.PlatformManager import PlatformManager


def FetchPlatformData():
        
        pm = PlatformManager()

        

        pm.pull_platform()
        

        

        all_info = spotify_info
        
        return all_info
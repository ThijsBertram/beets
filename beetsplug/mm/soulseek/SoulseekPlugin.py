# Beets
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand
from beets import config
from beetsplug.ssp import SongStringParser


# Varia'
import os
import shutil
import logging
import datetime

import threading
from queue import Queue
from datetime import datetime

from slskd_api import SlskdClient
from .download import Downloader
from .search import Searcher
# from .models import SoulseekModel
# from dotenv import load_dotenv




class SoulSeekPlugin(BeetsPlugin):
    
    def __init__(self):

        super().__init__()
        self._log = logging.getLogger('beets.soulseek')
        self.ssp = SongStringParser()

        # CONFIG
        self.api_key = str(config['mm']['SoulseekPlugin']['api_key'])
        self.max_threads = int(str(config['mm']['SoulseekPlugin']['max_threads']))
        self.library_dir = str(config['directory'])
        self.slsk_dl_dir = str(config['mm']['SoulseekPlugin']['slsk_dl_dir'])
        self.host = str(config['mm']['SoulseekPlugin']['host'])
        self.dl_timeout = int(str(config['mm']['SoulseekPlugin']['dl_timeout']))

        # Objects
        self.slsk = SlskdClient(api_key=self.api_key, host=self.host)
        self.searcher = Searcher(self.slsk, log=self._log)
        self.downloader = Downloader(self.slsk, log=self._log, timeout=self.dl_timeout)
        self.download_queue = Queue()
        self.threads = list()
        self.stop_event = threading.Event()

        # Central command definitions
        self.dl_slsk = Subcommand('dl-slsk')
        self.dl_slsk.parser.add_option('--n-tries', dest='tries', default='3')
        self.dl_slsk.func = self.dl_slsk

        # Results
        self.succeeded = list()
        self.failed = list()

    def commands(self):
        return [self.dl_slsk]
    
    def dl_slsk(self, lib, opts, args):
        return
    

    def get_songs(self):
        """Wrapper to start threads and ensure they stop when the queue is empty."""
        # start threads
        self.stop_event.clear()
        for _ in range(self.max_threads):
            t = threading.Thread(target=self.handle_download)
            t.daemon = True
            t.start()
            self.threads.append(t)
        # Wait for all tasks to be completed
        self.download_queue.join()          
        # Stops the download threads
        self.stop_event.set()               
        for _ in range(len(self.threads)):
            self.download_queue.put(None)
        for t in self.threads:
            t.join()
        self.threads.clear()


    def handle_download(self):
        """Handles the download tasks from the queue."""
        while not self.stop_event.is_set():
            try:
                item = self.download_queue.get(timeout=1)  # 1 second timeout
            except:
                continue  # If queue is empty, continue checking

            if item is None:
                break

            try:
                song = {
                    "main_artist": item['main_artist'],
                    "song_title": item['title'],
                    "feat_artist": item['feat_artist'],
                    "remixer": item['remixer'],
                    "remix_type": item['remix_type']
                }
                # Search song
                results, search_attempted_at = self.searcher.perform_search(song)
                search_data = {
                    'song_id': item['id'],
                    'search_attempted_at': search_attempted_at,
                    'download_attempted_at': datetime.now()  # Default in case of no matches or results
                }
                # Match search results
                if results:
                    matches = self.searcher.match_results(results, song)
                    search_data.update({
                        'results_found': str(len(results)),
                        'matches_found': str(len(matches))
                    })
                    # Download match
                    if matches:
                        for match in matches:
                            username, match_data = match
                            file, download_attempted_at = self.downloader.download(match=match_data,
                                                                                  username=username)

                            file_path = file['filename']
                            folder = file_path.split('\\')[-2]
                            f = file_path.split('\\')[-1]
                            extension = f.split('.')[-1]
                            song['extension'] = extension

                            # MOVE THE FILE
                            if file_path:
                                # SOURCE
                                src = os.path.join(self.slsk_dl_dir, folder, f)

                                artists = item['artists'][0].split(",")
                                # DESTINATION
                                fname_artist = self.ssp.concat_artists(artists)
                                if item['feat_artist']:
                                    fname_artist += f' feat. {item.feat_artist}'
                                fname_artist_title = fname_artist + ' - ' + item['title']
                                if item['remixer']:
                                    fname_artist_title += f' ({item.remixer} {item.remix_type})'

                                fname = fname_artist_title + f'.{extension}'
                                dst = os.path.join(self.library_dir, fname)
                                rmv = os.path.join(self.slsk_dl_dir, folder)
                                # MOVE
                                self.downloader.move_file(src, dst)
                                # DELETE FOLDER
                                shutil.rmtree(rmv)


                                search_data.update({
                                    'search_query': match[1]['filename'],
                                    'file': os.path.basename(file_path),
                                    'folder': folder,
                                    'download_status': 'success',
                                    'download_attempted_at': download_attempted_at
                                })

                                self.succeeded.append((item, fname))
                                break
                        else:
                            search_data.update({
                                'search_query': 'N/A',
                                'file': 'N/A',
                                'folder': 'N/A',
                                'download_status': 'no matches'
                            })
                    else:
                        search_data.update({
                            'search_query': 'N/A',
                            'file': 'N/A',
                            'folder': 'N/A',
                            'download_status': 'no matches'
                        })
                else:
                    search_data.update({
                        'results_found': '0',
                        'matches_found': '0',
                        'search_query': 'N/A',
                        'file': 'N/A',
                        'folder': 'N/A',
                        'download_status': 'no results'
                    })

                # TO DO DATABASE STUFFS
                # SoulseekModel.create(**search_data)

            except Exception as e:
                self._log.error(f"Error in handle_downloads: {e}")
            finally:
                self.download_queue.task_done()

        self._log.debug("Thread exiting...")


    def add_to_queue(self, item):
        """Adds a list of songs to the download queue."""

        def queue(song):
            # if isinstance(song, dict):
            self.download_queue.put(song)
            # else:
                # self._log.error(f"Error in adding song to queue, wrong type: {type(song)}")
            # return

        if isinstance(item, list):
            for i in item:
                queue(i)
       
        return
    

    def clean_slsk(self):

        # slsk - downloads
        self.slsk.transfers.remove_completed_downloads()

        # slsk - searches
        searches = self.slsk.searches.get_all()
        for s in searches:
            self.slsk.searches.delete(s['id'])

        # slsk - dl directory
        
        return
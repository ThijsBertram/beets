# Beets
from beets.plugins import BeetsPlugin
from beets.library import Library
from beets.ui import Subcommand
from beets import config
from beetsplug.ssp import SongStringParser


# Varia'
import os
import glob
import time
import shutil
import logging
import datetime


import pathlib
import threading
from queue import Queue, Empty
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
        self.dls = dict()

    def commands(self):
        return [self.dl_slsk]
    
    def get_songs(self):
        """Wrapper to start threads and ensure they stop when the queue is empty."""
        
        self.clean_slsk()

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

        """Wrapper to start threads and ensure they stop when the queue is empty."""

        return
            
    def get_item(self):
        item = self.download_queue.get(timeout=1)
        item_id = item.id
        self.dls[item.id] = dict()
        self.dls[item.id]['item'] = item
        self.dls[item.id]['status'] = 'started'
        self._log.info(f'\t\t THREAD - {item.id} - STARTED')
        return item, item_id
    
    def get_results(self, item, item_id):
        results, search_attempted_at = self.searcher.perform_search(item)
        if not results:
            self.dls[item_id]['status'] = 'no_results'
            # self.download_queue.task_done()
            return False
        else:
            self.dls[item_id]['status'] = 'results'
            n_results = len(results)
            self.dls[item.id]['n_results'] = n_results
            return results
        
    def get_matches(self, results, item):
        matches = self.searcher.match_results(results, item)
        if not matches:
            self.dls[item.id]['status'] = 'no_matches'
            # self.download_queue.task_done()
            return False
        n_matches = len(matches)
        self.dls[item.id]['n_mathces'] = n_matches

        return matches
    
    def get_download(self, match, item):
        # match data
        username, match_data = match
        # download file
        file, download_attempted_at = self.downloader.download(match=match_data,
                                                                username=username)
        # check 
        if not file:
            self.dls[item.id]['status'] = 'dl_failed'
            return False
        return file

    def move_dl(self, file, item):
        try:
            # 5. MOVE FILE
            # 5.0 process filename stuff - prepare moving 
            fpath = file['filename']
            fname = fpath.split('\\')[-1]
            dl_fstring = glob.glob(f'{self.slsk_dl_dir}/**/*{fname}')  

            # ugly piece of code - fix this 
            try:
                dl_fstring = dl_fstring[0]
            except IndexError:
                return False
            dl_abspath = pathlib.Path(dl_fstring).resolve()
            extension = fname.split('.')[-1]
            # 5.5 move file
            # MOVE FILE
            if dl_abspath:
                # CONSTRUCT PATHS
                src = dl_abspath
                dst = self.ssp.string_from_item(item, ext=extension, path=self.library_dir)
                rmv = dl_abspath.parent.absolute()


                if os.path.exists(dst):
                    # self._log.info(f"Destination file {dest} already exists. Deleting the source file {src}.")
                    os.remove(src)
                else:
                    os.rename(src, dst)
                                
                # delete placeholder dir
                shutil.rmtree(rmv)

                self.dls[item.id]['path'] = dst
                self.dls[item.id]['status'] = 'success'
                return dst
        except:
            self.dls[item.id]['status'] = 'move_failed'
            return False
        
    def handle_download(self):
        """Handles the download tasks from the queue."""
        # MAIN LOOP
        while not self.stop_event.is_set():
            results = None
            n_results = None
            matches = None
            n_matches = None
            item = None
            item_id = None
            title = None
            file = None
            
            try:
                # 1. ITEM - taken from queue
                item, item_id = self.get_item()
                if not item:
                    continue
                # 2. RESULTS for slsk item search
                results = self.get_results(item, item_id)
                if not results:
                    continue
                # 3. MATCH - results agains the item
                matches = self.get_matches(results, item)
                if not matches:
                    continue
                # 4. DOWNLOAD - best matches
                for match in matches[:1]:                   # [:3] REPLACE WITH CONFIG VALUE
                    file = self.get_download(match, item)
                    if not file:
                        continue

                # 5. MOVE - downloaded files
                    path = self.move_dl(file, item)
                    if not path:
                        continue          
     
                # 6. ADD PATH - downloaded files
                    item.path = path
                    item.store()

                # -
            except Exception as e:
                if item:
                    self._log.error(f"\t\t{item_id} - {self.dls[item.id]['title']} - ERROR - {e}")
                continue
            # used for joining queue ( can be prettier )
            except AttributeError:
                pass
            finally:
                # UGLY UGLY UGLY
                if not item:
                    continue

                status = self.dls[item.id]['status']        
                title = self.dls[item.id]['title']
                if status == 'no_results':
                    self._log.info(f'\t\t{item_id} - {title} - X RESOLVED X - no results')
                elif status == 'no_matches':
                    self._log.info(f'\t\t{item_id} - {title} - X RESOLVED X - no matches')
                elif status == 'download_failed':
                    self._log.info(f'\t\t{item_id} - {title} - X RESOLVED X - dl failed')
                elif status == 'started':
                    self._log.info(f'\t\t{item_id} - {title} - X RESOLVED X - not finished')
                else:
                    self._log.info(f'\t\t{item_id} - {title} - ! RESOLVED ! - download complete')
                self.download_queue.task_done()


        return

    def add_to_queue(self, item):
        """Adds a list of songs to the download queue."""

        def queue(song):
            self.download_queue.put(song)

        if isinstance(item, list):
            self._log.debug(f'ALL THREADS - {[i.id for i in item]} - {len([item])} TOTAL')
            for i in item:
                queue(i)
                time.sleep(0.1)
       
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
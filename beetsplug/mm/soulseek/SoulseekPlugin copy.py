# Beets
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand
from beets import config
from beetsplug.ssp import SongStringParser


# Varia'
import os
import glob
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

        # # Wait for all tasks to be completed
        # self.download_queue.join()
        # print("JOINED")          
        # # Stops the download threads
        # self.stop_event.set()               
        # for _ in range(len(self.threads)):
        #     self.download_queue.put(None)
        # for t in self.threads:
        #     t.join()
        """Wrapper to start threads and ensure they stop when the queue is empty."""

        # Wait for the queue to be processed
        self.download_queue.join()

        # Send a stop signal to the threads
        for _ in range(self.max_threads):
            self.download_queue.put(None)  # This will signal threads to stop

        self._log.info("All downloads completed and threads exited.")
        self.threads.clear()


    def handle_download(self):
        """Handles the download tasks from the queue."""

        while not self.stop_event.is_set():
            # print()
            # print()
            # print("NEW THREAD")
            # print("=========================================================")
            try:
                item = self.download_queue.get(timeout=1)  # 1 second timeout
                print(f'THREAD - {item.id} - STARTED')
                if item is None:
                    print("QUEUE EMPTY")
                    break

                # print(item)

                self.dls[item.id] = dict()
                self.dls[item.id]['item'] = item
                
                # SEARCH
                results, search_attempted_at = self.searcher.perform_search(item)

                # print('~~download_queue')
                # print(self.download_queue.unfinished_tasks)
                # print(len(self.download_queue.queue))

                if not results:
                    self.dls[item.id]['status'] = 'no_results'
                    break
                
                # print('hoi')
                # MATCH
                matches = self.searcher.match_results(results, item)

                # RESULTS DICT
                n_results = len(results)
                n_matches = len(matches)
                self.dls[item.id]['n_results'] = n_results
                self.dls[item.id]['n_mathces'] = n_matches

                if not matches:
                    # print("NO MATCHES")
                    self.dls[item.id]['status'] = 'no_matches'
                    break

                # Download match
                for match in matches:            
                    username, match_data = match
                    
                    file, download_attempted_at = self.downloader.download(match=match_data,
                                                                            username=username)
                    if not file:
                        self.dls[item.id]['status'] = 'dl_timeout'
                        break

                    fpath = file['filename']
                    fname = fpath.split('\\')[-1]

                    # print("PATHS")
                    # print(fpath)
                    # print(fname)

                    dl_fstring = glob.glob(f'{self.slsk_dl_dir}/**/*{fname}')
                    # print("MATCHED DOWNLOADED FILENAMES HERE")
                    # print(dl_fstring)
                    try:
                        dl_fstring = dl_fstring[0]
                    except IndexError:
                        # print("~~~~~~~~~~~~ BIG ERROR: ~~~~~~~~~~~~~~")
                        break
                    dl_abspath = pathlib.Path(dl_fstring).resolve()
                    extension = fname.split('.')[-1]

                    # MOVE FILE
                    if dl_abspath:
                        # CONSTRUCT PATHS
                        src = dl_abspath
                        # print("MAKING STRING FROM ITEM")
                        dst = self.ssp.string_from_item(item, ext=extension, path=self.library_dir)
                        # print("MADE STRING:")
                        # print(dst)  
                        rmv = dl_abspath.parent.absolute()
                        # print(f"SRC PATH IS: {src}")
                        # print("SRC IS FILE : ", os.path.isfile(src))
                        # MOVE
                        self.downloader.move_file(src, dst)
                        # DELETE FOLDER
                        # print(f"REMOVE FOLDER: {rmv}")
                        # print(f"FOLDER IS DIR: {os.path.isdir(rmv)}")
                        shutil.rmtree(rmv)

                        self.dls[item.id]['status'] = 'success'
                        break                
            
            except Empty:
                print("QUEUE EMPTY")
                break  # If queue is empty, continue checking

            except Exception as e:
                self._log.error(f'Error in handle_downlaods: {e}\nFor item {item}')
                break
            
            finally:
                self.download_queue.task_done()
                self._log.debug(f'TRHEAD - {item.id} - RESOLVED')

        # print("GEBROKEN")
        # self._log.debug(F"THREAD - {item.id} - RESOLVED")
        # self.download_queue.task_done()
        return

    def add_to_queue(self, item):
        """Adds a list of songs to the download queue."""

        def queue(song):
            # if isinstance(song, dict):
            self.download_queue.put(song)
            # else:
                # self._log.error(f"Error in adding song to queue, wrong type: {type(song)}")
            # return

        if isinstance(item, list):
            print(f'ALL THREADS - {[i.id for i in item]} - {len([item])} TOTAL')
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
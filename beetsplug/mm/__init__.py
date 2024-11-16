from beets.plugins import BeetsPlugin
from beetsplug.mm.platforms.PlatformManager import PlatformManager
from beetsplug.mm.soulseek.SoulseekPlugin import SoulSeekPlugin
from beetsplug.ssp import SongStringParser
from .cli.pipe_commands import pull_pf, sync_pf, get_items, dl_slsk, analyze, pipe

import os
import logging
from beets.ui import Subcommand
from collections import namedtuple





class MuziekMachine(BeetsPlugin):
    
    def __init__(self):

        super().__init__()
        self._log = logging.getLogger('beets.MuziekMachine')

        # OBJECTS
        self.pm = PlatformManager()
        self.slsk = SoulSeekPlugin()

        # COMMANDS
        self.pull_pf = pull_pf
        self.sync_pf = sync_pf
        self.get_items = get_items
        self.dl_slsk = dl_slsk
        self.analyze = analyze
        self.pipe = pipe
        self.pipe.func = self.start_pipeline

    def commands(self):
        return [self.pull_pf, self.sync_pf, self.get_items, self.dl_slsk, self.analyze, self.pipe]
    
    def start_pipeline(self, lib, args, opts):
        
        #stages
        n_stages= 0
        current_stage = 0
        # logging
        # self._log.info('PIPELINE STARTED WITH {} STAGES')

        items = list()
        # STAGE 1: pull platforms
        if args.pull_pf:
            
            self._log.info(f' ~~~ STAGE {current_stage}: PULL PLATFORM ~~~~ STARTED ~~~')

            # create opts and args 
            Options = namedtuple('Options', ['platform', 'playlist_type', 'db', 'playlist_name'])
            opts = Options(platform=args.pull_pf,
                           playlist_type=args.pl_type,
                           db=args.db,
                           playlist_name=args.pl_name
                           )
            
            items += self.pm.pull_platform(lib, opts, [])
            
            current_stage += 1


        

        # STAGE 2: pull database
        if args.get_items:

            self._log.info(f' ~~~ STAGE {current_stage}: PULL DATABASE ~~~~ STARTED ~~~')


            if args.get_items == 'all':
                query_results = list(lib.items())
                items += query_results
            elif args.get_items == 'missing_files':
                query_results = list(lib.items())
                missing_files = [item for item in query_results if item.get('path') is None]
                

                # TEMP
                missing_files = [item for item in missing_files if item.get('genre') == 'Club']

                items += missing_files

            else:
                query_results = list(lib.items(str(args.get_items)))
                items += query_results


            current_stage +=1 
    

        # STAGE 3: sync platforms

        # STAGE 4: dl_slsk
        if args.dl_slsk:

            self._log.info(f' ~~~ STAGE {current_stage}: DL SOULSEEK ~~~~ STARTED ~~~')
       

            skipped = list()
            # pre download stage: check if file already exists
            for i in items:
                # skip items that already have an existing file as a path
                if i.path:
                    if os.path.isfile(i.path):
                        skipped.append(i)
                        continue
            
            print('\t ADDING ITEMS TO DL QUEUE')
            self.slsk.add_to_queue(items)
            self.slsk.get_songs()
            
            # ADD SUCCESFUL DLS TO LIBRARY
            success = [i for i in self.slsk.dls.values() if i['status'] == 'success']
            no_results = [i for i in self.slsk.dls.values() if i['status'] == 'no_results']
            no_matches = [i for i in self.slsk.dls.values() if i['status'] == 'no_matches']
            dl_failed = [i for i in self.slsk.dls.values() if i['status'] == 'dl_failed']
            move_failed = [i for i in self.slsk.dls.values() if i['status'] == 'move_failed']
            not_finished = [i for i in self.slsk.dls.values() if i['status'] == 'not_finished']

            self._log.info("\t ~~~ DOWNLOAD RESULTS ~~~")
            self._log.info(f"\t {len(success)} - SUCCESS")
            self._log.info(f"\t {len(no_results)} - NO RESULTS")
            self._log.info(f"\t {len(no_matches)} - NO MATCHES")
            self._log.info(f"\t {len(dl_failed)} - DOWNLOAD FAILED")
            self._log.info(f"\t {len(move_failed)} - MOVING FAILED")
            self._log.info(f"\t {len(not_finished)} - NOT FINISHED")
            self._log.info(f"\t {len(success)} / {len(self.slsk.dls.values())} SUCCESSFUL")
            self._log.info('\t ~~~~~~~~~~~~~~~~~~~~~~~~')

            # for i in success:
            #     item = i['item']
            #     path = i['path']

            #     item.path = path
            #     item.store()

        return
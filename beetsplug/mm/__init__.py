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
        self._log.info('PIPELINE STARTED WITH {} STAGES')

        items = list()
        # STAGE 1: pull platforms
        if args.pull_pf:


            self._log.info(f'    > STAGE {current_stage}')
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
            self._log.info(f'\t> STAGE {current_stage}')

            if args.get_items == 'all':
                query_results = list(lib.items())
                items += query_results
            elif args.get_items == 'missing_files':
                query_results = list(lib.items())
                missing_files = [item for item in query_results if item.get('path') is None]
                items += missing_files
            else:
                query_results = list(lib.items(str(args.get_items)))
                items += query_results

            current_stage +=1 
    

        # STAGE 3: sync platforms

        # STAGE 4: dl_slsk
        if args.dl_slsk:

            skipped = list()
            # pre download stage: check if file already exists
            for i in items:
                # skip items that already have an existing file as a path
                if i.path:
                    if os.path.isfile(i.path):
                        skipped.append(i)
                        continue
            
            print('ADDING ITEMS TO DL QUEUE')
            self.slsk.add_to_queue(items)
            self.slsk.get_songs()
            
            # add new paths to items
            dl_succeeded = self.slsk.succeeded
            
            for item, path in dl_succeeded:
                item.path = path
                item.store()

            # clean slsk
            self.slsk.clean_slsk()

            self._log.info(f"DOWNLOADING FINISHED: {len(dl_succeeded)}/{len(items)} files downloaded - {len(skipped)} files skipped")        
        return
from beets.plugins import BeetsPlugin
from beetsplug.mm.platforms.PlatformManager import PlatformManager
from .cli.pipe_commands import pull_pf, sync_pf, get_items, dl_slsk, analyze, pipe

import logging
from beets.ui import Subcommand
from collections import namedtuple



class MuziekMachine(BeetsPlugin):
    
    def __init__(self):

        super().__init__()
        self._log = logging.getLogger('beets.MuziekMachine')

        # OBJECTS
        self.pm = PlatformManager()

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
            self._log.info(f'   > STAGE {current_stage}')
            items += list(lib.items(args.get_items))
            current_stage +=1 

        if args.dl_slsk:
            pass

        return
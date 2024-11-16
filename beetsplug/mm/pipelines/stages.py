from collections import namedtuple

class PullPF:
    def __init__(self, lib, platform_manager):

        self.lib = lib
        self.pm = platform_manager()

        self.name = 'Pull Platform'
        self.stage_id = 'pull_pf'
        self.command = '--pull-pf'

        return

    def construct_arts(self, args):
        Options = namedtuple('Options', ['platform', 'playlist_type', 'db', 'playlist_name'])
        opts = Options(platform=args.pull_pf,
                        playlist_type=args.pl_type,
                        db=args.db,
                        playlist_name=args.pl_name
                        )
        return

    
    def run(self, args):
        



        return


    def log_results(self):
        return

    def log_results(self):
        return
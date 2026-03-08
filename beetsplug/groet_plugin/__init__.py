from beets.plugins import BeetsPlugin
from beets.ui import Subcommand


class GroetPlugin(BeetsPlugin):
    name = "groet_plugin"
    def __init__(self):
        super().__init__()

        # Define the CLI subcommand
        self.pull_command = Subcommand('groetjes')

        # The CLI entrypoint is a thin wrapper around our core method
        self.pull_command.func = self.begroeting

    def commands(self):
        return [self.pull_command]

    # ──────────────────────────────────────────────────────────────────────────
    # CLI ENTRYPOINT (Thin Wrapper)
    # ──────────────────────────────────────────────────────────────────────────
    def begroeting(self, lib, opts, args):
        """
        CLI entrypoint for `beet pull` command.

        - Extracts the CLI options from `opts`
        - Calls the main `pull_platform_songs` method
        """
        print('hoi')


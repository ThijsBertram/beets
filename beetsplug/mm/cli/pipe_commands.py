from beets.ui import Subcommand

# PULL PLATFORM DATA
pull_pf = Subcommand('pull_pf')
pull_pf.parser.add_option('--pf', dest='platform', choices=['all', 'spotify', 'youtube', 'a'], help='Specify the music platform (spotify, youtube)')
pull_pf.parser.add_option('--type', dest='playlist_type', choices=['pl', 'mm'], default='mm', help="Process 'pl' playlists or regular genre/subgenre playlists")
pull_pf.parser.add_option('--db', action='store_true', help='Add retrieved info to the database')
pull_pf.parser.add_option('--g', action='store_true', help='hallo')
pull_pf.parser.add_option('--pl', dest='playlist_name', help='Name of the playlist to retrieve')

# SYNC PLAYLISTS
sync_pf = Subcommand('sync_pf')
sync_pf.parser.add_option('--p', dest='platform', choices=['all', 'youtube', 'spotify'])

# GET ITEMS
get_items = Subcommand('get_items')
get_items.parser.add_option('--q', dest='query')
get_items.parser.add_option('--path-null', action='store_true')


# DOWNLOAD MISSING SONGS
dl_slsk = Subcommand('dl_slsk')
# dl_slsk.parser.add_option('')

# ANALYZE SONGS
analyze = Subcommand('analyze')
analyze.parser.add_option('--bpm', action='store_true')
analyze.parser.add_option('--key', action='store_true')

pipe = Subcommand('pipe')
pipe.parser.add_option('--pull-pf', dest='pull_pf', choices=['', 'all', 'youtube', 'spotify'], help='Pull information from platforms')
pipe.parser.add_option('--pull-db', dest='get_items', help='Pull information from database')
pipe.parser.add_option('--dl-slsk', action='store_true', help='Download missing songs using Soulseek slskd api')
pipe.parser.add_option('--analyze', action='store_true')
pipe.parser.add_option('--type', dest='pl_type', choices=['all', 'mm', 'pl'], default='mm')
pipe.parser.add_option('--pl-name', dest='pl_name')
pipe.parser.add_option('--db', action='store_true', default=True)

setlist = Subcommand(
    name='setlist',
    help='Create a setlist by querying the library or using a schema.',
)
setlist.parser.add_option(
    '-p', '--path',
    dest='setlist_path',
    help='Path to create the setlist (overridSes config).',
)
setlist.parser.add_option(
    '-f', '--format',
    dest='path_format',
    help='Path format for organizing the setlist (overrides config).',
)
setlist.parser.add_option(
    '-n', '--name',
    dest='setlist_name',
    help='Name of the setlist.',
)
setlist.parser.add_option(
    '--genre',
    dest='genre',
    help='Comma-separated list of genres to include in the setlist.',
)
setlist.parser.add_option(
    '--subgenre',
    dest='subgenre',
    help='Comma-separated list of subgenres to include in the setlist.',
)
setlist.parser.add_option(
    '--min_bpm',
    dest='min_bpm',
    help='Minimum BPM for the setlist.',
)
setlist.parser.add_option(
    '--max_bpm',
    dest='max_bpm',
    help='Maximum BPM for the setlist.',
)
setlist.parser.add_option(
    '--exclude_artist',
    dest='exclude_artist',
    help='Comma-separated list of artists to exclude from the setlist.',
)
setlist.parser.add_option(
    '--active',
    dest='active',
    help='Minimum active value for the setlist.',
)
setlist.parser.add_option(
    '--rating',
    dest='rating',
    help='Minimum rating for the setlist.',
)
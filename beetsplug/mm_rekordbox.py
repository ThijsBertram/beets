# import os
# import time
# import shutil
# import xml.etree.ElementTree as ET
# import logging
# import re
# from urllib.parse import unquote

# from beetsplug.custom_logger import CustomLogger
# from beets.plugins import BeetsPlugin
# from beets.ui import Subcommand
# from beets import config

# # -----------------------------------------------------------
# # Color and Rating Mapping
# # -----------------------------------------------------------

# COLOUR_MAP = {
#     '0x660099': 'RAVE',
#     '0xFF007F': 'EZPARTY',
#     '0x00FF00': 'LOUNGE',
#     '0x0000FF': 'LOOM / TRIPPY',
#     '0x25FDE9': 'COOLDOWN',
#     '0xFFA500': 'Orange',
#     '0xFF0000': 'BEUKEN',
#     '0xFFFF00': 'NODJ'
# }

# RATING_RB_TO_FLOAT = {
#     '0': 0.0,
#     '51': 1.0,
#     '102': 2.0,
#     '153': 3.0,
#     '204': 4.0,
#     '255': 5.0
# }

# def rating_float_to_rb(rating_float):
#     """Clamp rating_float to [0..5], round to nearest star, map to {0,51,102,153,204,255}."""
#     if rating_float is None:
#         rating_float = 0.0
#     rating_float = max(0.0, min(5.0, rating_float))
#     stars = round(rating_float)  # integer 0..5
#     return str(stars * 51)


# class RekordboxSyncPlugin(BeetsPlugin):
#     def __init__(self):
#         super().__init__()

#         # Default configuration merged with user config
#         self.config.add({
#             'conflict_resolution': {
#                 'artist': 'beets',
#                 'title': 'beets',
#                 'filename': 'beets',
#                 'genre': 'beets',
#                 'bpm': 'rekordbox',
#                 'song_key': 'rekordbox',
#                 'tags': 'rekordbox',
#                 'colour': 'rekordbox',
#                 'rating': 'rekordbox',
#                 'default': 'last_modified'
#             },
#             'field_mapping': {
#                 'beets_to_rekordbox': {
#                     'artist': 'Artist',
#                     'title': 'Name',
#                     'genre': 'Genre',
#                     'bpm': 'AverageBpm',
#                     'song_key': 'Tonality',
#                     'tags': 'Comments',
#                     'rekordbox_colour': 'Colour',
#                     'rating': 'Rating'
#                 },
#                 'rekordbox_to_beets': {
#                     'Artist': 'artist',
#                     'Name': 'title',
#                     'Genre': 'genre',
#                     'AverageBpm': 'bpm',
#                     'Tonality': 'song_key',
#                     'Comments': 'tags',
#                     'Colour': 'rekordbox_colour',
#                     'Rating': 'rating'
#                 }
#             }
#         })

#         # This determines if we remove KAPOT/VERKEERD tracks
#         self.remove_kapot = False

#         # Paths from config
#         self.xml_path = os.path.abspath(
#             os.path.expanduser(self.config['rekordbox_xml_path'].as_str())
#         )
#         self.backup_dir = os.path.abspath(
#             os.path.expanduser(self.config['backup_directory'].as_str())
#         )

#         # Logger setup
#         # self.logger = self._setup_logger()
#         self._log = CustomLogger("RekordboxSync", default_color="green")

#         # CLI command definition
#         self.sync_command = Subcommand('sync-rkbx', aliases=['sr', 'sync-rk', 'sync-rb'])
#         self.sync_command.parser.add_option(
#             '--fields',
#             dest='fields',
#             help="Comma-separated list of fields to sync"
#         )
#         self.sync_command.parser.add_option(
#             '--rkbx-xml',
#             dest='rkbx_xml',
#             default=self.xml_path,
#             help="Path to Rekordbox XML"
#         )
#         self.sync_command.func = self.cli_sync_rkbx

#     def commands(self):
#         """Register the CLI subcommand(s)."""
#         return [self.sync_command]

#     # --------------------------------------------------------------------
#     # CLI ENTRYPOINT (Thin Wrapper)
#     # --------------------------------------------------------------------
#     def cli_sync_rkbx(self, lib, opts, args):
#         """
#         The function that runs when you type:
#             `beet sync-rkbx [options]`
#         """
#         fields = opts.fields.split(',') if opts.fields else None
#         xml_path_override = opts.rkbx_xml

#         # We can allow a user to override whether we remove kapot/etc. here:
#         # self.remove_kapot = True or some other logic if needed

#         # Call our core sync method
#         kapot_verkeerd_items = self.sync_rekordbox(
#             lib=lib,
#             fields=fields,
#             xml_path=xml_path_override,
#             remove_kapot=self.remove_kapot
#         )

#         # Possibly log or handle the returned items
#         if kapot_verkeerd_items:
#             self._log.log("info",
#                 f"{len(kapot_verkeerd_items)} items removed from Rekordbox due to KAPOT/VERKEERD tags"
#             )
#         return kapot_verkeerd_items
#     # --------------------------------------------------------------------
#     # PUBLIC METHOD: PROGRAMMATIC ENTRYPOINT
#     # --------------------------------------------------------------------
#     def sync_rekordbox(self, lib, fields=None, xml_path=None, remove_kapot=False):
#         """
#         Main (programmatic) method to sync between Beets and Rekordbox.

#         :param lib: Beets library object
#         :param fields: List of field names to sync (optional)
#         :param xml_path: Path to Rekordbox XML (optional)
#         :param remove_kapot: If True, remove 'KAPOT'/'VERKEERD' tracks from XML

#         :return: A list of items that had KAPOT or VERKEERD in comments (removed from Rekordbox).
#         """
#         self.remove_kapot = remove_kapot

#         # If the caller specified an alternate XML path, use it:
#         if xml_path:
#             self.xml_path = os.path.abspath(os.path.expanduser(xml_path))

#         # 1) Backup
#         self._perform_backup('sync_metadata')

#         # 2) Parse XML
#         try:
#             self._validate_path(self.xml_path)
#             tree = ET.parse(self.xml_path)
#             root = tree.getroot()
#         except Exception as e:
#             self._log.log("error", f"Error reading Rekordbox XML: {e}")
#             return []

#         # Build track dictionary
#         rb_tracks = self._parse_rekordbox_tracks(root)

#         items = lib.items()
#         updated_beets = 0
#         updated_rekordbox = 0
#         not_found = 0
#         kapot_verkeerd_items = []

#         # Field mappings from config
#         map_beets2rb = self.config['field_mapping']['beets_to_rekordbox'].get()
#         map_rb2beets = self.config['field_mapping']['rekordbox_to_beets'].get()

#         # Restrict fields if specified
#         if fields:
#             map_beets2rb = {k: v for k, v in map_beets2rb.items() if k in fields}
#             map_rb2beets = {k: v for k, v in map_rb2beets.items() if v in fields}

#         for item in items:
#             if not item.path:
#                 self._log.log("debug", f"Skipping item without a valid path: {item}")
#                 continue

#             full_path, short_path, rekordbox_file, rekordbox_location = self._process_path(item)
#             if not rekordbox_file:
#                 continue

#             rb_track = rb_tracks.get(rekordbox_file.lower())
#             if not rb_track:
#                 self._log.log("debug",
#                     f"Track not found in Rekordbox: {rekordbox_file} "
#                     f"({item.title} - {item.artist})"
#                 )
#                 not_found += 1
#                 continue

#             # 1) Remove KAPOT/VERKEERD if remove_kapot == True
#             if self.remove_kapot:
#                 comments_raw = rb_track.get('Comments', '') or ''
#                 if re.search(r'(KAPOT|VERKEERD)', comments_raw, re.IGNORECASE):
#                     track_elem = root.find(f".//TRACK[@TrackID='{rb_track['TrackID']}']")
#                     collection_elem = root.find(".//COLLECTION")
#                     if track_elem is not None and collection_elem is not None:
#                         collection_elem.remove(track_elem)

#                     kapot_verkeerd_items.append(item)
#                     continue

#             # 2) Update Beets from Rekordbox
#             updated_beets += self._update_beets_metadata(item, rb_track, map_rb2beets)

#             # 3) Update Rekordbox from Beets
#             updated_rekordbox += self._update_rekordbox_metadata(root, rb_track, item, map_beets2rb)

#             # 4) Sync tags (two-way merge) if 'tags' in either map
#             if 'tags' in map_beets2rb or 'tags' in map_rb2beets.values():
#                 updated_beets += self._sync_tags(item, rb_track)
#                 updated_rekordbox += self._sync_tags(item, rb_track, reverse=True)

#         # Write back to disk
#         self._write_rekordbox_xml(self.xml_path, root)

#         self._log.log("info", f"Updated metadata for {updated_beets} tracks in Beets.")
#         self._log.log("info", f"Updated metadata for {updated_rekordbox} tracks in Rekordbox.")
#         self._log.log("info", f"Skipped {not_found} tracks not found in Rekordbox.")

#         return updated_beets, updated_rekordbox, kapot_verkeerd_items

#     # --------------------------------------------------------------------
#     # Utility / Setup
#     # --------------------------------------------------------------------
#     def _setup_logger(self):
#         logger = logging.getLogger('rekordbox_sync')
#         handler = logging.StreamHandler()
#         handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
#         logger.addHandler(handler)
#         logger.setLevel(logging.DEBUG)
#         return logger

#     def _validate_path(self, path):
#         """Validate the existence of a file path."""
#         if not os.path.exists(path):
#             raise FileNotFoundError(f"The path does not exist: {path}")

#     def _perform_backup(self, operation):
#         os.makedirs(self.backup_dir, exist_ok=True)
#         timestamp = time.strftime('%Y%m%d_%H%M%S')
#         rb_xml_path = os.path.abspath(os.path.expanduser(self.xml_path))

#         self._validate_path(rb_xml_path)
#         rb_backup_path = os.path.join(
#             self.backup_dir,
#             f"rekordbox_backup_{operation}_{timestamp}.xml"
#         )
#         try:
#             shutil.copy(rb_xml_path, rb_backup_path)
#             self._log.log("error", f"Backed up Rekordbox XML to {rb_backup_path}")
#         except Exception as e:
#             self._log.log("error", f"Failed to back up Rekordbox XML: {e}")

#     def _parse_rekordbox_tracks(self, root):
#         """
#         Returns a dict keyed by lowercased filename -> track dict
#         with fields: TrackID, Artist, Name, Location, Genre, AverageBpm,
#         Tonality, Comments, Colour, Rating, etc.
#         """
#         tracks = {}
#         for track_elem in root.findall('.//TRACK'):
#             track_data = {
#                 'TrackID': track_elem.get('TrackID'),
#                 'Artist': track_elem.get('Artist'),
#                 'Name': track_elem.get('Name'),
#                 'filename': os.path.basename(track_elem.get('Location', '')),
#                 'Location': track_elem.get('Location', ''),
#                 'Genre': track_elem.get('Genre'),
#                 'AverageBpm': track_elem.get('AverageBpm'),
#                 'Tonality': track_elem.get('Tonality'),
#                 'Comments': track_elem.get('Comments'),
#                 'Colour': track_elem.get('Colour'),
#                 'Rating': track_elem.get('Rating')
#             }

#             # Skip if mandatory fields are missing
#             if (not track_data['TrackID'] or
#                 not track_data['Name'] or
#                 not track_data['Location']):
#                 self._log.log("debug",
#                     f"Skipping invalid track with missing fields: {track_data}"
#                 )
#                 continue

#             filename_key = track_data['filename']
#             if filename_key:
#                 tracks[filename_key.lower()] = track_data

#         return tracks

#     def _write_rekordbox_xml(self, path, root):
#         try:
#             tree = ET.ElementTree(root)
#             tree.write(path, encoding='UTF-8', xml_declaration=True)
#             self._log.log("debug", f"Successfully wrote Rekordbox XML to {path}")
#         except Exception as e:
#             self._log.log("error", f"Error writing Rekordbox XML: {e}")

#     # --------------------------------------------------------------------
#     # Conflict Resolution
#     # --------------------------------------------------------------------
#     def _resolve_conflict(self, beets_value, rb_value, field_name, rb_track, item):
#         """
#         Resolve metadata conflicts based on config.
#         If rating != '0' and colour is non-empty => Rekordbox always wins
#         else follow conflict rules (beets, rekordbox, last_modified).
#         """
#         rb_rating_str = rb_track.get('Rating', '0')
#         rb_colour = rb_track.get('Colour', '')

#         if rb_rating_str != '0' and rb_colour:
#             return rb_value

#         conflict_rule = self.config['conflict_resolution'].get().get(field_name, None)
#         if not conflict_rule:
#             conflict_rule = self.config['conflict_resolution']['default'].get(str)

#         if conflict_rule == 'beets':
#             return beets_value
#         elif conflict_rule == 'rekordbox':
#             return rb_value
#         elif conflict_rule == 'last_modified':
#             rb_last = rb_track.get('LastModified', 0)
#             beets_last = getattr(item, 'added', 0)
#             return rb_value if rb_last > beets_last else beets_value

#         return beets_value

#     # --------------------------------------------------------------------
#     # Updating Beets and Rekordbox
#     # --------------------------------------------------------------------
#     def _update_beets_metadata(self, item, rb_track, mapping):
#         """Update Beets metadata fields from Rekordbox track data."""
#         updated = 0
#         for rb_field, beets_field in mapping.items():
#             if beets_field == 'tags':
#                 # handled in _sync_tags
#                 continue

#             rb_value = rb_track.get(rb_field, None)
#             beets_value = getattr(item, beets_field, None)

#             # Colour -> item.rekordbox_colour
#             if beets_field == 'rekordbox_colour':
#                 if rb_value and rb_value in COLOUR_MAP:
#                     color_str = COLOUR_MAP[rb_value]
#                 else:
#                     color_str = ''
#                 resolved = self._resolve_conflict(beets_value, color_str, beets_field, rb_track, item)
#                 if resolved != beets_value:
#                     setattr(item, beets_field, resolved)
#                     item.store()
#                     updated += 1
#                 continue

#             # Rating -> item.rating
#             if beets_field == 'rating':
#                 rating_float = RATING_RB_TO_FLOAT.get(rb_value, 0.0)
#                 resolved = self._resolve_conflict(beets_value, rating_float, beets_field, rb_track, item)
#                 if resolved != beets_value:
#                     setattr(item, beets_field, resolved)
#                     item.store()
#                     updated += 1
#                 continue

#             # Normal fields
#             resolved_value = self._resolve_conflict(beets_value, rb_value, beets_field, rb_track, item)
#             if resolved_value != beets_value and resolved_value is not None:
#                 setattr(item, beets_field, resolved_value)
#                 item.store()
#                 updated += 1

#         return updated

#     def _update_rekordbox_metadata(self, root, rb_track, item, mapping):
#         """Update Rekordbox XML track data from Beets item fields."""
#         updated = 0
#         track_elem = root.find(f".//TRACK[@TrackID='{rb_track['TrackID']}']")
#         if track_elem is None:
#             return 0

#         for beets_field, rb_field in mapping.items():
#             if beets_field == 'tags':
#                 # handled in _sync_tags
#                 continue

#             beets_value = getattr(item, beets_field, None)
#             old_rb_value = rb_track.get(rb_field, None)

#             # item.rekordbox_colour -> track.Colour
#             if beets_field == 'rekordbox_colour' and rb_field == 'Colour':
#                 hex_found = None
#                 for hex_code, color_str in COLOUR_MAP.items():
#                     if color_str == beets_value:
#                         hex_found = hex_code
#                         break
#                 new_rb_val = hex_found if hex_found else ''
#                 resolved = self._resolve_conflict(new_rb_val, old_rb_value, beets_field, rb_track, item)
#                 if resolved != old_rb_value:
#                     track_elem.set('Colour', resolved)
#                     rb_track['Colour'] = resolved
#                     updated += 1
#                 continue

#             # item.rating -> track.Rating
#             if beets_field == 'rating' and rb_field == 'Rating':
#                 new_rb_rating = rating_float_to_rb(beets_value)
#                 resolved = self._resolve_conflict(new_rb_rating, old_rb_value, beets_field, rb_track, item)
#                 if resolved != old_rb_value:
#                     track_elem.set('Rating', resolved)
#                     rb_track['Rating'] = resolved
#                     updated += 1
#                 continue

#             # Normal fields
#             resolved_value = self._resolve_conflict(beets_value, old_rb_value, beets_field, rb_track, item)
#             if resolved_value != old_rb_value:
#                 track_elem.set(rb_field, resolved_value if resolved_value else '')
#                 rb_track[rb_field] = resolved_value
#                 updated += 1

#         return updated

#     def _sync_tags(self, item, rb_track, reverse=False):
#         """
#         Synchronize tags between Beets and Rekordbox "Comments".
#         We unify tags: union of both sides -> apply to both sides.
#         """
#         rb_tags_raw = rb_track.get('Comments', '')
#         rb_tags = [
#             tag.strip()
#             for tag in rb_tags_raw.replace('/*', '').replace('*/', '').split(' / ')
#         ] if rb_tags_raw else []

#         beets_tags_raw = item.tags if item.tags else ''
#         beets_tags = [tag.strip() for tag in beets_tags_raw.split(',')] if beets_tags_raw else []

#         total_tags = sorted(list(set(rb_tags + beets_tags)))
#         rb_tags_new = '*/ ' + ' / '.join(total_tags) + ' */' if total_tags else ''
#         beets_tags_new = ','.join(total_tags)

#         changes = 0
#         if beets_tags_new != item.tags:
#             item.tags = beets_tags_new
#             item.store()
#             changes += 1

#         if rb_tags_new != rb_tags_raw:
#             rb_track['Comments'] = rb_tags_new
#             changes += 1

#         return changes

#     def _process_path(self, item):
#         """Process and normalize the path for an item."""
#         try:
#             full_path = os.path.abspath(item.path.decode('utf-8'))
#             short_path = os.path.basename(full_path)
#             rekordbox_file = short_path.replace(' ', '%20')
#             rekordbox_location = f"file://localhost/D:/Muziek/AUDIOFILES/{rekordbox_file}"
#             return full_path, short_path, rekordbox_file, rekordbox_location
#         except Exception as e:
#             self._log.log("error", f"Error processing path for item: {item}. Error: {e}")
#             return None, None, None, None

import os
import time
import shutil
import xml.etree.ElementTree as ET
import logging
import re
from urllib.parse import quote, unquote

from beetsplug.custom_logger import CustomLogger
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand
from beets import config

# -----------------------------------------------------------
# Color and Rating Mapping
# -----------------------------------------------------------

COLOUR_MAP = {
    '0x660099': 'RAVE',
    '0xFF007F': 'EZPARTY',
    '0x00FF00': 'LOUNGE',
    '0x0000FF': 'LOOM / TRIPPY',
    '0x25FDE9': 'COOLDOWN',
    '0xFFA500': 'Orange',
    '0xFF0000': 'BEUKEN',
    '0xFFFF00': 'NODJ'
}

RATING_RB_TO_FLOAT = {
    '0': 0.0,
    '51': 1.0,
    '102': 2.0,
    '153': 3.0,
    '204': 4.0,
    '255': 5.0
}

def rating_float_to_rb(rating_float):
    """Clamp rating_float to [0..5], round to nearest star, map to {0,51,102,153,204,255}."""
    if rating_float is None:
        rating_float = 0.0
    rating_float = max(0.0, min(5.0, rating_float))
    stars = round(rating_float)  # integer 0..5
    return str(stars * 51)

# -----------------------------------------------------------
# Helper function: get primary artist from item
# -----------------------------------------------------------
def get_main_artist(item):
    """
    If item.artist is non-empty, return it. Otherwise, if item.artists
    is a list of strings, return the first entry. Otherwise, return "".
    """
    # 1) If `artist` is present, use it
    if item.artist:  # or: if item.artist and item.artist.strip():
        return item.artist.strip()

    # 2) If no main artist, check `artists`
    # The user might have item.artists as a list of strings
    many = getattr(item, "artists", None)
    if isinstance(many, list) and len(many) > 0:
        # Return the first string in that list
        return many[0].strip()
    # If `artists` is not a list, or is empty, just return ""
    return ""



class RekordboxSyncPlugin(BeetsPlugin):
    def __init__(self):
        super().__init__()

        # Default configuration merged with user config
        self.config.add({
            'conflict_resolution': {
                'artist': 'beets',
                'title': 'beets',
                'filename': 'beets',
                'genre': 'beets',
                'bpm': 'rekordbox',
                'song_key': 'rekordbox',
                'tags': 'rekordbox',
                'colour': 'rekordbox',
                'rating': 'rekordbox',
                'default': 'last_modified'
            },
            'field_mapping': {
                'beets_to_rekordbox': {
                    'artist': 'Artist',
                    'title': 'Name',
                    'genre': 'Genre',
                    'bpm': 'AverageBpm',
                    'song_key': 'Tonality',
                    'tags': 'Comments',
                    'rekordbox_colour': 'Colour',
                    'rating': 'Rating'
                },
                'rekordbox_to_beets': {
                    'Artist': 'artist',
                    'Name': 'title',
                    'Genre': 'genre',
                    'AverageBpm': 'bpm',
                    'Tonality': 'song_key',
                    'Comments': 'tags',
                    'Colour': 'rekordbox_colour',
                    'Rating': 'rating'
                }
            }
        })

        # This determines if we remove KAPOT/VERKEERD tracks
        self.remove_kapot = False

        # Paths from config
        self.xml_path = os.path.abspath(
            os.path.expanduser(self.config['rekordbox_xml_path'].as_str())
        )
        self.backup_dir = os.path.abspath(
            os.path.expanduser(self.config['backup_directory'].as_str())
        )

        # Logger setup
        self._log = CustomLogger("RekordboxSync", default_color="green")

        # CLI command definition
        self.sync_command = Subcommand('sync-rkbx', aliases=['sr', 'sync-rk', 'sync-rb'])
        self.sync_command.parser.add_option(
            '--fields',
            dest='fields',
            help="Comma-separated list of fields to sync"
        )
        self.sync_command.parser.add_option(
            '--rkbx-xml',
            dest='rkbx_xml',
            default=self.xml_path,
            help="Path to Rekordbox XML"
        )
        self.sync_command.func = self.cli_sync_rkbx

    def commands(self):
        """Register the CLI subcommand(s)."""
        return [self.sync_command]

    # --------------------------------------------------------------------
    # CLI ENTRYPOINT (Thin Wrapper)
    # --------------------------------------------------------------------
    def cli_sync_rkbx(self, lib, opts, args):
        """
        The function that runs when you type:
            `beet sync-rkbx [options]`
        """
        fields = opts.fields.split(',') if opts.fields else None
        xml_path_override = opts.rkbx_xml

        # self.remove_kapot could be set based on another CLI option if desired
        updated_beets, updated_rekordbox, kapot_verkeerd_items = self.sync_rekordbox(
            lib=lib,
            fields=fields,
            xml_path=xml_path_override,
            remove_kapot=self.remove_kapot
        )

        # Possibly log or handle the returned items
        if kapot_verkeerd_items:
            self._log.log("info",
                f"{len(kapot_verkeerd_items)} items removed from Rekordbox due to KAPOT/VERKEERD tags"
            )
        self._log.log("info", f"Updated {updated_beets} in Beets, {updated_rekordbox} in Rekordbox.")
        return kapot_verkeerd_items

    # --------------------------------------------------------------------
    # PUBLIC METHOD: PROGRAMMATIC ENTRYPOINT
    # --------------------------------------------------------------------
    def sync_rekordbox(self, lib, fields=None, xml_path=None, remove_kapot=False):
        """
        Main (programmatic) method to sync between Beets and Rekordbox.

        :param lib: Beets library object
        :param fields: List of field names to sync (optional)
        :param xml_path: Path to Rekordbox XML (optional)
        :param remove_kapot: If True, remove 'KAPOT'/'VERKEERD' tracks from XML

        :return: (updated_beets_count, updated_rekordbox_count, kapot_verkeerd_items_list)
        """
        self.remove_kapot = remove_kapot

        # If the caller specified an alternate XML path, use it:
        if xml_path:
            self.xml_path = os.path.abspath(os.path.expanduser(xml_path))

        # 1) Backup
        self._perform_backup('sync_metadata')

        # 2) Parse XML
        try:
            self._validate_path(self.xml_path)
            tree = ET.parse(self.xml_path)
            root = tree.getroot()
        except Exception as e:
            self._log.log("error", f"Error reading Rekordbox XML: {e}")
            return (0, 0, [])

        # Build track dictionary
        rb_tracks = self._parse_rekordbox_tracks(root)

        items = lib.items()
        updated_beets = 0
        updated_rekordbox = 0
        not_found = 0
        kapot_verkeerd_items = []

        # Field mappings from config
        map_beets2rb = self.config['field_mapping']['beets_to_rekordbox'].get()
        map_rb2beets = self.config['field_mapping']['rekordbox_to_beets'].get()

        # Restrict fields if specified
        if fields:
            map_beets2rb = {k: v for k, v in map_beets2rb.items() if k in fields}
            map_rb2beets = {k: v for k, v in map_rb2beets.items() if v in fields}

        for item in items:
            if not item.path:
                self._log.log("debug", f"Skipping item without a valid path: {item}")
                continue

            full_path, short_path, rekordbox_file, rekordbox_location = self._process_path(item)
            if not rekordbox_file:
                continue

            rb_track = rb_tracks.get(rekordbox_file.lower())
            if not rb_track:
                # We didn't find this track in Rekordbox => create a new entry
                self._log.log("debug",
                    f"Creating a new TRACK in Rekordbox for: {rekordbox_file} ({item.title} - {item.artist})"
                )
                new_rb_track = self._create_rekordbox_track(root, item)
                if new_rb_track is None:
                    self._log.log("error", f"Failed to create a new TRACK for {item}. Skipping.")
                    continue

                # Insert into our dictionary so subsequent logic can proceed
                rb_tracks[rekordbox_file.lower()] = new_rb_track
                rb_track = new_rb_track
            else:
                # If remove_kapot is True, we might remove the existing track
                if self.remove_kapot:
                    comments_raw = rb_track.get('Comments', '') or ''
                    if re.search(r'(KAPOT|VERKEERD)', comments_raw, re.IGNORECASE):
                        track_elem = root.find(f".//TRACK[@TrackID='{rb_track['TrackID']}']")
                        collection_elem = root.find(".//COLLECTION")
                        if track_elem is not None and collection_elem is not None:
                            collection_elem.remove(track_elem)
                        kapot_verkeerd_items.append(item)
                        continue

            # 1) Update Beets from Rekordbox
            updated_beets += self._update_beets_metadata(item, rb_track, map_rb2beets)

            # 2) Update Rekordbox from Beets
            updated_rekordbox += self._update_rekordbox_metadata(root, rb_track, item, map_beets2rb)

            # 3) Sync tags (two-way merge) if 'tags' in either map
            if 'tags' in map_beets2rb or 'tags' in map_rb2beets.values():
                updated_beets += self._sync_tags(item, rb_track)
                updated_rekordbox += self._sync_tags(item, rb_track, reverse=True)

        # Write back to disk
        self._write_rekordbox_xml(self.xml_path, root)

        self._log.log("info", f"Updated metadata for {updated_beets} tracks in Beets.")
        self._log.log("info", f"Updated metadata for {updated_rekordbox} tracks in Rekordbox.")
        self._log.log("info", f"Skipped {not_found} tracks not found in Rekordbox (or could not be created).")

        return (updated_beets, updated_rekordbox, kapot_verkeerd_items)

    # --------------------------------------------------------------------
    # HELPER: Create a new <TRACK> element if missing
    # --------------------------------------------------------------------
    def _create_rekordbox_track(self, root, item):
        """
        Create a new <TRACK> element in Rekordbox XML (under <COLLECTION>)
        for the given Beets item. Returns a new track dict suitable for
        insertion into rb_tracks, or None if unsuccessful.

        This method also uses get_main_artist(item) to handle fallback
        from `artists` if `artist` is empty.
        """
        collection_elem = root.find(".//COLLECTION")
        if collection_elem is None:
            self._log.log("error", "No <COLLECTION> element found in Rekordbox XML!")
            return None

        # Generate a new TrackID
        new_id = self._get_next_track_id(root)

        # Create the <TRACK> element
        track_elem = ET.SubElement(collection_elem, "TRACK")
        track_elem.set("TrackID", str(new_id))

        # location is from _process_path
        full_path, short_path, rekordbox_file, rekordbox_location = self._process_path(item)

        # Use the fallback logic for Artist
        primary_artist = get_main_artist(item)

        # Minimal attributes. The rest will be updated by conflict resolution if needed
        track_elem.set("Location", rekordbox_location or "")
        track_elem.set("Name", item.title or "")
        track_elem.set("Artist", primary_artist)
        track_elem.set("Genre", item.genre or "")

        # Build a dict that matches the structure in _parse_rekordbox_tracks
        new_rb_track = {
            'TrackID': str(new_id),
            'Artist': primary_artist,
            'Name': item.title or "",
            'filename': short_path or "",
            'Location': rekordbox_location or "",
            'Genre': item.genre or "",
            'AverageBpm': None,
            'Tonality': None,
            'Comments': "",
            'Colour': "",
            'Rating': "0"
        }
        return new_rb_track

    def _get_next_track_id(self, root):
        """
        Find the largest existing TrackID among <TRACK> elements
        and return (max_id + 1).
        """
        max_id = 0
        for trk in root.findall(".//TRACK"):
            tid_str = trk.get("TrackID")
            if tid_str and tid_str.isdigit():
                tid = int(tid_str)
                if tid > max_id:
                    max_id = tid
        return max_id + 1

    # --------------------------------------------------------------------
    # Utility / Setup
    # --------------------------------------------------------------------
    def _validate_path(self, path):
        """Validate the existence of a file path."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"The path does not exist: {path}")

    def _perform_backup(self, operation):
        os.makedirs(self.backup_dir, exist_ok=True)
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        rb_xml_path = os.path.abspath(os.path.expanduser(self.xml_path))

        self._validate_path(rb_xml_path)
        rb_backup_path = os.path.join(
            self.backup_dir,
            f"rekordbox_backup_{operation}_{timestamp}.xml"
        )
        try:
            shutil.copy(rb_xml_path, rb_backup_path)
            self._log.log("info", f"Backed up Rekordbox XML to {rb_backup_path}")
        except Exception as e:
            self._log.log("error", f"Failed to back up Rekordbox XML: {e}")

    def _parse_rekordbox_tracks(self, root):
        """
        Returns a dict keyed by lowercased filename -> track dict
        with fields: TrackID, Artist, Name, Location, Genre, AverageBpm,
        Tonality, Comments, Colour, Rating, etc.
        """
        tracks = {}
        for track_elem in root.findall('.//TRACK'):
            track_data = {
                'TrackID': track_elem.get('TrackID'),
                'Artist': track_elem.get('Artist'),
                'Name': track_elem.get('Name'),
                'filename': os.path.basename(track_elem.get('Location', '')),
                'Location': track_elem.get('Location', ''),
                'Genre': track_elem.get('Genre'),
                'AverageBpm': track_elem.get('AverageBpm'),
                'Tonality': track_elem.get('Tonality'),
                'Comments': track_elem.get('Comments'),
                'Colour': track_elem.get('Colour'),
                'Rating': track_elem.get('Rating')
            }

            # Skip if mandatory fields are missing
            if (not track_data['TrackID'] or
                not track_data['Name'] or
                not track_data['Location']):
                self._log.log("debug",
                    f"Skipping invalid track with missing fields: {track_data}"
                )
                continue

            filename_key = track_data['filename']
            if filename_key:
                tracks[filename_key.lower()] = track_data

        return tracks

    def _write_rekordbox_xml(self, path, root):
        try:
            tree = ET.ElementTree(root)
            tree.write(path, encoding='UTF-8', xml_declaration=True)
            self._log.log("debug", f"Successfully wrote Rekordbox XML to {path}")
        except Exception as e:
            self._log.log("error", f"Error writing Rekordbox XML: {e}")

    # --------------------------------------------------------------------
    # Conflict Resolution
    # --------------------------------------------------------------------
    def _resolve_conflict(self, beets_value, rb_value, field_name, rb_track, item):
        """
        Resolve metadata conflicts based on config.
        If rating != '0' and colour is non-empty => Rekordbox always wins
        else follow conflict rules (beets, rekordbox, last_modified).
        """
        rb_rating_str = rb_track.get('Rating', '0')
        rb_colour = rb_track.get('Colour', '')

        if rb_rating_str != '0' and rb_colour:
            return rb_value

        conflict_rule = self.config['conflict_resolution'].get().get(field_name, None)
        if not conflict_rule:
            conflict_rule = self.config['conflict_resolution']['default'].get(str)

        if conflict_rule == 'beets':
            return beets_value
        elif conflict_rule == 'rekordbox':
            return rb_value
        elif conflict_rule == 'last_modified':
            rb_last = rb_track.get('LastModified', 0)
            beets_last = getattr(item, 'added', 0)
            return rb_value if rb_last > beets_last else beets_value

        return beets_value

    # --------------------------------------------------------------------
    # Updating Beets and Rekordbox
    # --------------------------------------------------------------------
    def _update_beets_metadata(self, item, rb_track, mapping):
        """Update Beets metadata fields from Rekordbox track data."""
        updated = 0
        for rb_field, beets_field in mapping.items():
            if beets_field == 'tags':
                # handled in _sync_tags
                continue

            rb_value = rb_track.get(rb_field, None)
            beets_value = getattr(item, beets_field, None)

            # Colour -> item.rekordbox_colour
            if beets_field == 'rekordbox_colour':
                if rb_value and rb_value in COLOUR_MAP:
                    color_str = COLOUR_MAP[rb_value]
                else:
                    color_str = ''
                resolved = self._resolve_conflict(beets_value, color_str, beets_field, rb_track, item)
                if resolved != beets_value:
                    setattr(item, beets_field, resolved)
                    item.store()
                    updated += 1
                continue

            # Rating -> item.rating
            if beets_field == 'rating':
                rating_float = RATING_RB_TO_FLOAT.get(rb_value, 0.0)
                resolved = self._resolve_conflict(beets_value, rating_float, beets_field, rb_track, item)
                if resolved != beets_value:
                    setattr(item, beets_field, resolved)
                    item.store()
                    updated += 1
                continue

            # Normal fields
            resolved_value = self._resolve_conflict(beets_value, rb_value, beets_field, rb_track, item)
            if resolved_value != beets_value and resolved_value is not None:
                setattr(item, beets_field, resolved_value)
                item.store()
                updated += 1

        return updated

    def _update_rekordbox_metadata(self, root, rb_track, item, mapping):
        """Update Rekordbox XML track data from Beets item fields."""
        updated = 0
        track_elem = root.find(f".//TRACK[@TrackID='{rb_track['TrackID']}']")
        if track_elem is None:
            return 0

        for beets_field, rb_field in mapping.items():
            if beets_field == 'tags':
                # handled in _sync_tags
                continue

            # -- special fallback for artist
            if beets_field == 'artist':
                beets_value = get_main_artist(item)
            else:
                beets_value = getattr(item, beets_field, None)

            old_rb_value = rb_track.get(rb_field, None)

            # item.rekordbox_colour -> track.Colour
            if beets_field == 'rekordbox_colour' and rb_field == 'Colour':
                hex_found = None
                for hex_code, color_str in COLOUR_MAP.items():
                    if color_str == beets_value:
                        hex_found = hex_code
                        break
                new_rb_val = hex_found if hex_found else ''
                resolved = self._resolve_conflict(new_rb_val, old_rb_value, beets_field, rb_track, item)
                if resolved != old_rb_value:
                    track_elem.set('Colour', resolved)
                    rb_track['Colour'] = resolved
                    updated += 1
                continue

            # item.rating -> track.Rating
            if beets_field == 'rating' and rb_field == 'Rating':
                new_rb_rating = rating_float_to_rb(beets_value)
                resolved = self._resolve_conflict(new_rb_rating, old_rb_value, beets_field, rb_track, item)
                if resolved != old_rb_value:
                    track_elem.set('Rating', resolved)
                    rb_track['Rating'] = resolved
                    updated += 1
                continue

            # Normal fields
            resolved_value = self._resolve_conflict(beets_value, old_rb_value, beets_field, rb_track, item)
            if resolved_value != old_rb_value:
                track_elem.set(rb_field, resolved_value if resolved_value else '')
                rb_track[rb_field] = resolved_value
                updated += 1

        return updated

    def _sync_tags(self, item, rb_track, reverse=False):
        """
        Synchronize tags between Beets and Rekordbox "Comments".
        We unify tags: union of both sides -> apply to both sides.
        """
        rb_tags_raw = rb_track.get('Comments', '')
        rb_tags = [
            tag.strip()
            for tag in rb_tags_raw.replace('/*', '').replace('*/', '').split(' / ')
        ] if rb_tags_raw else []

        beets_tags_raw = item.tags if item.tags else ''
        beets_tags = [tag.strip() for tag in beets_tags_raw.split(',')] if beets_tags_raw else []

        total_tags = sorted(list(set(rb_tags + beets_tags)))
        rb_tags_new = '*/ ' + ' / '.join(total_tags) + ' */' if total_tags else ''
        beets_tags_new = ','.join(total_tags)

        changes = 0
        if beets_tags_new != item.tags:
            item.tags = beets_tags_new
            item.store()
            changes += 1

        if rb_tags_new != rb_tags_raw:
            rb_track['Comments'] = rb_tags_new
            changes += 1

        return changes

    def _process_path(self, item):
        """Process and normalize the path for an item. Returns (full_path, short_path, rb_file, rb_location)."""
        try:
            full_path = os.path.abspath(item.path.decode('utf-8'))
            short_path = os.path.basename(full_path)
            # Encode spaces as '%20' so Rekordbox recognizes them
            rekordbox_file = short_path.replace(' ', '%20')

            # Optionally encode other special characters if needed:
            #    rekordbox_file = quote(short_path)
            rekordbox_location = f"file://localhost/D:/Muziek/AUDIOFILES/{rekordbox_file}"

            return full_path, short_path, rekordbox_file, rekordbox_location
        except Exception as e:
            self._log.log("error", f"Error processing path for item: {item}. Error: {e}")
            return None, None, None, None

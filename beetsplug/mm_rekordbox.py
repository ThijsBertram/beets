import os
import time
import shutil
import xml.etree.ElementTree as ET
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand
import logging




class RekordboxSyncPlugin(BeetsPlugin):
    def __init__(self):
        super().__init__()

        self.beets_db_path = "F:/PROGRAMMING/beets - fork/beets.db"
        self.audiofiles_path = "D:/Muziek/AUDIOFILES"
        # Add configuration defaults
        self.config.add({
            'rekordbox_xml_path': 'F:/DJ/Rekordbox/rekordbox.xml',
            'backup_directory': '~/beets_backups',
            'filter': None,  # Add a filter/query field in the config
            'conflict_resolution': {
                'artist': 'beets',
                'title': 'beets',
                'filename': 'beets',
                'genre': 'beets',
                'bpm': 'rekordbox',
                'song_key': 'rekordbox',
                'default': 'last_modified'
            }
        })

        # Initialize logger
        self.logger = logging.getLogger('rekordbox_sync')
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)

          # Initialize commands
        export_playlists_cmd = Subcommand(
            'export-beets-playlists',
            help='Export Beets playlists to Rekordbox with optional filtering.'
        )
        export_playlists_cmd.parser.add_option(
            '-q', '--query', action='store', help='Query to filter tracks'
        )
        export_playlists_cmd.func = self.export_beets_playlists

        import_playlists_cmd = Subcommand(
            'import-rekordbox-playlists',
            help='Import Rekordbox playlists into Beets with optional filtering.'
        )
        import_playlists_cmd.parser.add_option(
            '-q', '--query', action='store', help='Query to filter tracks'
        )
        import_playlists_cmd.func = self.import_rekordbox_playlists

        sync_metadata_cmd = Subcommand(
            'sync-metadata',
            help='Sync metadata between Beets and Rekordbox with conflict resolution.'
        )
        sync_metadata_cmd.parser.add_option(
            '-q', '--query', action='store', help='Query to filter tracks'
        )
        sync_metadata_cmd.func = self.sync_metadata

        # Store commands in a custom attcribute to avoid conflict
        self.subcommands = [export_playlists_cmd, import_playlists_cmd, sync_metadata_cmd]

    def commands(self):
        """Return the list of commands for the plugin."""
        return self.subcommands
    # ----------------------- Metadata Sync -----------------------



    def sync_metadata(self, lib, opts, args):
        """Perform a two-way sync of metadata between Beets and Rekordbox."""

        def normalize_value(value):
            """Normalize values for comparison (strip whitespace, lower case, etc.)."""
            if isinstance(value, str):
                return value.strip().lower()  # Strip whitespace and convert to lowercase
            if isinstance(value, (int, float)):
                return round(float(value), 2)  # Round numerical values to 2 decimal places for consistency
            return value  # Return other types as-is
        
        # Perform backup
        self._perform_backup('sync_metadata')

        # LOAD XML
        rb_xml_path = os.path.abspath(os.path.expanduser(self.config['rekordbox_xml_path'].as_str()))
        try:
            tree = ET.parse(rb_xml_path)
            root = tree.getroot()
        except Exception as e:
            self.logger.error(f"Error reading Rekordbox XML: {e}")
            return

        # PARSE XML
        rb_tracks = self._parse_rekordbox_tracks(root)
        self.logger.info(f"Found {len(rb_tracks)} tracks in Rekordbox.")

        updated_beets = []
        updated_rekordbox = []
        items = [i for i in lib.items()]

        # LOOP OVER ALL BEETS ITEMS
        for item in items:
            print('=========================================================')
            if not item.path:
                self.logger.warning(f"Skipping item without a valid path: {item}")
                continue

            # PATH STUFF
            try:
                full_path = os.path.abspath(item.path.decode('utf-8'))
                short_path = os.path.basename(item.path.decode('utf-8'))
                rekordbox_path = short_path.replace(' ', '%20')
                rekordbox_location = f"file://localhost/D:/Muziek/AUDIOFILES/{rekordbox_path}"
            except Exception as e:
                self.logger.warning(f"Error processing path for item: {item}. Error: {e}")
                quit()
                continue
            print(full_path)
            print(short_path)
            print(rekordbox_path)
            print(rekordbox_location)
            print()

            title_artist = (item.title, item.artist)

            # MATCH REKORDBOX TRACK
            rb_track = rb_tracks.get(rekordbox_path) or rb_tracks.get(title_artist)
            if not rb_track:
                self.logger.debug(f"Track not found in Rekordbox: {rekordbox_path} ({item.title} - {item.artist})")
                continue

            # LOOP OVER ATTRIBUTES / FIELDS
            updated_beets = 0
            updated_rekordbox = 0

            for beets_field, rk_field in [('artist', 'Artist'), ('title', 'Name'), ('genre', 'Genre'), ('bpm', 'AverageBpm'), ('song_key', 'Tonality')]:
                
                # FIELD VALUES
                beets_value = getattr(item, beets_field, None)
                rb_value = rb_track.get(rk_field)

                conflict_resolution = self.config['conflict_resolution']
                rule = conflict_resolution[beets_field].get() if conflict_resolution[beets_field].exists() else conflict_resolution['default'].get()
                self.logger.debug(f"Field: {beets_field}, Beets: {beets_value}, Rekordbox: {rb_value}, Rule: {rule}")

                if rule == 'beets':
                    resolved_value = beets_value
                elif rule == 'rekordbox':
                    resolved_value = rb_value
                elif rule == 'last_modified':
                    resolved_value = rb_value if rb_track.get('LastModified', 0) > item.added else beets_value
                else:
                    resolved_value = beets_value


                # DECIDE ON GOLDEN TRUTH
                resolved_value

                # UPDATE BEETS FIELD
                if normalize_value(resolved_value) != normalize_value(beets_value):
                    setattr(item, beets_field, resolved_value)
                    self.logger.debug(f"Updated BEETS value for {beets_field}: {resolved_value} (normalized: {normalize_value(resolved_value)})")
                    item.store()
                    updated_beets += 1
                # UPDATE REKORDBOX FIELD
                elif normalize_value(resolved_value) != normalize_value(rb_value):
                    self.logger.debug(f"Updated REKORDBOX value for {rk_field}: {resolved_value} (normalized: {normalize_value(resolved_value)})")
                    rb_track[rk_field] = resolved_value

                    # Use XPath to find the TRACK with the specified TrackID
                    track_id = rb_track['TrackID']
                    track = root.find(f".//TRACK[@TrackID='{track_id}']")  # Replace 123 with your TrackID
                    if track is not None:
                        track.set(rk_field, resolved_value)
                        updated_rekordbox += 1
                    else:
                        print(f"TRACK with TrackID {track_id} not found.")

                # self.logger.debug(f"Resolved value for {beets_field}: {resolved_value} (normalized: {normalize_value(resolved_value)})")



        # Write back Rekordbox updates
        self._write_rekordbox_xml(rb_xml_path, root)

        self.logger.info(f"Updated metadata for {updated_beets} tracks in Beets.")
        self.logger.info(f"Updated metadata for {updated_rekordbox} tracks in Rekordbox.")



    # def sync_metadata(self, lib, opts, args):
    #     """Perform a two-way sync of metadata between Beets and Rekordbox."""
    #     # Perform backup
    #     self._perform_backup('sync_metadata')

    #     # Load Rekordbox XML
    #     rb_xml_path = os.path.abspath(os.path.expanduser(self.config['rekordbox_xml_path'].as_str()))
    #     try:
    #         tree = ET.parse(rb_xml_path)
    #         root = tree.getroot()
    #     except Exception as e:
    #         self.logger.error(f"Error reading Rekordbox XML: {e}")
    #         return

    #     rb_tracks = self._parse_rekordbox_tracks(root)
    #     self.logger.info(f"Found {len(rb_tracks)} tracks in Rekordbox.")

    #     updated_beets = []
    #     updated_rekordbox = []
    #     c_updated = 0

    #     items = [i for i in lib.items()]

    #     for item in items[:10]:
    #         # Skip items without a valid path
    #         if not item.path:
    #             self.logger.warning(f"Skipping item without a valid path: {item}")
    #             continue

    #         # Match tracks
    #         try:
    #             filename = os.path.basename(item.path.decode('utf-8')).replace(' ', '%20')
    #         except Exception as e:
    #             self.logger.warning(f"Error processing path for item: {item}. Error: {e}")
    #             continue

    #         title_artist = (item.title, item.artist)
    #         rb_track = rb_tracks.get(filename) or rb_tracks.get(title_artist)

    #         if not rb_track:
    #             self.logger.debug(f"Track not found in Rekordbox: {filename} ({item.title} - {item.artist})")
    #             continue

    #         updated = False
    #         for field in ['artist', 'title', 'filename', 'genre', 'bpm', 'song_key']:
    #             beets_value = getattr(item, field, None)
    #             rb_value = rb_track.get(field)

    #             # Get conflict resolution rule
    #             conflict_resolution = self.config['conflict_resolution']
    #             rule = conflict_resolution[field].get() if conflict_resolution[field].exists() else conflict_resolution['default'].get()

    #             # Apply conflict resolution
    #             if rule == 'beets':
    #                 resolved_value = beets_value
    #             elif rule == 'rekordbox':
    #                 resolved_value = rb_value
    #             elif rule == 'last_modified':
    #                 resolved_value = rb_value if rb_track.get('LastModified', 0) > item.added else beets_value
    #             else:
    #                 resolved_value = beets_value

    #             # Normalize values and compare
    #             if self.normalize_value(resolved_value) != self.normalize_value(beets_value):
    #                 setattr(item, field, resolved_value)
    #                 updated = True
    #             elif self.normalize_value(resolved_value) != self.normalize_value(rb_value):
    #                 rb_track[field] = resolved_value
    #                 updated = True

    #         if updated:
    #             c_updated += 1
    #             updated_beets.append(item)
    #             updated_rekordbox.append(rb_track)
    #             item.store()

    #     # Persist changes to Beets database only if updates are made
    #     for item in updated_beets:
    #         item.store()

    #     # Persist changes to Rekordbox XML
    #     for rb_track in updated_rekordbox:
    #         for track_elem in root.findall('.//TRACK'):
    #             if track_elem.get('TrackID') == rb_track['TrackID']:
    #                 track_elem.set('Artist', rb_track['artist'] or "")
    #                 track_elem.set('Name', rb_track['title'] or "")
    #                 track_elem.set('Location', rb_track['filename'] or "")
    #                 track_elem.set('Genre', rb_track['genre'] or "")
    #                 track_elem.set('AverageBpm', str(rb_track['bpm']) if rb_track['bpm'] else "")
    #                 track_elem.set('Tonality', rb_track['song_key'] or "")
    #                 break

    #     # Write back Rekordbox updates
    #     self._write_rekordbox_xml(rb_xml_path, root)

    #     self.logger.info(f"Updated metadata for {len(updated_beets)} tracks in Beets.")
    #     self.logger.info(f"Updated metadata for {len(updated_rekordbox)} tracks in Rekordbox.")

    #     self.logger.info(f"{c_updated} items updated")

    # ----------------------- Playlists Export -----------------------

    def export_beets_playlists(self, lib, opts, args):
        """Export Beets playlists to Rekordbox XML with filtering."""
        # Perform backup
        self._perform_backup('export_playlists')

        # Parse Rekordbox XML or create a new structure
        rb_xml_path = os.path.abspath(os.path.expanduser(self.config['rekordbox_xml_path'].as_str()))
        try:
            tree = ET.parse(rb_xml_path)
            root = tree.getroot()
        except Exception as e:
            self.logger.warning(f"Error reading Rekordbox XML. Creating new file: {e}")
            root = ET.Element('DJ_PLAYLISTS')
            ET.SubElement(root, 'PLAYLISTS')

        playlists_root = root.find('PLAYLISTS')

        # Fetch playlists and apply filter
        filter_query = self.config['filter'].as_str() if self.config['filter'].exists() else None
        self.logger.info(f"Using filter: {filter_query if filter_query else 'No filter applied'}")

        playlists = lib.get_playlists()  # Assuming `get_playlists()` fetches all playlists
        for playlist in playlists:
            # Apply filtering to tracks
            filtered_tracks = self._filter_tracks(playlist.tracks, filter_query)
            if not filtered_tracks:
                self.logger.info(f"Playlist '{playlist.name}' skipped due to filtering.")
                continue

            rb_playlist_name = f"{playlist.name} (From Beets)"
            rb_playlist = self._find_or_create_playlist(playlists_root, rb_playlist_name)

            # Append filtered tracks to Rekordbox playlist
            for track in filtered_tracks:
                if not self._track_in_playlist(rb_playlist, track):
                    track_elem = ET.SubElement(rb_playlist, 'TRACK')
                    track_elem.set('Name', track.title)
                    track_elem.set('Artist', track.artist)
                    track_elem.set('Location', track.path)
                    self.logger.info(f"Added track '{track.title}' by '{track.artist}' to playlist '{rb_playlist_name}'.")

        # Write updated XML
        self._write_rekordbox_xml(rb_xml_path, root)

    # ----------------------- Playlists Import -----------------------

    def import_rekordbox_playlists(self, lib, opts, args):
        """Import Rekordbox playlists into Beets with filtering."""
        # Perform backup
        self._perform_backup('import_playlists')

        # Parse Rekordbox XML
        rb_xml_path = os.path.abspath(os.path.expanduser(self.config['rekordbox_xml_path'].as_str()))
        try:
            tree = ET.parse(rb_xml_path)
            root = tree.getroot()
        except Exception as e:
            self.logger.error(f"Error reading Rekordbox XML: {e}")
            return

        playlists_root = root.find('PLAYLISTS')
        for rb_playlist in playlists_root.findall('NODE'):
            rb_playlist_name = rb_playlist.get('Name')
            tracks = self._get_tracks_from_playlist(rb_playlist)

            # Apply filtering to tracks
            filter_query = self.config['filter'].as_str() if self.config['filter'].exists() else None
            filtered_tracks = self._filter_tracks(tracks, filter_query)
            if not filtered_tracks:
                self.logger.info(f"Playlist '{rb_playlist_name}' skipped due to filtering.")
                continue

            # Create or update Beets playlist
            beets_playlist = lib.get_playlist(rb_playlist_name) or lib.create_playlist(rb_playlist_name, 'rekordbox')
            for track in filtered_tracks:
                if not beets_playlist.has_track(track):
                    beets_playlist.add_track(track)
                    self.logger.info(f"Added track '{track['title']}' by '{track['artist']}' to Beets playlist '{rb_playlist_name}'.")

    # ----------------------- Helpers and Backups -----------------------

    def _filter_tracks(self, tracks, query):
        """Filter tracks based on a Beets query."""
        if not query:
            return tracks
        # Simulate filtering logic
        filtered_tracks = [track for track in tracks if self._track_matches_query(track, query)]
        return filtered_tracks

    def _track_matches_query(self, track, query):
        """Check if a track matches a query."""
        if 'genre:' in query:
            genre = query.split('genre:')[1].strip()
            return track.get('genre') == genre
        if 'bpm:' in query:
            bpm_range = query.split('bpm:')[1].strip().split('-')
            if len(bpm_range) == 2:
                bpm_min, bpm_max = map(int, bpm_range)
                return bpm_min <= int(track.get('bpm', 0)) <= bpm_max
        return True

    def _find_or_create_playlist(self, playlists_root, playlist_name):
        """Find or create a playlist in the Rekordbox XML."""
        for node in playlists_root.findall('NODE'):
            if node.get('Name') == playlist_name:
                return node
        new_playlist = ET.SubElement(playlists_root, 'NODE', {'Name': playlist_name})
        return new_playlist

    def _track_in_playlist(self, rb_playlist, track):
        """Check if a track is already in the Rekordbox playlist."""
        for rb_track in rb_playlist.findall('TRACK'):
            if rb_track.get('Location') == track.path:
                return True
        return False

    def _get_tracks_from_playlist(self, rb_playlist):
        """Extract tracks from a Rekordbox playlist."""
        tracks = []
        for rb_track in rb_playlist.findall('TRACK'):
            tracks.append({
                'title': rb_track.get('Name'),
                'artist': rb_track.get('Artist'),
                'path': rb_track.get('Location')
            })
        return tracks

    def _write_rekordbox_xml(self, path, root):
        """Write the updated Rekordbox XML file."""
        self.logger.info(f"Attempting to write rekordbox XML to: {path}")
        try:
            tree = ET.ElementTree(root)
            tree.write(path, encoding='UTF-8', xml_declaration=True)
            self.logger.info(f"Successfully wrote Rekordbox XML to {path}")
        except Exception as e:
            self.logger.error(f"Error writing Rekordbox XML: {e}")

    def _perform_backup(self, operation):
        """Create a backup of Beets and Rekordbox data."""
        backup_dir = os.path.abspath(os.path.expanduser(self.config['backup_directory'].as_str()))
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = time.strftime('%Y%m%d_%H%M%S')
        rb_xml_path = os.path.abspath(os.path.expanduser(self.config['rekordbox_xml_path'].as_str()))
        beets_db_path = self.beets_db_path  # Default Beets SQLite path

        # Rekordbox backup
        rb_backup_path = os.path.join(backup_dir, f"rekordbox_backup_{operation}_{timestamp}.xml")
        try:
            shutil.copy(rb_xml_path, rb_backup_path)
            self.logger.info(f"Backed up Rekordbox XML to {rb_backup_path}")
        except Exception as e:
            self.logger.warning(f"Failed to back up Rekordbox XML: {e}")

        # Beets backup
        beets_backup_path = os.path.join(backup_dir, f"beets_backup_{operation}_{timestamp}.db")
        try:
            shutil.copy(beets_db_path, beets_backup_path)
            self.logger.info(f"Backed up Beets database to {beets_backup_path}")
        except Exception as e:
            self.logger.warning(f"Failed to back up Beets database: {e}")

    def _parse_rekordbox_tracks(self, root):
        """Extract track metadata from Rekordbox XML."""
        tracks = {}
        for track_elem in root.findall('.//TRACK'):
            # Extract track metadata
            track_data = {
                'TrackID': track_elem.get('TrackID'),  # Ensure TrackID is included
                'artist': track_elem.get('Artist'),
                'title': track_elem.get('Name'),
                'filename': os.path.basename(track_elem.get('Location', '')),
                'location': track_elem.get('Location', ''),
                'genre': track_elem.get('Genre'),
                'bpm': track_elem.get('AverageBpm'),
                'song_key': track_elem.get('Tonality'),
                'LastModified': track_elem.get('ModifiedDate')  # Optional, may not exist
            }

            # Use filename as the primary key for uniqueness
            filename_key = track_data['filename']
            if filename_key:
                tracks[filename_key] = track_data

            # Use (title, artist) as a secondary key
            if track_data['title'] and track_data['artist']:
                tracks[(track_data['title'], track_data['artist'])] = track_data

        self.logger.info(f"Parsed {len(tracks)} tracks from Rekordbox XML.")
        return tracks



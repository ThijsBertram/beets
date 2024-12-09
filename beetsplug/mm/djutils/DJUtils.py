import re
from typing import List
from schema import Schema, And, Use, Optional, SchemaError
from beets.dbcore.query import SubstringQuery, FieldQuery, MatchQuery, OrQuery, AndQuery, NumericQuery
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand, decargs, print_
from beets.library import Library
from beets.util import bytestring_path, mkdirall
from beets import config
import os
import shutil
import math
from ..cli.pipe_commands import setlist





# TO DO: continue with "create_setlist_from_dcit". 
#           - fix subgenre none handling
#           - fix handling of config values for path_format
#           - FINISHED with v0 :D
# 
# IMPROVEMENTS
#           - make query part creation generic, so we can use any field 
#                   - dynamic query class used based on field type 


DB_PATH = config['library'].as_filename()
lib = Library(DB_PATH)


class DJUtilsPlugin(BeetsPlugin):
    def __init__(self):
        super().__init__()

        self.lib = Library(DB_PATH)

        self.bpm_interval = int(str(config['mm']['DJUtils']['setlist_dir_struct']['bpm_interval']))
        self.path_format = config['mm']['DJUtils']['setlist_dir_struct']['path_format']
        self.setlist_path = str(config['mm']['DJUtils']['setlist_dir_struct']['setlist_path'])

    def create_setlist_from_dict(self, setlist_data, setlist_path=None, path_format=None, setlist_name='setlist'):
        query_string = self.create_query_from_validated_data(setlist_data)

        print(query_string)

        items = self.lib.items(query_string)
        if not items:
            print("No items matched the query/schema.")
            return

        print(len(items))

        if not path_format:
            path_format = self.path_format
        if not setlist_path:
            setlist_path = self.setlist_path

        setlist_dir = os.path.join(setlist_path, setlist_name)
        os.makedirs(setlist_dir, exist_ok=True)

        print("PATH FORMAT")
        print(path_format)

        quit()
        for item in items:
            subdir = setlist_dir
            for key in path_format:
                if key == 'bpm':
                    bpm_range = (item.bpm // self.bpm_interval) * self.bpm_interval
                    subdir = os.path.join(subdir, f'{bpm_range}-{bpm_range + self.bpm_interval - 1} BPM')
                elif key == 'genre':
                    subdir = os.path.join(subdir, item.genre)
                elif key == 'subgenre':
                    subdir = os.path.join(subdir, item.subgenre)
                elif key == 'rating':
                    rating = min(int(item.rating), 5)
                    subdir = os.path.join(subdir, f'Rating {rating}')
                else:
                    print(f'Unknown key in path_format: {key}')
                
                print(subdir)
                continue
                os.makedirs(subdir, exist_ok=True)
            quit()
            dest_path = os.path.join(subdir, os.path.basename(item.path))
            shutil.copy2(item.path, dest_path)
            print(f"Added {item} to setlist at {dest_path}")

        print(f"Setlist created at: {setlist_dir}")
            
    def create_query_from_validated_data(self, validated_data):
        query_parts = []

        if 'genre' in validated_data:
            genres = validated_data['genre']
            genre_queries = [MatchQuery('genre', genre) for genre in genres]
            query_parts.append(OrQuery(genre_queries))

        # FIX: ALLOW NONE         
        # if 'subgenre' in validated_data:
        #     subgenres = validated_data['subgenre']
        #     subgenre_queries = [MatchQuery('subgenre', subgenre) for subgenre in subgenres]
        #     query_parts.append(OrQuery(subgenre_queries))

        if 'min_bpm' in validated_data:
            min_bpm = validated_data['min_bpm']
            query_parts.append(NumericQuery('bpm', f'{min_bpm}..'))

        if 'max_bpm' in validated_data:
            max_bpm = validated_data['max_bpm']
            query_parts.append(NumericQuery('bpm', f'..{max_bpm}'))

        if 'exclude_artist' in validated_data:
            exclude_artists = validated_data['exclude_artist']
            exclude_artist_queries = [MatchQuery('artist', f'!{artist}') for artist in exclude_artists]
            query_parts.append(OrQuery(exclude_artist_queries))

        if 'active' in validated_data:
            active = validated_data['active']
            query_parts.append(NumericQuery('active', f'{active}..'))

        if 'rating' in validated_data:
            rating = validated_data['rating']
            query_parts.append(NumericQuery('rating', f'{rating}..'))

        # Combine all query parts into one query using AndQuery
        combined_query = AndQuery(query_parts)
        return combined_query
    
    def create_setlist(self, lib, opts, args):

        setlist_data = {}
        if opts.genre:
            setlist_data['genre'] = opts.genre.split(',')
        if opts.subgenre:
            setlist_data['subgenre'] = opts.subgenre.split(',')
        if opts.min_bpm:
            setlist_data['min_bpm'] = int(opts.min_bpm)
        if opts.max_bpm:
            setlist_data['max_bpm'] = int(opts.max_bpm)
        if opts.exclude_artist:
            setlist_data['exclude_artist'] = opts.exclude_artist.split(',')
        if opts.active:
            setlist_data['active'] = int(opts.active)
        if opts.rating:
            setlist_data['rating'] = float(opts.rating)

        self.unique_genres = list(set(item.genre for item in self.lib.items(SubstringQuery('genre', '')) if item.genre))
        self.unique_subgenres = list(set(item.subgenre for item in self.lib.items(SubstringQuery('subgenre', '')) if item.subgenre))

        self.setlist_schema = Schema({
            Optional('genre', default=self.unique_genres): And(
                list,
                [And(str, lambda s: s in self.unique_genres)]
            ),
            Optional('subgenre', default=self.unique_subgenres): And(
                list,
                [And(str, lambda s: s in self.unique_subgenres)]
            ),
            Optional('min_bpm', default=151): int,
            Optional('max_bpm', default=152): int,
            Optional('exclude_artist'): And(
                list,
                [str]
            ),
            Optional('active', default=1): int,
            Optional('rating', default=2.5): float
        })

        validated_data = self.setlist_schema.validate(setlist_data)

        setlist_path = opts.setlist_path if opts.setlist_path else self.setlist_path
        path_format = opts.path_format if opts.path_format else self.path_format
        setlist_name = opts.setlist_name if opts.setlist_name else 'setlist'

        print("HIERO")
        print(validated_data)
        print(setlist_path)
        print(path_format)
        print(setlist_name)
        print('------')

        self.create_setlist_from_dict(validated_data, setlist_path, path_format, setlist_name)
    



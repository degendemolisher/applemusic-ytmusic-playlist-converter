#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import sys

import requests
from bs4 import BeautifulSoup

YELLOW = '\033[33m'
GREEN = '\033[32m'
RED = '\033[31m'
RESET = '\033[0m'


def main():
    # Parse one argument: the playlist URL
    parser = argparse.ArgumentParser(description='Convert Apple Music playlist to a JSON file')
    parser.add_argument('playlist_url', help='Apple Music playlist URL')
    parser.add_argument('-r', '--reverse', action='store_true', help='reverse the order of the songs')
    parser.add_argument('-n', '--with-name', action='store_true',
                        help='output {"name": playlist name, "songs": [...]} instead of the song list')
    args = parser.parse_args()

    playlist_url = args.playlist_url

    print(f'Getting playlist from Apple Music...', file=sys.stderr)
    name, songs = get_songs_from_apple_playlist(playlist_url)
    if args.reverse:
        songs.reverse()

    json.dump({'name': name, 'songs': songs} if args.with_name else songs, sys.stdout, indent=4)

    print(f'{GREEN} Done!{RESET}', file=sys.stderr)


def get_songs_from_apple_playlist(playlist_url):
    r = requests.get(playlist_url, timeout=30)

    # Check if the request was successful
    if r.status_code != 200:
        raise Exception(f'Error getting playlist from Apple Music: {r.text} ({r.status_code})')

    bellazuppa = BeautifulSoup(r.content, 'html.parser')
    script_tag = bellazuppa.find("script", {"id": "serialized-server-data"})
    if script_tag is None:
        raise Exception('Playlist data not found in Apple Music page')

    j = json.loads(script_tag.text)
    # Newer pages wrap the list in {"data": [...], "userTokenHash": ...}
    if isinstance(j, dict):
        j = j['data']

    name = get_playlist_name(j[0]['data'])
    print(f'{YELLOW} Found playlist "{name}"{RESET}', file=sys.stderr)

    # JQ query: '.[].data.sections[1].items[] | ([.title, .artistName, .tertiaryLinks[0].title])'
    songs = []
    track_section = next(s for s in j[0]['data']['sections'] if s.get('itemKind') == 'trackLockup')
    for song in track_section['items']:
        title = song['title']
        artist = song['artistName']
        album = song['tertiaryLinks'][0]['title'] if song.get('tertiaryLinks') else None
        duration = song['duration']

        songs.append({
            'title': title,
            'artist': artist,
            'album': album,
            'duration': duration,
        })

    return name, songs


def get_playlist_name(page):
    header = next((s for s in page['sections'] if s.get('itemKind') == 'containerDetailHeaderLockup'), None)
    if header and header.get('items'):
        return header['items'][0]['title'].strip()
    return page['seoData']['pageTitle'].removesuffix(' - Apple Music')


if __name__ == '__main__':
    main()

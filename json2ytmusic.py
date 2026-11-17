#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import os
import re
import sys

from ytauth import get_ytmusic

YELLOW = '\033[33m'
GREEN = '\033[32m'
RED = '\033[31m'
RESET = '\033[0m'

LENGTH_TOLERANCE_SECONDS = 5
ALBUM_SUFFIXES = (' - Single', ' - EP')
VERSION_TAG_PATTERNS = (
    r'\blive\b', r'\bremix\b', r'\binstrumental\b', r'\bkaraoke\b', r'\bacoustic\b', r'\bdemo\b',
    r'\bversion\b', r'\bsped up\b', r'\bslowed\b', '伴奏', '纯享版', '純享版', '現場', '现场',
)


def find_song(yt, song):
    """Return the first likely song result from the same album, else the first as long as the song,
    else a same-length album track or video, else the song result closest in length."""
    results = yt.search(f'{song["title"]} {song["artist"]}', filter='songs', limit=5)
    results = [r for r in results if r.get('videoId')][:5]
    if not results:
        return None

    plausible = [
        r for r in results
        if not has_unrequested_version_tag(r['title'], song['title']) and is_plausible_artist(r, song)
    ]

    if not song.get('duration'):
        return (plausible or results)[0]

    length = song['duration'] / 1000
    same_album = [r for r in results if is_same_album(r, song) and is_likely_same_song(r, song, length)]
    if same_album:
        return same_album[0]

    same_length = [r for r in plausible if is_same_length(r, length)]
    if same_length:
        return same_length[0]

    album_track = find_song_in_albums(yt, song, length)
    if album_track:
        return album_track

    video = find_song_in_videos(yt, song, length)
    if video:
        return video

    return min(results, key=lambda r: (
        has_unrequested_version_tag(r['title'], song['title']),
        not is_plausible_artist(r, song),
        shared_title_characters(r['title'], song['title']) == 0,
        length_difference(r, length),
    ))


def find_song_in_albums(yt, song, length):
    for album_result in yt.search(f'{album_name(song)} {song["artist"]}', filter='albums', limit=3)[:3]:
        tracks = yt.get_album(album_result['browseId'])['tracks']
        candidates = [t for t in tracks if t.get('videoId') and is_likely_same_song(t, song, length)]
        if candidates:
            return max(candidates, key=lambda t: shared_title_characters(t['title'], song['title']))

    return None


def find_song_in_videos(yt, song, length):
    title_without_brackets = re.sub(r'\s*[(\[].*?[)\]]', '', song['title'])
    videos = yt.search(f'{song["artist"]} {title_without_brackets}', filter='videos', limit=5)[:5]
    return next((v for v in videos if v.get('videoId') and is_likely_same_song(v, song, length)), None)


def is_likely_same_song(result, song, length):
    return is_same_length(result, length) \
        and shared_title_characters(result['title'], song['title']) > 0 \
        and not has_unrequested_version_tag(result['title'], song['title']) \
        and is_plausible_artist(result, song)


def is_plausible_artist(result, song):
    """An identical title outweighs the artist name, which can be romanised differently (Jess Lee, Li Jiawei)."""
    return normalise(result['title']) == normalise(song['title']) or not is_different_artist(result, song)


def is_different_artist(result, song):
    """Only names written in Latin letters can be compared, so 林家謙 is never a different artist from Terence Lam."""
    names = [a['name'] for a in result.get('artists') or []]
    wanted_words = name_words(song['artist'])
    return bool(names) and all(name.isascii() and not name_words(name) & wanted_words for name in names)


def name_words(name):
    return set(re.findall(r'[a-z0-9]+', name.lower()))


def album_name(song):
    album = song.get('album') or song['title']
    for suffix in ALBUM_SUFFIXES:
        album = album.removesuffix(suffix)
    return album


def is_same_album(result, song):
    """Only for albums not named after the song, since any single of that title would match those."""
    result_album = (result.get('album') or {}).get('name')
    if not song.get('album') or not result_album:
        return False
    wanted_album = normalise(album_name(song))
    return wanted_album != normalise(song['title']) and normalise(result_album) == wanted_album


def normalise(text):
    return re.sub(r'[\W_]+', '', text.lower())


def has_unrequested_version_tag(result_title, wanted_title):
    return any(
        re.search(tag, result_title, re.IGNORECASE) and not re.search(tag, wanted_title, re.IGNORECASE)
        for tag in VERSION_TAG_PATTERNS
    )


def is_same_length(result, length):
    return length_difference(result, length) <= LENGTH_TOLERANCE_SECONDS


def length_difference(result, length):
    if result.get('duration_seconds') is None:
        return float('inf')
    return abs(result['duration_seconds'] - length)


def format_length(milliseconds):
    seconds = milliseconds // 1000
    return f'{seconds // 60}:{seconds % 60:02}'


def shared_title_characters(a, b):
    return len(set(a.lower()) & set(b.lower()) - set(' ()-'))


def main():
    parser = argparse.ArgumentParser(description='Convert Apple Music playlist to YouTube Music')
    parser.add_argument('playlist_id', nargs='?', help='YouTube Music playlist ID (left out with --create)')
    parser.add_argument('input', nargs='?', help='Apple Music playlist JSON file (default stdin)')
    parser.add_argument('--create', metavar='TITLE',
                        help='create a new playlist with this title instead of adding to an existing one')
    parser.add_argument('--privacy', choices=('PRIVATE', 'UNLISTED', 'PUBLIC'), default='PRIVATE',
                        help='privacy of the playlist made by --create (default PRIVATE)')
    parser.add_argument('--result', metavar='FILE',
                        help='write the playlist ID and the uncertain and unfound songs to this JSON file')
    parser.add_argument('-o', '--oauth', default='oauth.json', help='OAuth file (default oauth.json)')
    parser.add_argument('-c', '--cache', default='ytmusic-cache.json', help='Cache file (default ytmusic-cache.json)')
    args = parser.parse_args()

    input_path = args.input
    if args.create:
        if args.input:
            parser.error('leave out the playlist ID when using --create')
        input_path = args.playlist_id
    elif not args.playlist_id:
        parser.error('give a playlist ID or --create TITLE')

    yt = get_ytmusic(args.oauth)

    cache = {}
    if os.path.exists(args.cache):
        with open(args.cache, 'r') as f:
            cache = json.load(f)

    existing = set()
    if args.create:
        print(f'{YELLOW} Finding songs for new playlist "{args.create}"{RESET}')
    else:
        # noinspection PyTypeChecker
        dst_playlist = yt.get_playlist(args.playlist_id, limit=None)

        author = dst_playlist.get('author', {}).get('name', 'Unknown')
        print(f'{YELLOW} Adding new songs to playlist "{dst_playlist["title"]}" by {author}{RESET}')

        for song in dst_playlist["tracks"]:
            existing.add(song['videoId'])

    if input_path:
        with open(input_path, 'r') as f:
            src_playlist = json.load(f)
    else:
        src_playlist = json.load(sys.stdin)
    if isinstance(src_playlist, dict):
        src_playlist = src_playlist['songs']

    to_add = []
    uncertain = []
    not_found = []

    try:
        for song in src_playlist:
            title = song['title']
            artist = song['artist']

            if song.get('videoId'):
                cache[f'{title} {artist}'] = song['videoId']
                if song['videoId'] not in existing and song['videoId'] not in to_add:
                    print(f'{GREEN} {title} - {artist} '.ljust(60, ' '), end='')
                    print(f'-> provided: {song["videoId"]}{RESET}')
                    to_add.append(song['videoId'])
                continue

            query = f'{title} {artist}'

            if query in cache:
                if cache[query] not in existing and cache[query] not in to_add:
                    print(f'{YELLOW} {title} - {artist} '.ljust(60, ' '), end='')
                    print(f'-> cached: {cache[query]}{RESET}')
                    to_add.append(cache[query])
                continue

            best_result = find_song(yt, song)
            if best_result is None:
                print(f'{RED} No results for {query}{RESET}')
                not_found.append({'title': title, 'artist': artist})
                continue

            best_artists = best_result.get('artists') or []
            is_length_matched = not song.get('duration') or is_same_length(best_result, song['duration'] / 1000)
            colour = GREEN if is_length_matched else YELLOW

            print(f'{colour} {title} - {artist} '.ljust(60, ' '), end='')
            print(f'-> {best_result.get("title", "")} - {best_artists[0]["name"] if best_artists else ""}', end='')
            if not is_length_matched:
                print(f' (warning: {best_result.get("duration", "unknown")} long, '
                      f'Apple Music has {format_length(song["duration"])})', end='')
                uncertain.append({
                    'title': title,
                    'artist': artist,
                    'length': format_length(song['duration']),
                    'match_title': best_result.get('title', ''),
                    'match_artist': best_artists[0]['name'] if best_artists else '',
                    'match_length': best_result.get('duration'),
                })
            print(RESET)

            if best_result['videoId'] not in existing and best_result['videoId'] not in to_add:
                to_add.append(best_result['videoId'])
                cache[query] = best_result['videoId']
    finally:
        with open(args.cache, 'w') as f:
            json.dump(cache, f, indent=4)

    if args.create:
        print(f'{YELLOW} Creating playlist "{args.create}" with {len(to_add)} songs...{RESET}')
        playlist_id = yt.create_playlist(args.create, '', privacy_status=args.privacy, video_ids=to_add)
        if not isinstance(playlist_id, str):
            raise Exception(f'Error creating playlist: {playlist_id}')
        print(f'{GREEN} Created https://music.youtube.com/playlist?list={playlist_id}{RESET}')
    else:
        playlist_id = args.playlist_id
        print(f'{YELLOW} Adding {len(to_add)} new songs...{RESET}')
        if len(to_add) > 0:
            result = yt.add_playlist_items(args.playlist_id, videoIds=to_add)
            if 'SUCCEEDED' not in str(result.get('status', '')):
                raise Exception(f'Error adding songs to playlist: {result}')

    if args.result:
        with open(args.result, 'w') as f:
            json.dump({
                'playlist_id': playlist_id,
                'added': len(to_add),
                'uncertain': uncertain,
                'not_found': not_found,
            }, f, ensure_ascii=False, indent=4)

    print(f'{GREEN} Done!{RESET}')


if __name__ == '__main__':
    main()

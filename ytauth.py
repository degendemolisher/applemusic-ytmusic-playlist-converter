# -*- coding: utf-8 -*-
import json
import os
import sys

from ytmusicapi import OAuthCredentials, YTMusic

RED = '\033[31m'
RESET = '\033[0m'

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')


def load_env_file(path=ENV_FILE):
    """Load KEY=VALUE lines from a .env file, without overriding variables already set."""
    if not os.path.exists(path):
        return

    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip().removeprefix('export ').strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in '\'"':
                value = value[1:-1]
            os.environ.setdefault(key, value)


def get_ytmusic(auth_file):
    """Create a YTMusic client from an OAuth or browser auth file (or unauthenticated if None).

    OAuth files need the client ID and secret they were created with, read from the
    YTMUSIC_CLIENT_ID and YTMUSIC_CLIENT_SECRET environment variables or the .env file.
    """
    load_env_file()

    if auth_file is None:
        return YTMusic()

    with open(auth_file, 'r') as f:
        is_oauth = 'refresh_token' in json.load(f)

    if not is_oauth:
        return YTMusic(auth_file)

    client_id = os.environ.get('YTMUSIC_CLIENT_ID')
    client_secret = os.environ.get('YTMUSIC_CLIENT_SECRET')
    if not client_id or not client_secret:
        print(f'{RED} {auth_file} is an OAuth file: set YTMUSIC_CLIENT_ID and YTMUSIC_CLIENT_SECRET{RESET}',
              file=sys.stderr)
        sys.exit(1)

    return YTMusic(auth_file, oauth_credentials=OAuthCredentials(client_id=client_id, client_secret=client_secret))

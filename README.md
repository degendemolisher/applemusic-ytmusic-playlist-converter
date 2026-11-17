# Apple Music playlist scraper and YouTube Music playlist uploader

This project contains two scripts:

- One to scrape an Apple Music playlist and save the list of tracks to a JSON
  file
- One to read the JSON file and upload the tracks to a YouTube Music playlist

## Usage

### Create virtualenv and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Scrape Apple Music playlist

```bash
./applemusic2json.py 'https://music.apple.com/xx/playlist/...' > playlist.json
```

### Upload to YouTube Music playlist

The playlist ID is the last part of the URL, after the last `/`, when viewing
the playlist in the browser.

```bash
# Authenticate with YouTube Music, using a Google Cloud OAuth client ID
# of type "TVs and Limited Input devices"
ytmusicapi oauth --file oauth.json

# The scripts need the same client ID and secret to use oauth.json.
# Export them, or put these two lines in a .env file in this directory.
export YTMUSIC_CLIENT_ID='...apps.googleusercontent.com'
export YTMUSIC_CLIENT_SECRET='...'

# Upload playlist
./json2ytmusic.py 'PlaylistID' 'playlist.json'

# Or create a new playlist (PRIVATE unless --privacy says otherwise)
./json2ytmusic.py --create 'Title' --privacy UNLISTED 'playlist.json'
```

`applemusic2json.py --with-name` outputs `{"name": ..., "songs": [...]}` instead of the
plain song list; `json2ytmusic.py` reads either.

`json2ytmusic.py --result result.json` writes the playlist ID, how many songs were added,
and the songs it matched only roughly (`uncertain`) or not at all (`not_found`).

## License

MIT License. See [LICENSE](LICENSE) file.

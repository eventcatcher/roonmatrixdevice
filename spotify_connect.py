import requests
import ssl
from rich import print
import sys
import logging
import urllib3
import spotipy
import spotipy.oauth2 as oauth2

class SpotifyConnect:
    def __init__(self, display_cover = True, log = True, force_ipv4_only = True, enable_spotify_connect = False, client_id = "", client_secret = "", spotify_connect_auth_url_callback = None):
        self.spotify = None
        self.display_cover = display_cover
        self.log = log			# log infos on or off
        self.scope = (
            "user-read-playback-state "
            "user-modify-playback-state "
            "user-read-currently-playing "
            "user-read-recently-played"
        )
        self.force_ipv4_only = force_ipv4_only
        self.enable_spotify_connect = enable_spotify_connect
        self.client_id = client_id
        self.client_secret = client_secret
        self.spotify_connect_auth_url_callback = spotify_connect_auth_url_callback
        self.logger = logging.getLogger('spotify_connect')
        self.spotify_connect_auth_success = False
        
        self.auth()

    def flexprint(self, str, objStr = None):
        if self.log is True:
            if objStr is None:
                if sys.stdout.isatty():
                    print(str)
                else:
                    self.logger.info(str)
            else:
                if sys.stdout.isatty():
                    print(str, objStr)
                else:
                    self.logger.info(str, objStr)

    def check_token(self):
        # Test: Verbindung prüfen
        try:
            user = self.spotify.me()
            if user:
                self.flexprint(f"✅ Spotify OAuth erfolgreich für {user['display_name']}\n")
                return True
            else:
                self.flexprint("✅ Spotify ClientCredentials aktiv\n")
                return False
        except Exception as e:
            self.flexprint("Verbindungstest fehlgeschlagen:", e)
            return False
    
    def auth(self):
        """
        Initializes Spotipy.
        - enable_spotify_connect => True: use oAuth2 Spotify Connect, False: use ClientCredentials (read-only access)
        - Forces IPv4 if desired (force_ipv4_only)
        """
        if not self.client_id or not self.client_secret:
            raise ValueError("Spotify credentials missing (client_id or client_secret).")

        # Optionale IPv4-Erzwingung
        class IPv4OnlyAdapter(requests.adapters.HTTPAdapter):
            def init_poolmanager(self, *args, **kwargs):
                context = ssl.create_default_context()
                kwargs["ssl_context"] = context
                self.poolmanager = urllib3.poolmanager.PoolManager(*args, **kwargs)

        session = requests.Session()
        if self.force_ipv4_only:
            session.mount("https://", IPv4OnlyAdapter())

        cache_path = "/home/"+ ('coverplayer' if self.display_cover is True else 'rmuser') +"/FTP/.spotify-cache"
        self.flexprint('Spotify Connect cache_path: ' + str(cache_path))

        if self.enable_spotify_connect is True:
            self.flexprint("🔑 Using Spotify OAuth (Connect control enabled)")
            self.auth_manager = oauth2.SpotifyOAuth(
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri="http://127.0.0.1:8888/callback",
                scope=self.scope,
                cache_path=cache_path,
                open_browser=False,
            )

            try:
                token_info = self.auth_manager.get_cached_token()
                if token_info and not self.auth_manager.is_token_expired(token_info):
                    self.spotify_connect_auth_success = True
                    self.flexprint("✅ Spotify Connect Token found and valid")
                else:
                    # no valid token: try to refresh (can fail)
                    token_info = self.auth_manager.refresh_access_token(token_info["refresh_token"])
                    self.spotify_connect_auth_success = True
                    self.flexprint("🔄 Spotify Connect Token refreshed")
            except Exception as e:
                # no Token exist or not refreshable
                self.flexprint("⚠️ Invalid Spotify Connect authentification:", e)
                auth_url = self.auth_manager.get_authorize_url()
                self.flexprint('spotify connect token not exist → request by app')
                self.spotify_connect_auth_url_callback(auth_url)
                self.spotify_connect_auth_success = False
                return
        else:
            self.flexprint("🧩 Using Client Credentials (read-only access)")
            self.auth_manager = oauth2.SpotifyClientCredentials(
                client_id=self.client_id,
                client_secret=self.client_secret,
                cache_path=cache_path,
            )

        self.spotify = spotipy.Spotify(auth_manager=self.auth_manager, requests_session=session)
        return self.spotify

    def auth_response(self, redirect_response):
        try:
            code = self.auth_manager.parse_response_code(redirect_response)
            token_info = self.auth_manager.get_access_token(code=code, as_dict=True)
            self.auth_manager.cache_handler.save_token_to_cache(token_info)
            self.flexprint("Spotify Connect OAuth-Token saved. Future launches run automatically.")
            self.auth()
            return True
        except Exception as e:
            self.flexprint("Spotify Connect OAuth response error: " + str(e))
    
    def get_spotify_connect_auth_state(self):
        return self.spotify_connect_auth_success

    # Allgemeine Infos
    def devices(self):
        if self.spotify is None:
            return []
        devices = self.spotify.devices()
        return devices.get("devices", []) if "devices" in devices else []

    def current_or_last_played_track(self):
        if self.spotify is None:
            return
        item = None
        playback = self.spotify.current_playback()
        if not playback or not playback.get("item"):
            recent = self.spotify.current_user_recently_played(limit=1)
            if not recent or not recent.get("items"):
                return None
            else:
                item = recent["items"][0]["track"]
        else:
            item = playback["item"]
        if item is None:
            return

        artist = ", ".join([a["name"] for a in item["artists"]])
        cover = item['album']['images'][0]['url'] if ('album' in item and 'images' in item['album'] and len(item['album']['images']) > 0 and 'url' in item['album']['images'][0]) else ''
        status = "playing" if (playback is not None and 'is_playing' in playback and playback['is_playing']) else "paused"
        shuffle = "true" if (playback is not None and 'shuffle_state' in playback and playback['shuffle_state']) else "false"
        repeat = "true" if (playback is not None and 'repeat_state' in playback and playback['repeat_state'] != 'off') else "false"
        position = int(playback['progress_ms'] / 1000) if (playback is not None and 'progress_ms' in playback) else 0
        total = int(item['duration_ms'] / 1000)
        
        return {"zone": "SpotifyConnect", "status": status, "artist": artist, "album": item["album"]["name"], "track": item["name"], "shuffle": shuffle, "repeat": repeat, "position": position, "total": total, "sourcetype": "stream", "id": item['uri'], "cover": cover}

    # Wiedergabe-Steuerung
    def play(self, device_id=None, context_uri=None, uris=None, offset=None):
        if self.spotify is None:
            return
        self.flexprint('SpotifyConnect => play with device_id: ' + str(device_id))
        if uris:
            self.spotify.start_playback(device_id=device_id, uris=uris)
        elif context_uri:
            self.spotify.start_playback(device_id=device_id, context_uri=context_uri, offset=offset)
        else:
            self.spotify.start_playback(device_id=device_id)

    def pause(self, device_id=None):
        if self.spotify is None:
            return
        self.flexprint('SpotifyConnect => pause with device_id: ' + str(device_id))
        self.spotify.pause_playback(device_id=device_id)

    def next(self, device_id=None):
        if self.spotify is None:
            return
        self.spotify.next_track(device_id=device_id)

    def previous(self, device_id=None):
        if self.spotify is None:
            return
        self.spotify.previous_track(device_id=device_id)

    def set_volume(self, volume_percent, device_id=None):
        # volume_percent: 0–100
        if self.spotify is None:
            return
        volume_percent = max(0, min(100, int(volume_percent)))
        self.spotify.volume(volume_percent, device_id=device_id)

    # Shuffle / Repeat
    def shuffle(self, state=True, device_id=None):
        if self.spotify is None:
            return
        self.spotify.shuffle(state, device_id=device_id)

    def repeat(self, mode="context", device_id=None):
        # mode: 'off', 'track' oder 'context'
        if self.spotify is None:
            return
        self.spotify.repeat(mode, device_id=device_id)
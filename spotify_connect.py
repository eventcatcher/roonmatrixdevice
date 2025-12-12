#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# SpotifyConnect Class - Roonmatrix extension to support Spotify Connect
# Roonmatrix extension class
# version 1.2.0, date: 06.12.2025
#
# control and play music via Spotify Connect
#
# © Stephan Wilhelm, Bielefeld, Germany, coded @ 2025
#
# copy to /home/coverplayer/FTP
#
# logs saved to /home/coverplayer/FTP/logs

import requests
import ssl
from builtins import print as rawprint
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

        self.errorlog = True	# log errors
        self.debug = False		# log debug messages (variable information)        
        
        try:
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
            self.logger = None
            if self.display_cover is True:
                self.logger = logging.getLogger('spotify_connect')
            self.spotify_connect_auth_success = False
        
            self.auth()
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]init error:[/red] {e}")

    def flexprint(self, str, objStr = None):
        if self.log is True:
            if objStr is None:
                if sys.stdout.isatty() or self.logger is None:
                    if self.display_cover is True:
                        print(str) # output as colored text with rich (rich overrides original print)
                    else:
                        if sys.stdout.isatty():
                            print(str) # output as colored text with rich (rich overrides original print)
                        else:
                            rawprint(str) # output as raw text with rich like color and text style tags
                else:
                    self.logger.info(str) # output as colored text with rich (rich overrides original print) into own log folder with special logger formatting
            else:
                if sys.stdout.isatty() or self.logger is None:
                    if self.display_cover is True:
                        print(str, objStr) # output as colored text with rich (rich overrides original print)
                    else:
                        if sys.stdout.isatty():
                            print(str, objStr) # output as colored text with rich (rich overrides original print)
                        else:
                            rawprint(str, objStr) # output as raw text with rich like color and text style tags
                else:
                    self.logger.info(f"{str} {objStr}") # output as colored text with rich (rich overrides original print) into own log folder with special logger formatting

    def check_token(self):
        # check connection
        try:
            user = self.spotify.me()
            if user:
                self.flexprint(f"✅ Spotify OAuth successful for {user['display_name']}\n")
                return True
            else:
                self.flexprint("✅ Spotify ClientCredentials active\n")
                return False
        except Exception as e:
            if self.errorlog is True: self.flexprint("Spotify Connect Connection test failed:", e)
            return False
    
    def auth(self):
        # Initializes Spotipy.
        # - enable_spotify_connect => True: use oAuth2 Spotify Connect, False: use ClientCredentials (read-only access)
        # Forces IPv4 if desired (force_ipv4_only)

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

    def devices(self):
        try:
            if self.spotify is None:
                return []
            devices = self.spotify.devices()
            return devices.get("devices", []) if "devices" in devices else []
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]Spotify Connect devices error:[/red] {e}")
            return []

    def current_or_last_played_track(self):
        try:
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
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]Spotify Connect current or last played track error:[/red] {e}")
            return

    # playback controls
    def play(self, device_id=None, context_uri=None, uris=None, offset=None):
        try:
            if self.spotify is None:
                return
            self.flexprint('SpotifyConnect => play with device_id: ' + str(device_id))
            if uris:
                self.spotify.start_playback(device_id=device_id, uris=uris)
            elif context_uri:
                self.spotify.start_playback(device_id=device_id, context_uri=context_uri, offset=offset)
            else:
                self.spotify.start_playback(device_id=device_id)
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]Spotify Connect play error:[/red] {e}")

    def transfer_playback(self, device_id=None, force_play = False):
        if self.spotify is None:
            return
        self.flexprint('SpotifyConnect => transfer_playback with device_id: ' + str(device_id))
        if device_id is not None:
            try:
                self.spotify.transfer_playback(device_id = device_id, force_play = force_play)
            except Exception as e:
                self.flexprint("Spotify Connect transfer_playback error: " + str(e))
    
    def pause(self, device_id=None):
        if self.spotify is None:
            return
        self.flexprint('SpotifyConnect => pause with device_id: ' + str(device_id))
        try:
            self.spotify.pause_playback(device_id=device_id)
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]Spotify Connect pause error:[/red] {e}")

    def next(self, device_id=None):
        if self.spotify is None:
            return
        self.flexprint('SpotifyConnect => next with device_id: ' + str(device_id))
        try:
            self.spotify.next_track(device_id=device_id)
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]Spotify Connect next error:[/red] {e}")

    def previous(self, device_id=None):
        if self.spotify is None:
            return
        self.flexprint('SpotifyConnect => previous with device_id: ' + str(device_id))
        try:
            self.spotify.previous_track(device_id=device_id)
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]Spotify Connect previous error:[/red] {e}")

    def set_volume(self, volume_percent, device_id=None):
        # volume_percent: 0–100
        if self.spotify is None:
            return
        self.flexprint('SpotifyConnect => set volume with ' + str(volume_percent) + ' percent and device_id: ' + str(device_id))
        try:
            volume_percent = max(0, min(100, int(volume_percent)))
            self.spotify.volume(volume_percent, device_id=device_id)
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]Spotify Connect set volume error:[/red] {e}")

    # Shuffle / Repeat
    def shuffle(self, state=True, device_id=None):
        if self.spotify is None:
            return
        self.flexprint('SpotifyConnect => shuffle with state: ' + str(state) + ' and device_id: ' + str(device_id))
        try:
            self.spotify.shuffle(state, device_id=device_id)
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]Spotify Connect shuffle error:[/red] {e}")

    def repeat(self, mode="context", device_id=None):
        # mode: 'off', 'track' or 'context'
        if self.spotify is None:
            return
        self.flexprint('SpotifyConnect => repeat with mode: ' + str(mode) + ' and device_id: ' + str(device_id))
        try:
            self.spotify.repeat(mode, device_id=device_id)
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]Spotify Connect repeat error:[/red] {e}")

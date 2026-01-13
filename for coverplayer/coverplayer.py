#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# CoverPlayer Class - display roon, spotify and apple music playout informations and cover art on 720x720px Pimoroni HyperPixel Square 4.0 LCD matrix display
# Roonmatrix extension class
# version 1.2.0, date: 06.12.2025
#
# show what is playing on roon zones and via webservers on Spotify and Apple Music
#
# © Stephan Wilhelm, Bielefeld, Germany, coded @ 2025
#
# copy to /home/coverplayer/FTP
#
# icon images loaded from /home/coverplayer/FTP/icons
# fallback image loaded from /home/coverplayer/FTP/cover_fallback.png
# logs saved to /home/coverplayer/FTP/logs

from tkinter import Tk, Label, Button, Frame, Canvas, font as tkFont, NORMAL, DISABLED
from PIL import Image, ImageTk, ImageDraw, ImageFont
import queue
import threading
import requests
from io import BytesIO
from os import path, system
import time
import subprocess
from datetime import timedelta
from threading import Timer
from rich import print
import sys
import logging
import freetype
import asyncio
from aiohttp import ClientSession, ClientTimeout, ClientConnectorError
from unidecode import unidecode

class Coverplayer:
    _instance = None
    _queue = queue.Queue()

    def flexprint(self, str, objStr = None):
        if self.log is True:
            if objStr is None:
                if sys.stdout.isatty() or self.logger is None:
                    print(str) 
                else:
                    self.logger.info(str)
            else:
                if sys.stdout.isatty() or self.logger is None:
                    print(str, objStr)
                else:
                    self.logger.info(f"{str} {objStr}")

    def flexprint_list(self, mylist):
        if self.searchlog is True:
            for item in mylist:
                self.flexprint(str(item))
  
    @classmethod
    def set_keyboard_codes(cls, keyb_list, alternative_layout):
        cls._ensure_running()
        cls._queue.put(('set_keyboard_codes', keyb_list, alternative_layout, None, None, None, None, None, None, None, None, None, None, None, None, None))

    @classmethod
    def config(cls, lang, webserver_url_request_timeout, display_auto_wakeup):
        cls._ensure_running()
        cls._queue.put(('config', lang, webserver_url_request_timeout, display_auto_wakeup, None, None, None, None, None, None, None, None, None, None, None, None))

    @classmethod
    def disable_spotify(cls, disabled):
        cls._ensure_running()
        cls._queue.put(('disable_spotify', disabled, None, None, None, None, None, None, None, None, None, None, None, None, None, None))

    @classmethod
    def disable_applemusic(cls, disabled):
        cls._ensure_running()
        cls._queue.put(('disable_applemusic', disabled, None, None, None, None, None, None, None, None, None, None, None, None, None, None))

    @classmethod
    def vkeyb_error_message(cls, message):
        cls._ensure_running()
        cls._queue.put(('vkeyb_error_message', message, None, None, None, None, None, None, None, None, None, None, None, None, None, None))

    @classmethod
    def itemlist_error_message(cls, message):
        cls._ensure_running()
        cls._queue.put(('itemlist_error_message', message, None, None, None, None, None, None, None, None, None, None, None, None, None, None))

    @classmethod
    def update(cls, playpos, playlen, path_or_url, is_playing, sourcetype, is_radio, shuffle_on, repeat_on, track_id, text = [], buttons = None, zone_callback = None, control_callback = None, search_callback = None, itemclick_callback = None):
        cls._ensure_running()
        cls._queue.put(('update', playpos, playlen, path_or_url, is_playing, sourcetype, is_radio, shuffle_on, repeat_on, track_id, text, buttons or [], zone_callback, control_callback, search_callback, itemclick_callback))

    @classmethod
    def setpos(cls, playpos, playlen, path_or_url, is_playing, sourcetype, is_radio, shuffle_on, repeat_on, track_id, text = []):
        cls._ensure_running()
        cls._queue.put(('setpos', playpos, playlen, path_or_url, is_playing, sourcetype, is_radio, shuffle_on, repeat_on, track_id, text, None, None, None, None, None))

    @classmethod
    def setZones(cls, buttons, text, zone_callback):
        cls._ensure_running()
        cls._queue.put(('setZones', None, None, None, None, None, None, None, None, None, text, buttons or [], zone_callback, None, None, None))

    @classmethod
    def _ensure_running(cls):
        if cls._instance is None:
            cls._instance = cls()
            threading.Thread(target = cls._instance._gui_loop, daemon = True).start()

    @classmethod
    def _wrap_text(cls, text, font, max_width):
        """wraps text if its too long."""
        lines = []
        
        try:
            words = text.split()
            current_line = ""

            for word in words:
                test_line = current_line + " " + word if current_line else word
                test_width, _ = ImageDraw.Draw(Image.new('RGB', (1, 1))).textsize(test_line, font)

                if test_width <= max_width:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
        
            if current_line:
                lines.append(current_line)
        except Exception as e:
            if cls.errorlog is True: cls.flexprint('[red]wrap text error: ' + str(e) + '[/red]')
        return lines

    @classmethod
    def _load_image(cls, obj, errorlog, debug, log, lang, flexprint, maxpx, paused, icon_path, fonts, faces, font_size, webserver_url_request_timeout, path_or_url = None, text = None):
        font = fonts["latin"]

        def get_font_for_char(ch):
            try:
                font_order = ["latin", "cjk", "emoji"]
                codepoint = ord(ch)

                for key in font_order:
                    face = faces[key]
                    if face.get_char_index(codepoint) != 0:  # Glyph exist
                        return fonts[key]
            except Exception as e:
                if errorlog is True: flexprint('[red]get font for char error: ' + str(e) + '[/red]')
            return fonts["latin"]

        def convert_special_chars(str):
            try:
                return unidecode(str).encode("ascii", errors="ignore").decode()
            except Exception as e:
                if errorlog is True: flexprint('[red]convert special chars error: ' + str(e) + '[/red]')

        def get_right_font(text):
            count_latin = 0
            count_cjk = 0
            count_emoji = 0
            notfound = 0
            notfound_flag = False
            try:
                for ch in text:
                    found = False
                    font = get_font_for_char(ch)
                    if font == fonts["latin"]:
                        count_latin += 1
                        found = True
                    if font == fonts["cjk"]:
                        count_cjk += 1
                        found = True
                    if font == fonts["emoji"]:
                        count_emoji += 1
                        found = True
                    if found == False:
                        notfound += 1                    
                    
                if debug is True: flexprint('latin: ' + str(count_latin) + ', cjk: ' + str(count_cjk) + ', emoji: ' + str(count_emoji) + ', notfound: ' + str(notfound) + ' ('+text+')')
                if notfound >= count_latin and notfound >= count_cjk and notfound >= count_emoji:
                    notfound_flag = True
                if count_cjk >= count_latin and count_cjk >= count_emoji and count_cjk >= notfound:
                    return [fonts["cjk"], notfound_flag]
                if count_emoji >= count_latin and count_emoji >= count_cjk and count_emoji >= notfound:
                    return [fonts["emoji"], notfound_flag]
            except Exception as e:
                if errorlog is True: flexprint('[red]get right font error: ' + str(e) + '[/red]')
            return [fonts["latin"], notfound_flag]

        async def fetch_url(session, reqobj):
            # Helper function to fetch a single URL asynchronously
            try:
                name = reqobj['name']
                url = reqobj['url']
                async with session.get(url) as response:
                    content = await response.read()
                    return {
                        'url': url,
                        'name': name,
                        'status': response.status,
                        'length': len(content),
                        'content': content
                    }
            except ClientConnectorError as e:
                if errorlog is True: flexprint('aiohttp.ClientConnectorError', str(e))
                return {
                    'url': url,
                    'name': name,
                    'error': str(e)
                }
            except Exception as e:
                return {
                    'url': url,
                    'name': name,
                    'error': str(e)
                }

        async def async_web_requests(requestlist, get_head, timeout, callback):
            # Non-blocking implementation that fetches URLs concurrently
            timeout_obj = ClientTimeout(total = timeout)
            async with ClientSession(timeout = timeout_obj) as session:
                if get_head:
                    tasks = [asyncio.create_task(head_url(session, reqobj)) for reqobj in requestlist]
                else:
                    tasks = [asyncio.create_task(fetch_url(session, reqobj)) for reqobj in requestlist]

                for t in tasks:
                    t.add_done_callback(lambda fut: callback(fut.result()))

                return await asyncio.gather(*tasks)

        def prepare_image(img):
            try:
                img = img.resize((maxpx, maxpx), Image.ANTIALIAS)
            
                if paused is True:
                    canvas = Image.new("RGB", (maxpx,maxpx))
                    mask   = Image.new('L',   (maxpx,maxpx))
                    canvasDraw = ImageDraw.Draw(canvas)
                    maskDraw   = ImageDraw.Draw(mask)
                    canvasDraw.rectangle((0,0,maxpx - 1,maxpx - 1), 'white')
                    maskDraw.rectangle((0,0,maxpx - 1,maxpx - 1), 160)
                    img.paste(canvas, mask)
                    size = round(maxpx / 5)
                    icon_img = Image.open(icon_path)
                    icon_img = icon_img.resize((size, size), Image.ANTIALIAS)
                    pos = round((maxpx - size) / 2)
                    img.paste(icon_img, (pos, pos), mask = icon_img)

                img = img.convert("RGBA") # convert img to RGBA mode
                draw = ImageDraw.Draw(img)

                if text:
                    line_space = 5

                    max_width = img.width - 40  # max width of text
                    lines_all_items = 0
                
                    for text_part in text:
                        sep = text_part.split(':')
                        props = get_right_font(sep[1].strip() if len(sep) > 1 else text_part)
                        font = props[0]
                        notfound = props[1]
                        if notfound is True:
                            text_part = convert_special_chars(text_part)                
                        lines = cls._wrap_text(text_part, font, max_width)
                        lines_all_items += len(lines)
                    
                    border_space = 20
                    text_x = border_space
                    text_y = img.height - border_space - lines_all_items * (font_size + line_space)
                
                    background = (0, 0, 0, 255)  # RGB + Alpha (0-255)
                
                    for text_part in text:
                        sep = text_part.split(':')
                        props = get_right_font(sep[1].strip() if len(sep) > 1 else text_part)
                        font = props[0]
                        notfound = props[1]
                        if notfound is True:
                            lines = cls._wrap_text(convert_special_chars(text_part), font, max_width)
                        else:
                            lines = cls._wrap_text(text_part, font, max_width)
                        for line in lines:
                            text_width, text_height = draw.textsize(line, font = font)
                            try:
                                draw.rectangle([text_x - 5, text_y - line_space, text_x + text_width + 5, text_y + text_height + line_space], fill = background)
                            except Exception as e:
                                try:
                                    flexprint('=> draw.rectangle fallback for grayscale image')
                                    draw.rectangle([text_x - 5, text_y - line_space, text_x + text_width + 5, text_y + text_height + line_space], fill = 0) # fallback for grayscale images (not true color)
                                except Exception as e:
                                    if errorlog is True: flexprint('draw.rectangle error: ' + str(e))
                            draw.text((text_x, text_y), line, font = font, fill = "white")
                            text_y += text_height + line_space  # line spacing

                image = ImageTk.PhotoImage(img)
                if image:
                    obj.config(image = image)
                    obj.image = image
                else:
                    obj.config(text = lang['image_notfound'].title(), image = "")
            except Exception as e:
                if errorlog is True: flexprint('prepare image error: ' + str(e))

        def async_web_requests_with_timing(requestlist, callback):
            req_start_time = time.time()
            async_results = asyncio.run(async_web_requests(requestlist, False, webserver_url_request_timeout, callback))
            req_end_time = time.time()
            req_time = req_end_time - req_start_time

            if debug is True:
                flexprint(f"async_web_requests results ({req_time:.2f} seconds):", async_results)
            else:
                flexprint(f"async_web_requests time: ({req_time:.2f} seconds)")

            if async_results is not None and isinstance(async_results, list):
                for idx,data in enumerate(async_results,1):     
                    if 'status' in data: flexprint('[green]Webserver ' + data['name']  + ' with status ' + str(data['status']) + '[/green]')
                    if (len(async_results) == 0 or 'error' in data):
                        err = data['error'] if 'error' in data else ''
                        if err == '' and req_time >= webserver_url_request_timeout:
                            err = 'timeout'
                        if err == '' and len(async_results) == 0:
                            err = 'empty result'
                        flexprint('[red]Webserver ' + data['name']  + ' with error: ' + err + '[/red]')
            else:
                if errorlog is True: flexprint('[red]async_web_requests: lost response[/red]')
                async_results = [] 

            return async_results

        try:
            if path_or_url is None or path_or_url == '':
            	path_or_url = path.dirname(__file__) + '/cover_fallback.png'
            if path_or_url.startswith("http"):
                requestlist = [{'name':'imageSource','url':path_or_url}]
                
                def image_callback(async_web_response):
                    if async_web_response is not None and 'error' not in async_web_response:
                        flexprint('async_web_response (image) => len: ' + str(async_web_response['length'] if 'length' in async_web_response else 'unknown'))
                        img = Image.open(BytesIO(async_web_response['content']))
                    else:
                        if errorlog is True: flexprint('coverplayer load_image request failed => take fallback image')
                        path_or_url = path.dirname(__file__) + '/cover_fallback.png'
                        img = Image.open(path_or_url)
                    if obj is not None:
                        prepare_image(img)
                        
                async_web_response = async_web_requests_with_timing(requestlist, image_callback)
                if len(async_web_response) > 0 and 'error' not in async_web_response[0]:
                    img = Image.open(BytesIO(async_web_response[0]['content']))
                else:
                    if errorlog is True: flexprint('coverplayer load_image request failed => take fallback image')
                    path_or_url = path.dirname(__file__) + '/cover_fallback.png'
                    img = Image.open(path_or_url)                        
            else:
                img = Image.open(path_or_url)
                if obj is not None:
                    prepare_image(img)
                
        except Exception as e:
            if errorlog is True: flexprint(f"[red]Error on image loading:[/red] {e}")
            return None

    def _gui_loop(self):
        self.errorlog = True 	# log errors
        self.debug = False   	# log debug messages (memory and variable information)
        self.searchlog = False 	# log search data
        self.log = True      	# log infos on or off

        try:
            self.maxpx_x = 720 # screen width in px
            self.maxpx_y = 720 # screen height in px
            self.logger = logging.getLogger('coverplayer')
            self.font_size = 24

            self.FONT_PATHS = {
                "latin": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "cjk": "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                "emoji": "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
            }
            self.fonts = {k: ImageFont.truetype(path, (109 if k=='emoji' else self.font_size)) for k, path in self.FONT_PATHS.items()}        
            self.faces = {k: freetype.Face(path) for k, path in self.FONT_PATHS.items()}

            self.root = Tk()
            self.root.focus_force()
            self.root.title("CoverImage")
            self.root.overrideredirect(True)
            self.root.geometry(str(self.maxpx_x) + 'x' + str(self.maxpx_y) + '+0+0')
            self.root.config(cursor="none")
            self.scriptpath = path.dirname(__file__) + '/'
            self.last_screen_on = time.time()
            self.just_woke_up = False
            self.wake_time = 0
            self._check_display()

            self.label = Label(self.root)
            self.label.pack(fill = "both", expand = True)
            self.label.bind("<Button-1>", self._on_click_start)
            self.label.bind("<ButtonRelease-1>", self._on_click_end)

            self.autoclose_in_seconds = 30
            self.overlay_height = self.maxpx_y
            self.overlay_relheight = 1
            self.ctrl_btn_bgcolor = "white"	# background color of control buttons
            self.pending_btn_bgcolor = '#CCCCCC' # background color of control buttons in pending status
            self.overlay_bgcolor = "#222222"	# background color of control overlay
            self.btn_small_bgcolor = "#222222"	# background color of small buttons
            self.pending_btn_small_bgcolor = '#303030' # background color of small buttons in pending state
            self.btn_disabled_color = "#555555"	# background color of disabled button
            self.buttonFont = tkFont.Font(family='Noto Sans Mono', size=15, weight=tkFont.NORMAL)
            self.button_highlight_color = '#80ed99'

            # button size in px (screensize is 72mm x 72mm for 720px x 720px => 10px / mm on screen)
            self.zone_button_height = 91
            self.control_button_height = 90
            self.extra_space_height = 50
            self.progressbar_width_std = self.maxpx_x - 240
            self.progressbar_width_disabled = self.maxpx_x - 186
            self.playlen_pos_std = self.maxpx_x - 110
            self.playlen_pos_disabled = self.maxpx_x - 56

            self.debug = False
            self.spotify_disabled = False
            self.applemusic_disabled = False
            self.display_auto_wakeup = False
            self.webserver_url_request_timeout = 8
            self.count = 0
            self.shuffle_btn = None
            self.repeat_btn = None
            self.backward_btn = None
            self.play_btn = None
            self.forward_btn = None
            self.overlay = None
            self.overlay_timer = None
            self.in_menu_mode = False
            self.buttons = []
            self.playpos = -1
            self.playlen = -1
            self.playpos_next = None
            self.playpos_text = None
            self.playlen_text = None
            self.playlen_canvas = None
            self.canvas = None
            self.canvas_clear = None
            self.text = []
            self.zone = None
            self.zone_off = True
            self.spotify_devicelist = []
            self.missing_zone = False
            self.stopped_zone = False
            self.zone_btn = {}
            self.path = ''
            self.zone_callback = None
            self.control_callback = None
            self.search = ''
            self.searchtype = ''
            self.search_callback = None
            self.itemclick_callback = None
            self.is_playing = True
            self.sourcetype = 'local'
            self.alternative_layout = False
            self.is_radio = False # true: is applemusic radio stream
            self.shuffle_on = False
            self.repeat_on = False
            self.track_id = ''
            self.control_icons = {}
            self._load_control_icons()
            self.tracklist_btn = None

            from vkeyboard import VirtualKeyboard
            self.vkeyb = VirtualKeyboard(self.log,self.maxpx_x,self.maxpx_y)

            from itemlist import ItemList
            self.itemlistclass = ItemList(self.log,self.maxpx_x,self.maxpx_y)

            self.root.after(1000, self.update_playpos)

            self._poll_queue()
            self.root.mainloop()
        except Exception as e:
            self.flexprint(f"[red]gui loop error:[/red] {e}")

    def _check_display(self):
        try:
            screen_on = self.is_screen_on()
            now = time.time()
            if self.debug is True: self.flexprint('[bold red]check_display[/bold red] => screen_on: ' + str(screen_on))

            if screen_on:
                # If the display has just been switched on
                if now - self.last_screen_on > 10:
                    self.flexprint("Display has been reactivated")
                    self.just_woke_up = True
                    self.root.after(1000, self._reset_wake_flag)
                    self.wake_time = now  # keep track of time
                self.last_screen_on = now
            else:
                self._reset_wake_flag()  # to be on the safe side
            self.root.after(1000, self._check_display)
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]check display error:[/red] {e}")

    def _reset_wake_flag(self):
        self.just_woke_up = False
    
    def is_screen_on(self):
        try:
            output = subprocess.check_output(['xset', '-q']).decode()
            for line in output.splitlines():
                if "Monitor is" in line:
                    return "On" in line
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]Error with xset:[/red] {e}")
        return False

    def _on_click_start(self, event):
        try:
            screen_on = self.is_screen_on()
            now = time.time()
            if self.debug is True: self.flexprint('[bold red]on touch[/bold red] => screen_on: ' + str(screen_on) + ', diff: ' + str(now - self.last_screen_on) + ', just_woke_up: ' + str(self.just_woke_up) + ', wake_time: ' + str(self.wake_time))
            if (screen_on is True and now - self.last_screen_on > 10) or (self.just_woke_up and now - self.wake_time < 1):
                self.flexprint("Touch ignored after wake-up.")
                self.last_screen_on = now
                return

            # After the first action, do not block again
            self._reset_wake_flag()

            self._press_after_id = self.root.after(5000, self._on_long_press)

            if self.in_menu_mode is True:
                if event.y < int(self.root.winfo_height() * (1 - self.overlay_relheight)):
                    self._hide_overlay()
            else:
                self._show_overlay()
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]on click start error:[/red] {e}")

    def _on_click_end(self, event):
        try:
            if hasattr(self, "_press_after_id"):
                self.root.after_cancel(self._press_after_id)
                del self._press_after_id
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]on click end error:[/red] {e}")

    def _on_long_press(self):
        self.flexprint("long press – close coverplayer app.")
        try:
            self.root.destroy()
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]on long press error:[/red] {e}")

    def _load_control_icons(self):
        from tkinter import PhotoImage
        try:
            self.control_icons = {
                "play": PhotoImage(file = self.scriptpath + "icons/play.png"),
                "pause": PhotoImage(file = self.scriptpath + "icons/pause.png"),
                "forward": PhotoImage(file = self.scriptpath + "icons/forward.png"),
                "backward": PhotoImage(file = self.scriptpath + "icons/backward.png"),
                "shuffle_on": PhotoImage(file = self.scriptpath + "icons/shuffle-on.png"),
                "shuffle_off": PhotoImage(file = self.scriptpath + "icons/shuffle-off.png"),
                "stream_on": PhotoImage(file = self.scriptpath + "icons/stream-on.png"),
                "stream_off": PhotoImage(file = self.scriptpath + "icons/stream-off.png"),
                "repeat_on": PhotoImage(file = self.scriptpath + "icons/repeat-on.png"),
                "repeat_off": PhotoImage(file = self.scriptpath + "icons/repeat-off.png"),
                "close": PhotoImage(file = self.scriptpath + "icons/close.png"),
                "keyb": PhotoImage(file = self.scriptpath + "icons/keyb.png"),
                "tracklist": PhotoImage(file = self.scriptpath + "icons/tracklist.png"),
                "applemusic": PhotoImage(file = self.scriptpath + "icons/applemusic.png"),
                "spotify": PhotoImage(file = self.scriptpath + "icons/spotify.png"),
                "spotify-connect": PhotoImage(file = self.scriptpath + "icons/spotify-connect.png"),
                "roon": PhotoImage(file = self.scriptpath + "icons/roon.png"),
        }
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]Icon loading error:[/red] {e}")

    def _start_overlay_timer(self):
        try:
            self._cancel_overlay_timer()
            self.overlay_timer = self.root.after(self.autoclose_in_seconds * 1000, self._hide_overlay) # disable this line to prevent auto-close of overlay
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]start overlay timer error:[/red] {e}")

    def _cancel_overlay_timer(self):
        try:
            if self.overlay_timer:
                self.root.after_cancel(self.overlay_timer)
                self.overlay_timer = None
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]cancel overlay timer error:[/red] {e}")

    def switch_small_button_state(self, btn, command, enabled):
        try:
            if self.in_menu_mode is True and btn is not None:
                if enabled is True:
                    btn.config(command = command, bg = self.btn_small_bgcolor, activebackground = self.btn_small_bgcolor)
                else:
                    btn.config(command = lambda: None, bg = self.btn_disabled_color, activebackground = self.btn_disabled_color)
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]switch small button state error:[/red] {e}")

    def switch_playcontrol_button_state(self, btn, command, enabled):
        try:
            if self.in_menu_mode is True and btn is not None:
                if enabled is True:
                    btn.config(command = command, bg = self.ctrl_btn_bgcolor, activebackground = self.ctrl_btn_bgcolor)
                else:
                    btn.config(command = lambda: None, bg = self.btn_disabled_color, activebackground = self.btn_disabled_color)
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]switch playcontrol button state error:[/red] {e}")

    def switch_button_state(self, btn, enabled):
        try:
            if self.in_menu_mode is True and btn is not None:
                if enabled is True:
                    btn.config(state=NORMAL, bg = self.overlay_bgcolor)
                else:
                    btn.config(state=DISABLED, bg = self.btn_disabled_color)
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]switch button state error:[/red] {e}")

    def get_zonetype(self):
        if self.zone is None:
            return ''
        try:
            return (self.zone.split('-')[1].strip()) if (len(self.zone.split('-'))==2 and (self.zone.endswith('-Apple Music') or self.zone.endswith('-Spotify') or self.zone.endswith('-SpotifyConnect'))) else 'Roon'
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]get zonetype error:[/red] {e}")
            return ''

    def set_search_button(self):
        try:
            if self.in_menu_mode is True and self.keyb_btn is not None:
                icon_enabled = self.zone is not None
                zonetype = self.get_zonetype()
                if zonetype.startswith('Spotify') and self.spotify_disabled is True:
                    icon_enabled = False
                if zonetype == 'Apple Music' and self.applemusic_disabled is True:
                    icon_enabled = False
                if zonetype == 'Roon' and self.zone not in self.buttons:
                    icon_enabled = False
                self.switch_button_state(self.keyb_btn, icon_enabled)
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]set search button error:[/red] {e}")

    def set_tracklist_button(self, zone):
        try:
            if self.in_menu_mode is True and self.tracklist_btn is not None:
                icon_enabled = self.zone is not None and zone == self.zone
                zonetype = self.get_zonetype()
                if (zonetype.startswith('Spotify') or zone.startswith('Spotify')) and self.spotify_disabled is True:
                    icon_enabled = False
                if (zonetype == 'Apple Music' or zone == 'Apple Music') and self.applemusic_disabled is True:
                    icon_enabled = False
                self.switch_button_state(self.tracklist_btn, icon_enabled)
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]set tracklist button error:[/red] {e}")

    def draw_progressbar(self, playpos, playlen):
        try:
            if self.canvas is not None:
                self.canvas.config(width = self.progressbar_width_std)
            else:
                self.canvas=Canvas(self.overlay, width = self.progressbar_width_std, height = 5)
                self.canvas.place(x = 120, y = self.overlay_height - self.control_button_height - self.extra_space_height + 15)
            self.canvas.create_line(0, 0, self.progressbar_width_std,0, fill = "white", width = 14)
            if playpos > 0:
                w = (self.progressbar_width_std - 3) / ((playlen / playpos) if playlen is not None and playlen > 0 else 1)
            else:
                w = 0
            self.canvas.create_line(1, 1, w, 1, fill = "green", width = 12)
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]draw progressbar error:[/red] {e}")

    def get_sourcetype_icon(self, label):
        if label.endswith('-apple music'):
            return 'applemusic'
        elif label.endswith('-spotifyconnect'):
            return 'spotify-connect'
        elif label.endswith('-spotify'):
            return 'spotify'
        else:
            return 'roon'

    def get_zonebutton_label_without_type(self, label):
        return label.replace('-Apple Music', '').replace('-SpotifyConnect', '').replace('-Spotify', '')
    
    def _show_overlay(self):
        try:
            self._start_overlay_timer()
        
            max_per_row = 3		# max 3 buttons per row

            ctrl_btn_ipad = 20			# inner padding in px of control buttons
            corner_btn_size = 88		# button size in px of shuffle and close button in the bottom corners
        
            total = len(self.buttons)
            rows = (total + max_per_row - 1) // max_per_row
            self.overlay_height = rows * self.zone_button_height + self.extra_space_height + self.control_button_height
            self.overlay_relheight = 1/self.maxpx_y*self.overlay_height

            self.in_menu_mode = True
            self.overlay = Frame(self.root, bg = self.overlay_bgcolor)
            self.overlay.grid_columnconfigure(0, weight = 1)
            self.overlay.place(relx = 0, rely = 1 - self.overlay_relheight, relwidth = 1, relheight = self.overlay_relheight)

            # container for zone buttons (top)
            zone_frame = Frame(self.overlay, bg = self.overlay_bgcolor)
            zone_frame.pack(side = 'top', fill = 'x')
            zone_frame.place(relx = 0, rely = 0, relwidth = 1, height = rows * self.zone_button_height)

            # divide columns for upper buttons (consider max_per_row)
            for col in range(max_per_row):
                zone_frame.grid_columnconfigure(col, weight = 1)

            # zone buttons (top)
            wraplength = int(self.maxpx_x / 3) - 80
            for idx, label in enumerate(self.buttons):
                row = idx // max_per_row
                col = idx % max_per_row
                icon_key = self.get_sourcetype_icon(label.lower())
                icon = self.control_icons[icon_key]
                text = self.get_zonebutton_label_without_type(label)
                self.zone_btn[label] = Button(zone_frame, text = text, image=icon, anchor="w", justify="left", compound="left", wraplength = wraplength, bg = self.button_highlight_color if (self.zone is not None and label == self.zone) else None, font = self.buttonFont, command = lambda l = label: self._on_button_click(l), padx = 4, pady = 5, height = 56)
                self.zone_btn[label].grid(row = row, column = col, padx = 10, pady = 10, sticky = "ew")

            # container for play control buttons (bottom)
            control_frame = Frame(self.overlay, bg = self.overlay_bgcolor)
            control_frame.grid_columnconfigure(0, weight = 1)
            control_frame.pack(side = 'bottom', anchor = 'center')

            # control buttons close together
            self.backward_btn = Button(control_frame, image = self.control_icons["backward"], bg = self.ctrl_btn_bgcolor, activebackground = self.ctrl_btn_bgcolor, bd = 0, command = lambda: self._control("backward"), takefocus = 0)
            self.backward_btn.pack(side = "left", padx = (5, 5), ipadx = ctrl_btn_ipad, ipady = ctrl_btn_ipad)
            icon = self.control_icons["pause"] if self.is_playing else self.control_icons["play"]
            self.play_btn = Button(control_frame, image = icon, bg = self.ctrl_btn_bgcolor, takefocus = 0, activebackground = self.ctrl_btn_bgcolor, bd = 0, command = self._toggle_play)
            self.play_btn.pack(side = "left", padx = 5, ipadx = ctrl_btn_ipad, ipady = ctrl_btn_ipad)
            self.forward_btn = Button(control_frame, image = self.control_icons["forward"], bg = self.ctrl_btn_bgcolor, activebackground = self.ctrl_btn_bgcolor, bd = 0, command = lambda: self._control("forward"), takefocus = 0)
            self.forward_btn.pack(side = "left", padx = 5, ipadx = ctrl_btn_ipad, ipady = ctrl_btn_ipad)
            self.set_play_control()

            # shuffle button at the bottom left
            icon = self.control_icons["shuffle_on"] if self.shuffle_on else self.control_icons["shuffle_off"]
            switch_enabled = self.is_radio is False and self.playlen is not None and self.playlen!=-1
            bg = self.btn_small_bgcolor if switch_enabled else self.btn_disabled_color
            self.shuffle_btn = Button(self.overlay, image = icon, bg=bg, bd = 0, command = self._toggle_shuffle if switch_enabled else lambda: None, takefocus = 0, activebackground = bg, height = corner_btn_size, width = corner_btn_size)
            self.shuffle_btn.place(relx = 0.0, rely = 1.0, anchor = "sw", x = 0, y = 0)

		    # repeat button at the bottom left
            icon = self.control_icons["repeat_on"] if (self.repeat_on and self.is_radio is False) else self.control_icons["repeat_off"]
            self.repeat_btn = Button(self.overlay, image = icon, bg = bg, bd = 0, command = self._toggle_repeat if switch_enabled else lambda: None, takefocus = 0, activebackground = bg, height = corner_btn_size, width = corner_btn_size)
            self.repeat_btn.place(relx = 0.14, rely = 1.0, anchor = "sw", x = 0, y = 0)

            # keyboard button at the bottom right
            icon = self.control_icons["keyb"]
            self.keyb_btn = Button(self.overlay, image = icon, bg = self.btn_small_bgcolor, bd = 0, state=DISABLED, command = lambda: self._open_keyb('search'), takefocus = 0, activebackground = self.btn_small_bgcolor, height = corner_btn_size, width = corner_btn_size)
            self.keyb_btn.place(relx = 0.86, rely = 1.0, anchor = "se", x = 0, y = 0)
            self.set_search_button()

            # tracklist button at the bottom right        
            icon = self.control_icons["tracklist"]
            self.tracklist_btn = Button(self.overlay, image = icon, bg = self.btn_small_bgcolor, bd = 0, state=DISABLED, command = lambda: self._open_keyb('tracklist'), takefocus = 0, activebackground = self.btn_small_bgcolor, height = corner_btn_size, width = corner_btn_size)
            self.tracklist_btn.place(relx = 1.0, rely = 1.0, anchor = "se", x = 0, y = 0)
            if self.text is not None and len(self.text) > 3:
                zone = self.text[0].split(':')[1].strip()
                self.set_tracklist_button(zone)
            else:
                self.switch_button_state(self.tracklist_btn, False)

            # back button at the bottom right
            #back_btn = Button(self.overlay, image = self.control_icons["close"], bg = self.overlay_bgcolor, bd = 0, command = self._hide_overlay, takefocus=False, height = corner_btn_size, width = corner_btn_size)
            #back_btn.place(relx = 1.0, rely = 1.0, anchor = "se", x = 0, y = 0)
        
            if self.playpos is not None and self.playpos != -1:
                self.playpos_text = Label(self.overlay, text = timedelta(seconds=self.playpos), bg = self.overlay_bgcolor, font = "Arial 20 bold", fg = 'white')
                self.playpos_text.place(x = 10, y = self.overlay_height - self.control_button_height - self.extra_space_height)
                self.draw_progressbar(self.playpos, self.playlen)

            if self.playlen is not None and self.playlen > 0:
                self.playlen_text = Label(self.overlay, text = timedelta(seconds=self.playlen), bg = self.overlay_bgcolor, font = "Arial 20 bold", fg = 'white')
                self.playlen_text.place(x = self.playlen_pos_std, y = self.overlay_height - self.control_button_height - self.extra_space_height)
            else:
                if self.playpos is not None and self.playpos != -1:
                    self.canvas=Canvas(self.overlay, width = self.progressbar_width_disabled, height = 5)
                    self.canvas.place(x = 120, y = self.overlay_height - self.control_button_height - self.extra_space_height + 15)
                    self.canvas.create_line(0, 0, self.progressbar_width_disabled,0, fill = "white", width = 14)
                    self.canvas.create_line(1, 1, self.progressbar_width_disabled - 3, 1, fill = "green", width = 12)
                    playlen_canvas = Canvas(self.overlay, width = 40, height = 36, bg = self.overlay_bgcolor, bd = 0, highlightthickness = 0)
                    playlen_canvas.place(x = self.playlen_pos_disabled, y = self.overlay_height - self.control_button_height - self.extra_space_height)   
                    txtid = playlen_canvas.create_text(0, -15, text='\u221E', fill="white", font=('Arial', 40), anchor='nw')             
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]show overlay error:[/red] {e}")

    def update_playpos(self):
        try:
            switch_enabled = self.playlen is not None and self.playlen!=-1
            self.root.after(1000, self.update_playpos)
            if self.playpos_next != None:
                self.playpos = self.playpos_next
                self.playpos_next = None
            if self.missing_zone is False and self.stopped_zone is False and self.is_playing is True and self.playpos is not None and self.playpos != -1:
                if self.is_radio is False and (self.playlen is None or self.playpos < self.playlen):
                    self.playpos += 1
                if self.in_menu_mode is True:
                    if self.playpos_text is None:
                        self.playpos_text = Label(self.overlay, text = timedelta(seconds=self.playpos), bg = self.overlay_bgcolor, font = "Arial 20 bold", fg = 'white')
                    else:
                        self.playpos_text.config(text=timedelta(seconds=self.playpos))
                    self.playpos_text.place(x = 10, y = self.overlay_height - self.control_button_height - self.extra_space_height)
                    if self.canvas is None:
                        self.canvas=Canvas(self.overlay, width = self.progressbar_width_std if switch_enabled else self.progressbar_width_disabled, height = 5)
                        self.canvas.place(x = 120, y = self.overlay_height - self.control_button_height - self.extra_space_height + 15)
                    self.canvas.create_line(0, 0, self.progressbar_width_std if switch_enabled else self.progressbar_width_disabled,0, fill = "white", width = 14)
                    if self.playpos > 0:
                        w = ((self.progressbar_width_std if switch_enabled else self.progressbar_width_disabled) - 3) / ((self.playlen / self.playpos) if self.playlen is not None and self.playlen > 0 else 1)
                    else:
                        w = 0
                    self.canvas.create_line(1, 1, w, 1, fill = "green", width = 12)
            if self.debug is True:
                self.flexprint('CoverPlayer: classfunc update_playpos: ' + str(self.playpos))
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]update playpos error:[/red] {e}")

    def _control(self, action):
        try:
            self._start_overlay_timer()   
            self.flexprint('_control action: ' + str(action) + ', is_radio: ' + str(self.is_radio))
            if action == 'pause' or action == 'play':
                icon = self.control_icons['pause' if action=='play' else 'play']
                self.play_btn.config(image = icon, bg=self.pending_btn_bgcolor, activebackground=self.pending_btn_bgcolor)
            else:
                icon = self.control_icons[action]

            if action == 'backward':
                self.backward_btn.config(image = icon, bg=self.pending_btn_bgcolor, activebackground=self.pending_btn_bgcolor)

            if action == 'forward':
                self.forward_btn.config(image = icon, bg=self.pending_btn_bgcolor, activebackground=self.pending_btn_bgcolor)

            switch_enabled = self.is_radio is False and self.playlen is not None and self.playlen!=-1
            if switch_enabled and (action == 'shuffle_off' or action == 'shuffle_on'):
                bg = self.pending_btn_small_bgcolor if switch_enabled else self.btn_disabled_color
                self.shuffle_btn.config(image = icon, command = self._toggle_shuffle if switch_enabled else lambda: None, bg=bg, activebackground=bg)

            if switch_enabled and (action == 'repeat_off' or action == 'repeat_on'):
                bg = self.pending_btn_small_bgcolor if switch_enabled else self.btn_disabled_color
                self.repeat_btn.config(image = icon, command = self._toggle_repeat if switch_enabled else lambda: None, bg=bg, activebackground=bg)
        
            if self.control_callback:
                if self.is_radio is False or action == 'pause' or action == 'play':
                    stateupdate = self.control_callback(action)
                    self.flexprint('control_callback DONE')
                    is_playing = stateupdate[0]
                    shuffle_on = stateupdate[1]
                    repeat_on = stateupdate[2]
                    track_id = stateupdate[3]
                #self._set_playmode(is_playing)
                #self.is_playing = is_playing
                if action == 'backward':
                    self.backward_btn.config(image = icon, bg=self.ctrl_btn_bgcolor, activebackground=self.ctrl_btn_bgcolor)
                if action == 'forward':
                    self.forward_btn.config(image = icon, bg=self.ctrl_btn_bgcolor, activebackground=self.ctrl_btn_bgcolor)
                #self._set_shufflemode(shuffle_on, playlen)
                #self.shuffle_on = shuffle_on
                #self._set_repeatmode(repeat_on, playlen)
                #self.repeat_on = repeat_on
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]control error:[/red] {e}")

    def _toggle_play(self):
        try:
            self._start_overlay_timer()
            self._control("pause" if self.is_playing else "play")
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]toggle play error:[/red] {e}")

    def _set_playmode(self, mode):
        try:
            if self.in_menu_mode is True and self.play_btn is not None:
                icon = self.control_icons["pause"] if mode else self.control_icons["play"]
                self.play_btn.config(image = icon, bg=self.ctrl_btn_bgcolor, activebackground=self.ctrl_btn_bgcolor)
                self.flexprint('[bold red]CoverPlayer: set_playmode: '+ str(mode) + '[/bold red]')
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]set playmode error:[/red] {e}")

    def _toggle_shuffle(self):
        try:
            self._start_overlay_timer()
            self._control("shuffle_off" if (self.is_radio is True or self.shuffle_on) else "shuffle_on")
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]toggle shuffle error:[/red] {e}")

    def _set_shufflemode(self, mode, playlen):
        try:
            if self.in_menu_mode is True and self.shuffle_btn is not None:
                icon = self.control_icons["shuffle_on"] if (self.is_radio is False and mode is True) else self.control_icons["shuffle_off"]
                bg = self.btn_small_bgcolor if (self.is_radio is False and playlen is not None and playlen!=-1) else self.btn_disabled_color
                self.shuffle_btn.config(image = icon, bg=bg, activebackground=bg)
                self.flexprint('[bold red]CoverPlayer: set_shufflemode: '+ str(mode) + '[/bold red]')
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]set shufflemode error:[/red] {e}")

    def _toggle_repeat(self):
        try:
            self._start_overlay_timer()
            self._control("repeat_off" if (self.is_radio is True or self.repeat_on) else "repeat_on")
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]toggle repeat error:[/red] {e}")

    def _set_repeatmode(self, mode, playlen):
        try:
            if self.in_menu_mode is True and self.repeat_btn is not None:
                icon = self.control_icons["repeat_on"] if (self.is_radio is False and mode is True) else self.control_icons["repeat_off"]
                bg = self.btn_small_bgcolor if (self.is_radio is False and playlen is not None and playlen!=-1) else self.btn_disabled_color
                self.repeat_btn.config(image = icon, bg=bg, activebackground=bg)
                self.flexprint('[bold red]CoverPlayer: set_repeatmode: '+ str(mode) + '[/bold red]')
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]set repeatmode error:[/red] {e}")

    def _on_button_click(self, value):
        try:
            if value == self.zone and value.endswith('-SpotifyConnect'):
                self._open_keyb('spotify-devicelist')
            else:
                if self.zone_callback:
                    self.zone = value
                    self.zone_callback(value)

                    if self.in_menu_mode is True and self.tracklist_btn is not None:
                        if self.text is not None and len(self.text) > 3:
                            zone = self.text[0].split(':')[1].strip()
                            icon_enabled = self.zone is not None and zone == self.zone
                            self.switch_button_state(self.tracklist_btn, icon_enabled)
                        else:
                            self.switch_button_state(self.tracklist_btn, False)
                    if self.in_menu_mode is True and self.keyb_btn is not None:
                        icon_enabled = self.zone is not None
                        self.switch_button_state(self.keyb_btn, icon_enabled)

                self._hide_overlay()
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]on button_click error:[/red] {e}")

    def _hide_overlay(self):
        try:
            self._cancel_overlay_timer()
            if self.overlay:
                self.playpos_text = None
                self.playlen_text = None
                self.playlen_canvas = None
                if self.canvas is not None:
                    self.canvas.destroy()
                    self.canvas = None
                if self.canvas_clear is not None:
                    self.canvas_clear.destroy()
                    self.canvas_clear = None
                self.overlay.destroy()
                self.overlay = None
                self.in_menu_mode = False
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]hide overlay error:[/red] {e}")

    def close_keyb(self):
        try:
            self.flexprint('close_keyb')
            self.root.deiconify()
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]close keyb error:[/red] {e}")

    def close_list(self):
        try:
            self.root.deiconify()
            self._hide_overlay()
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]close list error:[/red] {e}")

    def unescape_quotes(self, str):
        return str.replace('\\"',"\"")

    def filter_list_to_unique_id(self, items):
        filtered_items = []
        idlist = []
        try:
            for item in items:
                if item['id'] not in idlist:
                    filtered_items.append(item)
                    idlist.append(item['id'])
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]filter list to unique id error:[/red] {e}")
        return filtered_items
    
    def on_search(self, is_stream, type, key):
        try:
            self.flexprint('coverplayer => on_search, zone: ' + str(self.zone) + ', is_stream:' + str(is_stream) + ', type: ' + str(type) + ', key: ' + str(key))
            if self.search_callback is not None and self.zone is not None:
                data = self.search_callback(is_stream, key, self.zone, type)
                if isinstance(data, str):
                    self.vkeyb.error_message(data)
                    return
                if len(data) > 0:
                    meta = data[0]
                    if self.searchlog is True: self.flexprint("coverplayer => on_search, meta:" + str(meta))
                    if 'zonetype' in meta and meta['zonetype']=='':
                        self.vkeyb.error_message(self.lang['Zone'] + ' ' + self.lang['inactive'].upper())
                        return
                    if meta['type'] == 'albums':
                        self.search = meta['artist']
                        albums = data[1]
                        if albums is not None and isinstance(albums, str) is False and len(albums) > 0:
                            if isinstance(albums[0], str) is True:
                                self.flexprint_list(albums)
                            else:
                                album_names = list(map(lambda obj: obj['name'], albums))
                                self.flexprint_list(album_names)
                            meta['label'] = self.lang['select_album'].title()
                            meta['listname'] = self.unescape_quotes(meta['artist'])
                            self._open_list(meta, albums)
                        elif albums is not None and isinstance(albums, str) is True:
                            self.vkeyb.error_message(albums)
                        else:
                            self.vkeyb.error_message(self.lang['notfound'].upper())
                    if meta['type'] == 'artists' and len(data) == 2:
                        self.search = meta['search']
                        artists = data[1]
                        if artists is not None and isinstance(artists, str) is False and len(artists) > 0:
                            self.flexprint_list(artists)
                            meta['label'] = self.lang['select_artist'].title()
                            meta['listname'] = None
                            self._open_list(meta, artists)
                        elif artists is not None and isinstance(artists, str) is True:
                            self.vkeyb.error_message(artists)
                        else:
                            self.vkeyb.error_message(self.lang['notfound'].upper())
                    if meta['type'] == 'genres' and len(data) == 2:
                        self.search = meta['search']
                        genres = data[1]
                        if genres is not None and isinstance(genres, str) is False and len(genres) > 0:
                            self.flexprint_list(genres)
                            meta['label'] = self.lang['select_genre'].title()
                            meta['listname'] = None
                            self._open_list(meta, genres)
                        elif genres is not None and isinstance(genres, str) is True:
                            self.vkeyb.error_message(genres)
                        else:
                            self.vkeyb.error_message(self.lang['notfound'].upper())
                    if meta['type'] == 'tracks' and len(data) == 2:
                        self.search = meta['search']
                        tracks = data[1]
                        if tracks is not None and isinstance(tracks, str) is False and len(tracks) > 0:
                            if meta['zonetype'] == 'Apple Music':
                                if is_stream is False:
                                    tracks = list(map(lambda name: {"name": (name.split('|')[0] + ' [' + name.split('|')[1] + ']') if len(name.split('|')) == 2 else name, "id": name.split('|')[0]}, tracks))
                                tracks = self.filter_list_to_unique_id(tracks)
                                if 'playlist' in meta:
                                    tracks.insert(0, {"name": self.lang['play_playlist'].title(), "id": "[FULLPLAYLIST]"})
                            self.flexprint_list(tracks)
                            meta['label'] = self.lang['select_track'].title()
                            meta['listname'] = self.unescape_quotes(meta['search'])
                            if self.searchlog is True: self.flexprint('coverplayer applemusic playlist tracks: ' + str(tracks))
                            self._open_list(meta, tracks)
                        elif tracks is not None and isinstance(tracks, str) is True:
                            self.vkeyb.error_message(tracks)
                        else:
                            self.vkeyb.error_message(self.lang['notfound'].upper())
                    if meta['type'] == 'playlists' and len(data) == 2:
                        self.search = meta['search']
                        playlists = data[1]
                        if playlists is not None and isinstance(playlists, str) is False and len(playlists) > 0:
                            self.flexprint_list(playlists)
                            meta['label'] = self.lang['select_playlist'].title()
                            meta['listname'] = None
                            if meta['zonetype']=='Apple Music' and meta['stream'] is True:
                                meta['playlists'] = playlists
                            self._open_list(meta, playlists)
                        elif playlists is not None and isinstance(playlists, str) is True:
                            self.vkeyb.error_message(playlists)
                        else:
                            self.vkeyb.error_message(self.lang['notfound'].upper())
                    if meta['type'] == 'radios' and len(data) == 2:
                        self.search = meta['search']
                        radios = data[1]
                        if radios is not None and isinstance(radios, str) is False and len(radios) > 0:
                            self.flexprint_list(radios)
                            meta['label'] = self.lang['select_radio'].title()
                            meta['listname'] = None
                            self._open_list(meta, radios)
                        elif radios is not None and isinstance(radios, str) is True:
                            self.vkeyb.error_message(radios)
                        else:
                            self.vkeyb.error_message(self.lang['notfound'].upper())
                    if meta['type'] == 'radio':
                        self.close_list()
            else:
                self.vkeyb.error_message(self.lang['Zone'] + ' ' + self.lang['inactive'].upper())
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]on search error:[/red] {e}")

    def on_itemclick(self, meta, name, id = None):
        try:
            self.flexprint('coverplayer => on_itemclick, meta: ' + str(meta) + ', name: ' + str(name) + ', id: ' + str(id) + ', zone: ' + self.zone)
            self.close_list()
            if self.itemclick_callback is not None:
                data = self.itemclick_callback(meta, self.search if (meta['type'] == 'albums' or meta['type']=='artistalbums' or meta['type']=='tracks') else name, id if (id is not None and id != '') else name, self.zone)
                if isinstance(data, str):
                    self.itemlistclass.error_message(data if data !='' else self.lang['unknown_error'])
                    return
                if self.searchlog is True: self.flexprint('coverplayer ==> itemclick_callback, data: ' + str(data))
                if data is not None and len(data) > 0:
                    result_type = data[0]
                    if result_type == 'spotify-devicelist':
                        self.search = data[1]
                        self.spotify_devicelist = data[2]
                        devicelist = list(map(lambda obj: {"name": obj['name'], "id": obj['id'], "is_active": obj['is_active']}, self.spotify_devicelist))
                        self._open_list(meta, devicelist)
                    if result_type == 'artist':
                        self.search = data[1]
                        meta['type'] = 'artistalbums'
                        meta['artist'] = self.search
                        meta['label'] = self.lang['select_album'].title()
                        self.on_itemclick(meta, 'albums', self.search)
                    if result_type == 'artists':
                        self.search = data[1]
                        artists = data[2]
                        if artists is not None and len(artists) > 0:
                            if isinstance(artists[0], str) is True:
                                self.flexprint_list(artists)
                            else:
                                artist_names = list(map(lambda obj: obj['name'], artists))
                                self.flexprint_list(artist_names)
                            meta['type'] = result_type
                            meta['genre'] = self.search
                            meta['genreId'] = id
                            meta['label'] = self.lang['genre'].title()
                            meta['listname'] = self.unescape_quotes(self.search)
                            if self.searchlog is True: self.flexprint('on_itemclick before _open_list (artists), meta: ' + str(meta))
                            self._open_list(meta, artists)
                        else:
                            self.itemlistclass.error_message(self.lang['notfound'].upper())
                    if result_type == 'albums':
                        self.search = data[1]
                        albums = data[2]
                        if albums is not None and len(albums) > 0:
                            if isinstance(albums[0], str) is True:
                                self.flexprint_list(albums)
                            else:
                                album_names = list(map(lambda obj: obj['name'], albums))
                                self.flexprint_list(album_names)
                            meta['type'] = result_type
                            meta['artist'] = self.search
                            meta['artistId'] = id
                            meta['label'] = self.lang['select_album'].title()
                            meta['listname'] = self.unescape_quotes(self.search)
                            if self.searchlog is True: self.flexprint('on_itemclick before _open_list (albums), meta: ' + str(meta))
                            self._open_list(meta, albums)
                        else:
                            self.itemlistclass.error_message(self.lang['notfound'].upper())
                    if self.searchlog is True: self.flexprint('#### coverplayer on_itemclick result_type: ' + result_type + ', meta: ' + str(meta))                 
                    if meta['type']!='playlists' and meta['type']!='tracks' and result_type == 'tracks':
                        self.search = data[1]
                        album = data[2]
                        tracks = data[3]
                        if self.searchlog is True: self.flexprint('coverplayer on_itemclick tracks ===>  meta: ' + str(meta) + ', search: ' + self.search + ', album: ' + album)
                        if tracks is not None and len(tracks) > 0:
                            albumId = id
                            if isinstance(tracks[0], str) is True:
                                self.flexprint_list(tracks)
                            else:
                                tracks = self.filter_list_to_unique_id(tracks)
                                if meta['zonetype'] == 'Apple Music':
                                    tracks.insert(0, {"name": self.lang['play_album'].title(), "id": "[FULLALBUM]"})
                                if meta['zonetype'].startswith('Spotify'):
                                    tracks = list(map(lambda obj: {"name": str(obj['track_number']) + '. ' +  obj['name'], "id": 'spotify:track:' + obj['id']}, tracks))
                                    albumId = meta['albumId'] if 'albumId' in meta else album
                                    tracks.insert(0, {"name": self.lang['play_album'].title(), "id": 'spotify:album:' + albumId})
                                track_names = list(map(lambda obj: obj['name'], tracks))
                                self.flexprint_list(track_names)
                            meta['type'] = result_type
                            meta['album'] = name
                            meta['albumId'] = albumId
                            meta['label'] = self.lang['select_track'].title()
                            meta['listname'] = meta['artist'] + ' - ' + meta['album']
                            if self.searchlog is True: self.flexprint('on_itemclick before _open_list (no playlists or tracks), meta: ' + str(meta))
                            self._open_list(meta, tracks)
                        else:
                            self.itemlistclass.error_message(self.lang['notfound'].upper())
                    if meta['type']=='playlists' and result_type == 'tracks':
                        self.search = data[1]
                        playlist = data[2]
                        tracks = data[3]
                        if self.searchlog is True: self.flexprint('coverplayer on_itemclick playlist tracks ===>  meta: ' + str(meta) + ', search: ' + self.search + ', playlist: ' + str(playlist))
                        if tracks is not None and len(tracks) > 0:
                            if isinstance(tracks[0], str) is True:
                                self.flexprint_list(tracks)
                            else:
                                tracks = self.filter_list_to_unique_id(tracks)
                                if meta['zonetype'] == 'Apple Music':
                                    tracks.insert(0, {"name": self.lang['play_playlist'].title(), "id": "[FULLPLAYLIST]"})
                                if meta['zonetype'].startswith('Spotify'):
                                    tracks = list(map(lambda obj: {"name": obj['name'], "id": obj['id']}, tracks))
                                    tracks = self.filter_list_to_unique_id(tracks)
                                    tracks.insert(0, {"name": self.lang['play_playlist'].title(), "id": 'spotify:playlist:' + playlist})
                                track_names = list(map(lambda obj: obj['name'], tracks))
                                self.flexprint_list(track_names)
                            meta['type'] = result_type
                            meta['playlist'] = name
                            meta['playlistId'] = id # or maybe playlist
                            meta['label'] = self.lang['select_track'].title()
                            meta['listname'] = name
                            if self.searchlog is True: self.flexprint('on_itemclick before _open_list (playlists), meta: ' + str(meta))
                            self._open_list(meta, tracks)
                        else:
                            self.itemlistclass.error_message(self.lang['notfound'].upper())
                    if result_type =='track' or result_type =='radio':
                        self.itemlistclass.close()
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]on itemclick error:[/red] {e}")

    def _open_keyb(self, type):
        try:
            self.root.withdraw()
            if type=='tracklist':
                if len(self.text) > 3:
                    zone = self.text[0].split(':')[1].strip()
                    zonetype = zone.split('-')[1].strip() if (self.zone is not None and len(self.zone.split('-'))==2) else ''
                    if (zonetype!='Apple Music' and not zonetype.startswith('Spotify')):
                        zonetype = 'Roon'
                    artist = self.text[1].split(':')[1].strip()
                    if '/' in artist:
                        artist = artist.split('/')[0].strip()
                    if ',' in artist:
                        artist = artist.split(',')[0].strip()
                    if '+' in artist:
                        artist = artist.split('+')[0].strip()
                    if '&' in artist:
                        artist = artist.split('&')[0].strip()
                    album = self.text[2].split(':')[1].strip()
                    track = self.text[3].split(':')[1].strip()
                    if zone == self.zone:
                        is_stream = self.sourcetype == 'stream'
                        meta = {"stream": is_stream, "zonetype": zonetype, "type": 'albums', 'searchtype': type, 'search': artist, 'artist': artist, 'artistId': artist, 'album': album, 'trackId': str(self.track_id), 'label': self.lang['artist'].title(), 'listname': artist}
                        self.flexprint('tracklist clicked => meta: ' + str(meta))
                        self.search = artist
                        self.on_itemclick(meta, album, self.track_id)
            elif type=='spotify-devicelist':
                is_stream = self.sourcetype == 'stream'
                zone_name = self.zone.split('-')[0]
                meta = {"type": 'spotify-devicelist', 'label': self.lang['select_spotify-devicelist'], 'listname': zone_name}
                self.flexprint('coverplayer _open_keyb spotify-devicelist clicked => meta: ' + str(meta))
                self.search = zone_name
                self.on_itemclick(meta, zone_name, zone_name)
            else:
                self.hasRadioSearch = False
                zonetype = self.get_zonetype()
                if (zonetype.startswith('Spotify') is False):
                    self.hasRadioSearch = True
                self.flexprint('********* _open_keyb, type: ' + str(type) + ', zonetype: ' + str(zonetype) + ', hasRadioSearch: ' + str(self.hasRadioSearch))
                self.vkeyb.start(type, [], self.keyb_list, self.lang, self.hasRadioSearch, zonetype, self.sourcetype, self.alternative_layout, self.on_search, self.close_keyb)
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]open keyb error:[/red] {e}")

    def _open_list(self, meta, items):
        try:
            self.flexprint('coverplayer => open_list, meta: ' + str(meta) + ', items: ' + str(len(items)))
            #self.root.withdraw()
            self.itemlistclass.start(meta, items, self.lang, self.on_itemclick, self.close_list)
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]open list error:[/red] {e}")

    def draw_progressbar_with_endless_symbol(self, playpos, playlen):
        try:
            if self.canvas is not None:
                self.canvas.config(width = self.progressbar_width_disabled)
            else:
                self.canvas=Canvas(self.overlay, width = self.progressbar_width_disabled, height = 5)
                self.canvas.place(x = 120, y = self.overlay_height - self.control_button_height - self.extra_space_height + 15)
            if playlen == -1 and playpos == -1:
                if self.playlen_canvas != None:
                    self.playlen_canvas.destroy()
                    self.playlen_canvas = None
            else:
                self.canvas.create_line(0, 0, self.progressbar_width_disabled,0, fill = "white", width = 14)
                self.canvas.create_line(1, 1, self.progressbar_width_disabled - 3, 1, fill = "green", width = 12)
                self.playlen_canvas = Canvas(self.overlay, width = 40, height = 36, bg = self.overlay_bgcolor, bd = 0, highlightthickness = 0)
                self.playlen_canvas.place(x = self.playlen_pos_disabled, y = self.overlay_height - self.control_button_height - self.extra_space_height)   
                txtid = self.playlen_canvas.create_text(0, -15, text='\u221E', fill="white", font=('Arial', 40), anchor='nw')             
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]draw progressbar with endless symbol error:[/red] {e}")

    def wakeup_load_image_select_zone_disable_tracklist_and_search(self, playmode, path, text):
        # wakeup, load_image, select zone button, disable tracklist and search button if zone is spotify or applemusic streaming and disabled or zone is inactive, 
        try:
            paused = not playmode
            icon_path = self.scriptpath + "icons/play.png"
            self.flexprint('display_auto_wakeup: ' + str(self.display_auto_wakeup))
            if self.display_auto_wakeup is True:
                subprocess.run(["sh", "-c", "export DISPLAY=:0;xset dpms force on"], check=True) # wakeup display
            self._load_image(self.label, self.errorlog, self.debug, self.log, self.lang, self.flexprint, self.maxpx_y, paused, icon_path, self.fonts, self.faces, self.font_size, self.webserver_url_request_timeout, path, text)
            if len(text) > 0:
                self.text = text
                line_parts = text[0].split(':')
                if len(line_parts) > 1:
                    if self.in_menu_mode is True and self.zone is not None and self.zone in self.zone_btn:
                        self.zone_btn[self.zone].config(bg = None)
                    self.zone = line_parts[1].strip()
                    if self.in_menu_mode is True and self.zone is not None and self.zone in self.zone_btn:
                        self.zone_btn[self.zone].config(bg = self.button_highlight_color)
                    if self.in_menu_mode is True and self.tracklist_btn is not None:
                        if self.text is not None and len(self.text) > 3:
                            zone = self.text[0].split(':')[1].strip()
                            self.set_tracklist_button(zone)
                        else:
                            self.switch_button_state(self.tracklist_btn, False)               
                    self.set_search_button()
        except Exception as e:
            if self.errorlog is True: self.flexprint("[red]wakeup error:[/red]", e)
    
    def update_playpos_next(self, func, check_playpos, playpos, is_radio):
        try:
            if check_playpos is not None and check_playpos != -1:
                self.playpos_next = playpos if is_radio is False else 0
                if self.debug is True:
                    self.flexprint('[red]CoverPlayer: poll_queue ' + func + ' => playpos_next: ' + str(playpos) + '[/red]')
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]update playpos next error:[/red] {e}")

    def set_playlen_text_or_remove_progressbar_if_changed_and_negative_set_endless_symbol_if_undefined(self, playpos, playlen):
        # remove progressbar if playlen is changed to negative, set playlen text if playlen is negative, set endless symbol if playlen is none or negative
        try:
            if self.in_menu_mode is True and playlen is not None and self.playlen != playlen:
                if playlen == -1:
                    self.canvas_clear = Canvas(self.overlay, width = self.maxpx_x, height = 40, bd = 0, highlightthickness = 0, relief = 'ridge', bg = self.overlay_bgcolor)
                    self.canvas_clear.place(x = 0, y = self.overlay_height - self.control_button_height - self.extra_space_height)
                else:
                    self.draw_progressbar(self.playpos, self.playlen)
                    self.playlen_text = Label(self.overlay, text = timedelta(seconds=playlen), bg = self.overlay_bgcolor, font = "Arial 20 bold", fg = 'white')
                    self.playlen_text.place(x = self.playlen_pos_std, y = self.overlay_height - self.control_button_height - self.extra_space_height)
                    if self.canvas_clear is not None:
                        self.canvas_clear.destroy()
                        self.canvas_clear = None
            if self.in_menu_mode is True and (playlen is None or playlen == -1):
                self.draw_progressbar_with_endless_symbol(playpos, playlen)
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]set playlen text or remove progressbar if changed and negative set endless symbol if undefined error:[/red] {e}")

    def set_playpos(self, playpos):
        try:
            if self.in_menu_mode is True and self.debug is True:
                self.count += 1
                upd_pos_text = str(timedelta(seconds=playpos)) + ' / ' + str(self.count) if (playpos is not None and playpos != -1) else str(playpos) + ' / ' + str(self.count)
                upd_pos = Label(self.overlay, text = upd_pos_text, bg = self.overlay_bgcolor, font = "Arial 20 bold", fg = 'white')
                upd_pos.place(x = 10, y = self.overlay_height - self.control_button_height - self.extra_space_height + 40)
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]set playpos error:[/red] {e}")

    def set_shuffle_and_repeat(self, playlen):
        # shuffle and repeat button at the bottom left
        try:
            if self.in_menu_mode is True and self.shuffle_btn is not None and self.shuffle_btn.winfo_exists() and (self.playlen is None or playlen is None or self.playlen == -1 or playlen == -1):
                switch_enabled = self.is_radio is False and playlen is not None and playlen!=-1 and self.missing_zone is False and self.stopped_zone is False
                self.switch_small_button_state(self.shuffle_btn, self._toggle_shuffle, switch_enabled)
                self.switch_small_button_state(self.repeat_btn, self._toggle_repeat, switch_enabled)
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]set shuffle and repeat error:[/red] {e}")

    def set_play_control(self):
        try:
            zone_type = (self.zone.split('-')[1].strip()) if (self.zone is not None and len(self.zone.split('-'))==2 and (self.zone.endswith('-Apple Music') or self.zone.endswith('-Spotify') or self.zone.endswith('-SpotifyConnect'))) else 'Roon'
            switch_enabled = self.zone is not None and (zone_type == 'Spotify' or zone_type == 'Apple Music' or (self.missing_zone is False and self.stopped_zone is False))

            self.switch_playcontrol_button_state(self.backward_btn, lambda: self._control("backward"), switch_enabled)      
            self.switch_playcontrol_button_state(self.play_btn, self._toggle_play, switch_enabled)
            self.switch_playcontrol_button_state(self.forward_btn, lambda: self._control("forward"), switch_enabled)
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]set play control error:[/red] {e}")

    def _poll_queue(self):
        try:
            while True:
                func, playpos, playlen, path, is_playing, sourcetype, is_radio, shuffle_on, repeat_on, track_id, text, buttons, zone_callback, control_callback, search_callback, itemclick_callback = self._queue.get_nowait()
                if func == 'update':
                    text_changed = '|'.join(self.text) != '|'.join(text)
                    path_changed = self.path != path
                    playlen_changed = self.playlen != playlen
                    playing_changed = self.is_playing != is_playing 
                    shuffle_changed = self.shuffle_on != shuffle_on
                    repeat_changed = self.repeat_on != repeat_on
                    track_id_changed = self.track_id != track_id
        
                    if text_changed or path_changed or playlen_changed or playing_changed or shuffle_changed or repeat_changed:
                        self.missing_zone = self.text is not None and len(self.text) == 2 and self.text[1] == 'offline'
                        self.stopped_zone = self.text is not None and len(self.text) == 2 and self.text[1] == 'inactive'

                        if self.zone_off is True or self.missing_zone is True or self.stopped_zone is True:
                            self.zone_off = False
                            self.missing_zone = False
                            self.stopped_zone = False
                        if self.debug is True:
                            self.flexprint('[bold red]CoverPlayer: poll_queue update => playpos: ' + str(playpos) + ', playlen: ' + str(playlen) + ', is_playing: ' + str(is_playing) + ', shuffle: ' + str(shuffle_on) + ', repeat: ' + str(repeat_on) + ', track_id: ' + str(track_id) + '[/bold red]')

                        #playmode = playlen is not None and playlen != -1 and is_playing is True
                        playmode = is_playing # new for roon radio
                        self.flexprint('[red]CoverPlayer: poll_queue update => playmode: ' + str(playmode) +  ', path: ' + str(path) + ', text_changed: ' + str(text_changed) + ', path_changed: ' + str(path_changed) + ', playlen_changed: ' + str(playlen_changed) + ', playing_changed: ' + str(playing_changed) + ', shuffle_changed: ' + str(shuffle_changed) + ', repeat_changed: ' + str(repeat_changed) + '[/red]')
                        self._set_playmode(playmode)

                        self._set_shufflemode(shuffle_on, playlen)
                        self._set_repeatmode(repeat_on, playlen)

                        self.is_playing = is_playing
                        self.sourcetype = sourcetype
                        self.is_radio = is_radio
                        self.shuffle_on = shuffle_on
                        self.repeat_on = repeat_on
                        self.track_id = track_id

                        if self.buttons != buttons:
                            self.buttons = buttons

                        if playpos is None:
                            if self.debug is True:
                                self.flexprint('[red]CoverPlayer: poll_queue update => playpos: is None[/red]')
                        if (playpos is None and playlen == -1) or (playpos is not None and playpos == -1):
                            self.playpos_next = -1
                        if (playpos is None or is_radio is True) and playlen != -1:
                            self.playpos_next = 0

                        self.update_playpos_next(func, playpos, playpos, is_radio)
                        self.set_playlen_text_or_remove_progressbar_if_changed_and_negative_set_endless_symbol_if_undefined(playpos, playlen)
                        self.set_shuffle_and_repeat(playlen)
                        self.set_play_control()
                    
                        self.playlen = playlen
                        self.zone_callback = zone_callback
                        self.control_callback = control_callback
                        self.search_callback = search_callback
                        self.itemclick_callback = itemclick_callback

                        self.flexprint('[bold red]update wakeup => playmode: ' + str(playmode) + ', path: ' + str(path) + ', text: ' + str(text) + '[/bold red]')
                        self.wakeup_load_image_select_zone_disable_tracklist_and_search(playmode, path, text)                                
                        self.path = path
                if func == 'set_keyboard_codes':
                    self.keyb_list = playpos
                    self.alternative_layout = playlen
                if func == 'config':
                    self.lang = playpos
                    self.webserver_url_request_timeout = playlen 
                    self.display_auto_wakeup = path
                if func == 'disable_spotify':
                    self.spotify_disabled = playpos
                if func == 'disable_applemusic':
                    self.applemusic_disabled = playpos
                if func == 'vkeyb_error_message' and self.vkeyb is not None:
                    self.vkeyb.error_message(playpos)
                if func == 'itemlist_error_message' and self.itemlistclass is not None:
                    self.itemlistclass.error_message(playpos)
                if func == 'setpos':
                    text_changed = '|'.join(self.text) != '|'.join(text)
                    path_changed = self.path != path
                    if path_changed is True:
                        self.flexprint('>>>>> >>>> >>> path_changed: ' + str(path_changed) + ', path: ' + str(path) + ', self.path: ' + str(self.path))
                    playing_changed = self.is_playing != is_playing 

                    if self.debug is True:
                        self.flexprint('[bold red]CoverPlayer: poll_queue => sourcetype: ' + str(sourcetype) + ', setpos => playpos: ' + str(playpos) + ', playlen: ' + str(playlen) + ', is_playing: ' + str(is_playing) + ', shuffle: ' + str(shuffle_on) + ', repeat: ' + str(repeat_on) + ', is_radio: ' + str(is_radio) + ', track_id: ' + str(track_id) + '[/bold red]')
                    if playpos is None:
                        if self.debug is True:
                            self.flexprint('[red]CoverPlayer: poll_queue setpos => playpos: is None[/red]')
                    if (playpos is None and playlen == -1) or (playpos is not None and playpos == -1):
                        self.playpos_next = -1
                    if (playpos is None or is_radio is True) and playlen != -1:
                        self.playpos_next = 0
                    if playpos is not None or playlen != self.playlen:
                        self.update_playpos_next(func, self.playpos, playpos, is_radio)
                    self.set_playlen_text_or_remove_progressbar_if_changed_and_negative_set_endless_symbol_if_undefined(playpos, playlen)

                    #playmode = playlen is not None and playlen != -1 and is_playing is True
                    playmode = is_playing # new for roon radio
                    self.flexprint('[red]CoverPlayer: poll_queue setpos => playmode: ' + str(playmode) + ', self.is_playing: ' + str(self.is_playing) + ', is_playing: ' + str(is_playing) + '[/red]')
                    self._set_playmode(playmode)
                    self._set_shufflemode(shuffle_on, playlen)
                    self._set_repeatmode(repeat_on, playlen)
                    
                    if self.text is not None and len(self.text) > 0 and (path_changed or text_changed or playing_changed):
                        self.flexprint('[bold red]setpos wakeup => path_changed: ' + str(path_changed) + ', text_changed: ' + str(text_changed) + ', playing_changed: ' + str(playing_changed) + '[/bold red]')
                        self.wakeup_load_image_select_zone_disable_tracklist_and_search(playmode, path, text)                                    
                        if playpos is None or is_radio is True:
                            self.playpos_next = 0

                    self.set_playpos(playpos)
                    self.set_shuffle_and_repeat(playlen)
                    self.set_play_control()

                    self.playlen = playlen
                    self.path = path
                    self.is_playing = is_playing
                    self.sourcetype = sourcetype
                    self.is_radio = is_radio
                    self.shuffle_on = shuffle_on
                    self.repeat_on = repeat_on
                    self.track_id = track_id
                if func == 'setZones' and self.buttons != buttons:
                    buttons_backup = self.buttons
                    self.buttons = buttons
                    self.zone_callback = zone_callback
                    first_load = len(self.text) == 0 and text is not None and len(text) == 2 and (text[1] == '[offline]' or text[1] == '[inactive]')
                    self.missing_zone = self.zone not in self.buttons and text is not None and len(text) == 2 and text[1] == '[offline]'
                    self.stopped_zone = self.zone in self.buttons and text is not None and len(text) == 2 and text[1] == '[inactive]'
                    self.flexprint('[red]CoverPlayer setZones => first_load: ' + str(first_load) + ', missing_zone: ' + str(self.missing_zone) + ', stopped_zone: ' + str(self.stopped_zone) + ', zone: ' + str(self.zone) + ', buttons_backup: ' + str('|'.join(buttons_backup)) + ', buttons: ' + str('|'.join(self.buttons))  + ', text: ' + str(text) + '[/red]')
                    if self.missing_zone or self.stopped_zone:
                        self.playlen =-1
                    self.set_shuffle_and_repeat(self.playlen)
                    self.set_play_control()
                    if first_load or self.missing_zone or self.stopped_zone:
                        if len(text) == 2 and (text[1] == '[offline]' or text[1] == '[inactive]'):
                            text[1] = self.lang[text[1][1:-1]]
                            self.zone_off = text[1] == '[offline]'
                        else:
                            self.zone_off = False
                        self.text = text
                        self.flexprint('[bold red]setZones wakeup => buttons: ' + str('|'.join(buttons)) + ', text: ' + str('|'.join(text)) + '[/bold red]')
                        self.wakeup_load_image_select_zone_disable_tracklist_and_search(False, '', self.text)
                    else:
                        self.zone_off = False
        except queue.Empty:
            pass
        except Exception as e:
            if self.errorlog is True: self.flexprint(f"[red]poll_queue error:[/red] {e}")
        self.root.after(100, self._poll_queue)


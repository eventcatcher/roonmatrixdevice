from tkinter import Tk, Label, Button, Frame, Canvas, font as tkFont
from PIL import Image, ImageTk, ImageDraw, ImageFont
import queue
import threading
import requests
from io import BytesIO
from os import path
import time
import subprocess
from datetime import timedelta
from threading import Timer
from rich import print

class SimpleImageWindow:
    _instance = None
    _queue = queue.Queue()
    maxpx = 720					# screen size in px

    @classmethod
    def update(cls, playpos, playlen, path_or_url, is_playing, shuffle_on, text = [], buttons = None, callback = None, control_callback = None):
        cls._ensure_running()
        cls._queue.put(('update', playpos, playlen, path_or_url, is_playing, shuffle_on, text, buttons or [], callback, control_callback))

    @classmethod
    def setpos(cls, playpos, playlen, path_or_url, is_playing, shuffle_on, text = []):
        cls._ensure_running()
        cls._queue.put(('setpos', playpos, playlen, path_or_url, is_playing, shuffle_on, text, None, None, None))

    @classmethod
    def setZones(cls, buttons):
        cls._ensure_running()
        cls._queue.put(('setZones', None, None, None, None, None, None, buttons or [], None, None))

    @classmethod
    def _ensure_running(cls):
        if cls._instance is None:
            cls._instance = cls()
            threading.Thread(target = cls._instance._gui_loop, daemon = True).start()

    def _gui_loop(self):
        self.root = Tk()
        self.root.focus_force()
        self.root.title("CoverImage")
        self.root.overrideredirect(True)
        self.root.geometry("720x720+0+0")
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

        self.maxpx = 720					# screen size in px
        self.overlay_height = self.maxpx
        self.overlay_relheight = 1
        self.overlay_bgcolor = "#222222"	# background color of control overlay
        self.buttonFont = tkFont.Font(family='Noto Sans Mono', size=13, weight=tkFont.NORMAL)
        self.button_highlight_color = '#80ed99'

        # button size in px (screensize is 72mm x 72mm for 720px x 720px => 10px / mm on screen)
        self.zone_button_height = 91
        self.control_button_height = 90
        self.extra_space_height = 50

        self.debug = False
        self.count = 0
        self.play_btn = None
        self.overlay = None
        self.overlay_timer = None
        self.in_menu_mode = False
        self.buttons = []
        self.playpos = -1
        self.playlen = -1
        self.playpos_next = None
        self.playpos_text = None
        self.playlen_text = None
        self.canvas = None
        self.canvas_clear = None
        self.text = []
        self.zone = None
        self.zone_btn = {}
        self.path = ''
        self.callback = None
        self.control_callback = None
        self.is_playing = True
        self.shuffle_on = False
        self.control_icons = {}
        self._load_control_icons()

        self.root.after(1000, self.update_playpos)

        self._poll_queue()
        self.root.mainloop()

    def _check_display(self):
        screen_on = self.is_screen_on()
        now = time.time()

        if screen_on:
            # If the display has just been switched on
            if now - self.last_screen_on > 10:
                print("Display has been reactivated")
                self.just_woke_up = True
                self.root.after(1000, self._reset_wake_flag)
                self.wake_time = now  # Zeit merken
            self.last_screen_on = now
        else:
            self._reset_wake_flag()  # to be on the safe side
        self.root.after(1000, self._check_display)

    def _reset_wake_flag(self):
        self.just_woke_up = False
    
    def is_screen_on(self):
        try:
            output = subprocess.check_output(['xset', '-q']).decode()
            for line in output.splitlines():
                if "Monitor is" in line:
                    return "On" in line
        except Exception as e:
            print(f"[red]Error with xset:[/red] {e}")
        return False

    def _on_click_start(self, event):
        screen_on = self.is_screen_on()
        now = time.time()
        if (screen_on is True and now - self.last_screen_on > 10) or (self.just_woke_up and now - self.wake_time < 1):
            print("Touch ignored after wake-up.")
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
        
    def _on_click_end(self, event):
        if hasattr(self, "_press_after_id"):
            self.root.after_cancel(self._press_after_id)
            del self._press_after_id

    def _on_long_press(self):
        print("long press – close app.")
        self.root.destroy()
    
    def _load_control_icons(self):
        from tkinter import PhotoImage
        try:
            self.control_icons = {
                "play": PhotoImage(file = self.scriptpath + "icons/play.png"),
                "pause": PhotoImage(file = self.scriptpath + "icons/pause.png"),
                "forward": PhotoImage(file = self.scriptpath + "icons/forward.png"),
                "back": PhotoImage(file = self.scriptpath + "icons/backward.png"),
                "shuffle_on": PhotoImage(file = self.scriptpath + "icons/shuffle-on.png"),
                "shuffle_off": PhotoImage(file = self.scriptpath + "icons/shuffle-off.png"),
                "close": PhotoImage(file = self.scriptpath + "icons/close.png"),
        }
        except Exception as e:
            print(f"[red]Icon loading error:[/red] {e}")

    def _start_overlay_timer(self):
        self._cancel_overlay_timer()
        #self.overlay_timer = self.root.after(15000, self._hide_overlay)

    def _cancel_overlay_timer(self):
        if self.overlay_timer:
            self.root.after_cancel(self.overlay_timer)
            self.overlay_timer = None

    def _show_overlay(self):
        self._start_overlay_timer()
        
        max_per_row = 3		# max 3 buttons per row

        ctrl_btn_bgcolor = "white"	# background color of control buttons
        ctrl_btn_ipad = 20			# inner padding in px of control buttons
        corner_btn_size = 60		# button size in px of shuffle and close button in the bottom corners
        
        total = len(self.buttons)
        rows = (total + max_per_row - 1) // max_per_row
        self.overlay_height = rows * self.zone_button_height + self.extra_space_height + self.control_button_height
        self.overlay_relheight = 1/self.maxpx*self.overlay_height

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
    
        for idx, label in enumerate(self.buttons):
            row = idx // max_per_row
            col = idx % max_per_row
            self.zone_btn[label] = Button(zone_frame, text = label, bg = self.button_highlight_color if (self.zone is not None and label == self.zone) else None, wraplength = self.maxpx / 4 , font = self.buttonFont, command = lambda l = label: self._on_button_click(l), pady = 20, height = 1)
            self.zone_btn[label].grid(row = row, column = col, padx = 10, pady = 10, sticky = "ew")

        # container for play control buttons (bottom)
        control_frame = Frame(self.overlay, bg = self.overlay_bgcolor)
        control_frame.grid_columnconfigure(0, weight = 1)
        control_frame.pack(side = 'bottom', anchor = 'center')

        # control buttons close together
        Button(control_frame, image = self.control_icons["back"], bg = ctrl_btn_bgcolor, bd = 0, command = lambda: self._control("backward"), takefocus = 0).pack(side = "left", padx = (0, 5), ipadx = ctrl_btn_ipad, ipady = ctrl_btn_ipad)
        icon = self.control_icons["pause"] if self.is_playing else self.control_icons["play"]
        self.play_btn = Button(control_frame, image = icon, bg = ctrl_btn_bgcolor, bd = 0, command = self._toggle_play)
        self.play_btn.pack(side = "left", padx = 5, ipadx = ctrl_btn_ipad, ipady = ctrl_btn_ipad)
        Button(control_frame, image = self.control_icons["forward"], bg = ctrl_btn_bgcolor, bd = 0, command = lambda: self._control("forward"), takefocus = 0).pack(side = "left", padx = 5, ipadx = ctrl_btn_ipad, ipady = ctrl_btn_ipad)

		# shuffle button at the bottom left
        icon = self.control_icons["shuffle_on"] if self.shuffle_on else self.control_icons["shuffle_off"]
        self.shuffle_btn = Button(self.overlay, image = icon, bg = self.overlay_bgcolor, bd = 0, command = self._toggle_shuffle, takefocus = 0, activebackground = self.overlay_bgcolor, height = corner_btn_size, width = corner_btn_size)
        self.shuffle_btn.place(relx = 0.0, rely = 1.0, anchor = "sw", x = 0, y = 0)

        # back button at the bottom right
        back_btn = Button(self.overlay, image = self.control_icons["close"], bg = self.overlay_bgcolor, bd = 0, command = self._hide_overlay, height = corner_btn_size, width = corner_btn_size)
        back_btn.place(relx = 1.0, rely = 1.0, anchor = "se", x = 0, y = 0)

        if self.playpos is not None and self.playpos != -1:
            self.playpos_text = Label(self.overlay, text = timedelta(seconds=self.playpos), bg = self.overlay_bgcolor, font = "Arial 20 bold", fg = 'white')
            self.playpos_text.place(x = 10, y = self.overlay_height - self.control_button_height - self.extra_space_height)
            self.canvas=Canvas(self.overlay, width = self.maxpx - 240, height = 5)
            self.canvas.place(x = 120, y = self.overlay_height - self.control_button_height - self.extra_space_height + 15)
            self.canvas.create_line(0, 0, self.maxpx - 240,0, fill = "white", width = 14)
            w = (self.maxpx - 243) / self.playlen * self.playpos
            self.canvas.create_line(1, 1, w, 1, fill = "green", width = 12)

        if self.playlen is not None and self.playlen != -1:
            self.playlen_text = Label(self.overlay, text = timedelta(seconds=self.playlen), bg = self.overlay_bgcolor, font = "Arial 20 bold", fg = 'white')
            self.playlen_text.place(x = self.maxpx - 110, y = self.overlay_height - self.control_button_height - self.extra_space_height)

    def update_playpos(self):
        self.root.after(1000, self.update_playpos)
        if self.playpos_next != None:
            self.playpos = self.playpos_next
            self.playpos_next = None
        if self.is_playing is True and self.playpos is not None and self.playpos != -1 and self.playlen is not None and self.playlen != -1:
            if self.playpos < self.playlen:
                self.playpos += 1
            if self.in_menu_mode is True:
                if self.playpos_text is None:
                    self.playpos_text = Label(self.overlay, text = timedelta(seconds=self.playpos), bg = self.overlay_bgcolor, font = "Arial 20 bold", fg = 'white')
                else:
                    self.playpos_text.config(text=timedelta(seconds=self.playpos))
                self.playpos_text.place(x = 10, y = self.overlay_height - self.control_button_height - self.extra_space_height)
                if self.canvas is None:
                    self.canvas=Canvas(self.overlay, width = self.maxpx - 240, height = 5)
                    self.canvas.place(x = 120, y = self.overlay_height - self.control_button_height - self.extra_space_height + 15)
                self.canvas.create_line(0, 0, self.maxpx - 240,0, fill = "white", width = 14)
                w = (self.maxpx - 243) / self.playlen * self.playpos
                self.canvas.create_line(1, 1, w, 1, fill = "green", width = 12)
        if self.debug is True:
            print('### classfunc update_playpos: ' + str(self.playpos))
    
    def _control(self, action):
        self._start_overlay_timer()
        if self.control_callback:
            self.control_callback(action)

    def _toggle_play(self):
        self._start_overlay_timer()
        self._set_playmode(not self.is_playing)
        self.is_playing = not self.is_playing
        self._control("play" if self.is_playing else "pause")

    def _set_playmode(self, mode):
        if self.in_menu_mode is True and self.play_btn is not None:
            icon = self.control_icons["pause"] if mode else self.control_icons["play"]
            self.play_btn.config(image = icon)
            print('[bold red]### set_playmode: '+ str(mode) + '[/bold red]')
    
    def _toggle_shuffle(self):
        self._start_overlay_timer()
        self.shuffle_on = not self.shuffle_on
        icon = self.control_icons["shuffle_on"] if self.shuffle_on else self.control_icons["shuffle_off"]
        self.shuffle_btn.config(image = icon)
        self._control("shuffle_on" if self.shuffle_on else "shuffle_off")

    def _on_button_click(self, value):
        if self.callback:
            self.zone = value
            self.callback(value)
        self._hide_overlay()

    def _hide_overlay(self):
        self._cancel_overlay_timer()
        if self.overlay:
            self.playpos_text = None
            self.playlen_text = None
            if self.canvas is not None:
                self.canvas.destroy()
                self.canvas = None
            if self.canvas_clear is not None:
                self.canvas_clear.destroy()
                self.canvas_clear = None
            self.overlay.destroy()
            self.overlay = None
            self.in_menu_mode = False

    def _poll_queue(self):
        try:
            while True:
                func, playpos, playlen, path, is_playing, shuffle_on, text, buttons, callback, control_callback = self._queue.get_nowait()
                if func == 'update' and ('|'.join(self.text) != '|'.join(text) or self.path != path or self.playlen != playlen):
                    if self.debug is True:
                        print('[bold red]### poll_queue update => playpos: ' + str(playpos) + ', playlen: ' + str(playlen) + ', is_playing: ' + str(is_playing) + ', shuffle: ' + str(shuffle_on) + '[/bold red]')
                    playmode = playlen is not None and playlen != -1 and is_playing is True
                    print('[red]### poll_queue update => playmode: ' + str(playmode) +  ', path: ' + str(path) + '[/red]')
                    self._set_playmode(playmode)

                    self.is_playing = is_playing
                    self.shuffle_on = shuffle_on

                    if self.buttons != buttons:
                        self.buttons = buttons

                    if playpos is None:
                        if self.debug is True:
                            print('[red]### poll_queue update => playpos: is None[/red]')
                    if (playpos is None and playlen == -1) or (playpos is not None and playpos == -1):
                        self.playpos_next = -1
                    if playpos is None and playlen != -1:
                        self.playpos_next = 0
                    #if playpos is not None and playpos != -1 and (self.playpos is None or self.playpos == -1 or (self.playpos is not None and playpos >= self.playpos) or self.text != text or self.path != path or self.playlen != playlen):
                    if playpos is not None and playpos != -1:
                        self.playpos_next = playpos
                        if self.debug is True:
                            print('[red]### poll_queue update => playpos_next: ' + str(playpos) + '[/red]')
                    if self.in_menu_mode is True and playlen is not None and self.playlen != playlen:
                        if playlen == -1:
                            self.canvas_clear = Canvas(self.overlay, width = self.maxpx, height = 40, bd = 0, highlightthickness = 0, relief = 'ridge', bg = self.overlay_bgcolor)
                            self.canvas_clear.place(x = 0, y = self.overlay_height - self.control_button_height - self.extra_space_height)
                        else:
                            self.playlen_text = Label(self.overlay, text = timedelta(seconds=playlen), bg = self.overlay_bgcolor, font = "Arial 20 bold", fg = 'white')
                            self.playlen_text.place(x = self.maxpx - 110, y = self.overlay_height - self.control_button_height - self.extra_space_height)
                            if self.canvas_clear is not None:
                                self.canvas_clear.destroy()
                                self.canvas_clear = None

                    self.playlen = playlen
                    self.callback = callback
                    self.control_callback = control_callback
                    paused = not playmode
                    icon_path = self.scriptpath + "icons/play.png"
                    img = self._load_image(paused, icon_path, path, text)
                    if img:
                        self.label.config(image = img)
                        self.label.image = img
                    else:
                        self.label.config(text = "Image not found", image = "")
                    self.text = text
                    if len(text) > 0:
                        line_parts = text[0].split(':')
                        if len(line_parts) > 0:
                            if self.in_menu_mode is True and self.zone is not None and self.zone in self.zone_btn:
                                self.zone_btn[self.zone].config(bg = None)
                            self.zone = line_parts[1].strip()
                            if self.in_menu_mode is True and self.zone is not None and self.zone in self.zone_btn:
                                self.zone_btn[self.zone].config(bg = self.button_highlight_color)
                    self.path = path
                if func == 'setpos':
                    if self.debug is True:
                        print('[bold red]### poll_queue setpos => playpos: ' + str(playpos) + ', playlen: ' + str(playlen) + ', is_playing: ' + str(is_playing) + ', shuffle: ' + str(shuffle_on) + '[/bold red]')
                    if playpos is None:
                        if self.debug is True:
                            print('[red]### poll_queue setpos => playpos: is None[/red]')
                    else:
                        if self.playlen is not None and self.playlen != -1:
                            self.playpos_next = playpos
                            if self.debug is True:
                                print('[red]### poll_queue setpos => playpos_next: ' + str(playpos) + '[/red]')
                    if self.in_menu_mode is True and playlen is not None and self.playlen != playlen:
                        if playlen == -1:
                            self.canvas_clear = Canvas(self.overlay, width = self.maxpx, height = 40, bd = 0, highlightthickness = 0, relief = 'ridge', bg = self.overlay_bgcolor)
                            self.canvas_clear.place(x = 0, y = self.overlay_height - self.control_button_height - self.extra_space_height)
                        else:
                            self.playlen_text = Label(self.overlay, text = timedelta(seconds=playlen), bg = self.overlay_bgcolor, font = "Arial 20 bold", fg = 'white')
                            self.playlen_text.place(x = self.maxpx - 110, y = self.overlay_height - self.control_button_height - self.extra_space_height)
                            if self.canvas_clear is not None:
                                self.canvas_clear.destroy()
                                self.canvas_clear = None

                    playmode = playlen is not None and playlen != -1 and is_playing is True
                    print('[red]### poll_queue setpos => playmode: ' + str(playmode) + ', self.is_playing: ' + str(self.is_playing) + ', is_playing: ' + str(is_playing) + '[/red]')
                    self._set_playmode(playmode)
                            
                    if self.path != path or '|'.join(self.text) != '|'.join(text) or self.is_playing != is_playing:
                        paused = not playmode
                        icon_path = self.scriptpath + "icons/play.png"
                        img = self._load_image(paused, icon_path, path, text)
                        if img:
                            self.label.config(image = img)
                            self.label.image = img
                        else:
                            self.label.config(text = "Image not found", image = "")
                        self.path = path
                        self.text = text
                        if len(text) > 0:
                            line_parts = text[0].split(':')
                            if len(line_parts) > 0:
                                if self.in_menu_mode is True and self.zone is not None and self.zone in self.zone_btn:
                                    self.zone_btn[self.zone].config(bg = None)
                                self.zone = line_parts[1].strip()
                                if self.in_menu_mode is True and self.zone is not None and self.zone in self.zone_btn:
                                    self.zone_btn[self.zone].config(bg = self.button_highlight_color)
                        if playpos is None:
                            self.playpos_next = 0

                    if self.in_menu_mode is True and self.debug is True:
                        self.count += 1
                        upd_pos_text = str(timedelta(seconds=playpos)) + ' / ' + str(self.count) if (playpos is not None and playpos != -1) else str(playpos) + ' / ' + str(self.count)
                        upd_pos = Label(self.overlay, text = upd_pos_text, bg = self.overlay_bgcolor, font = "Arial 20 bold", fg = 'white')
                        upd_pos.place(x = 10, y = self.overlay_height - self.control_button_height - self.extra_space_height + 40)

                    self.playlen = playlen
                    self.is_playing = is_playing
                    self.shuffle_on = shuffle_on
                if func == 'setZones' and self.buttons != buttons:
                    self.buttons = buttons

        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)
    
    @classmethod
    def _wrap_text(cls, text, font, max_width):
        """wraps text if its too long."""
        lines = []
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
        
        return lines

    @classmethod
    def _load_image(cls, paused, icon_path, path_or_url = None, text = None):
        try:
            if path_or_url is None:
            	path_or_url = path.dirname(__file__) + '/cover_fallback.png'
            if path_or_url.startswith("http"):
                response = requests.get(path_or_url, timeout = 5)
                img = Image.open(BytesIO(response.content))
            else:
                img = Image.open(path_or_url)

            img = img.resize((cls.maxpx, cls.maxpx), Image.ANTIALIAS)
            
            if paused is True:
                canvas = Image.new("RGB", (cls.maxpx,cls.maxpx))
                mask   = Image.new('L',   (cls.maxpx,cls.maxpx))
                canvasDraw = ImageDraw.Draw(canvas)
                maskDraw   = ImageDraw.Draw(mask)
                canvasDraw.rectangle((0,0,cls.maxpx - 1,cls.maxpx - 1), 'white')
                maskDraw.rectangle((0,0,cls.maxpx - 1,cls.maxpx - 1), 160)
                img.paste(canvas, mask)
                size = round(cls.maxpx / 5)
                icon_img = Image.open(icon_path)
                icon_img = icon_img.resize((size, size), Image.ANTIALIAS)
                pos = round((cls.maxpx - size) / 2)
                img.paste(icon_img, (pos, pos), mask = icon_img)

            draw = ImageDraw.Draw(img)

            if text:
                font_size = 24
                line_space = 5
                
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size = font_size)
                except IOError:
                    font = ImageFont.load_default()

                max_width = img.width - 40  # max width of text
                lines_all_items = 0
                for text_part in text:
                    lines = cls._wrap_text(text_part, font, max_width)
                    lines_all_items += len(lines)
                    
                border_space = 20
                text_x = border_space
                text_y = img.height - border_space - lines_all_items * (font_size + line_space)
                
                background = (0, 0, 0, 128)  # RGB + Alpha (0-255)
                
                for text_part in text:
                    lines = cls._wrap_text(text_part, font, max_width)
                    for line in lines:
                        text_width, text_height = draw.textsize(line, font = font)
                        draw.rectangle(
                            [text_x - 5, text_y - line_space, text_x + text_width + 5, text_y + text_height + line_space],
                            fill = background
                        )
                        draw.text((text_x, text_y), line, font = font, fill = "white")
                        text_y += text_height + line_space  # line spacing

            return ImageTk.PhotoImage(img)
        except Exception as e:
            print(f"[red]Error on image loading:[/red] {e}")
            return None


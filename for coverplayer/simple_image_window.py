from tkinter import Tk, Label, Button, Frame
from PIL import Image, ImageTk, ImageDraw, ImageFont
import queue
import threading
import requests
from io import BytesIO
from os import path
import time
import subprocess

class SimpleImageWindow:
    _instance = None
    _queue = queue.Queue()

    @classmethod
    def update(cls, path_or_url, is_playing, shuffle_on, text = None, buttons = None, callback = None, control_callback = None):
        cls._ensure_running()
        cls._queue.put((path_or_url, is_playing, shuffle_on, text, buttons or [], callback, control_callback))

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

        self.overlay = None
        self.overlay_timer = None
        self.in_menu_mode = False
        self.buttons = []
        self.callback = None
        self.control_callback = None
        self.is_playing = True
        self.shuffle_on = False
        self.control_icons = {}
        self._load_control_icons()

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
            print(f"Error with xset: {e}")
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

        if self.in_menu_mode:
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
            print(f"Icon loading error: {e}")

    def _start_overlay_timer(self):
        self._cancel_overlay_timer()
        self.overlay_timer = self.root.after(15000, self._hide_overlay)

    def _cancel_overlay_timer(self):
        if self.overlay_timer:
            self.root.after_cancel(self.overlay_timer)
            self.overlay_timer = None

    def _show_overlay(self):
        self._start_overlay_timer()
        
        
        maxpx = 720			# screen size in px
        max_per_row = 3		# max 3 buttons per row

        overlay_bgcolor = "#222222"	# background color of control overlay
        ctrl_btn_bgcolor = "white"	# background color of control buttons
        ctrl_btn_ipad = 20			# inner padding in px of control buttons
        corner_btn_size = 60		# button size in px of shuffle and close button in the bottom corners
        
        # button size in px (screensize is 72mm x 72mm for 720px x 720px => 10px / mm on screen)
        zone_button_height = 85
        extra_space_height = 50
        control_button_height = 90
        
        total = len(self.buttons)
        rows = (total + max_per_row - 1) // max_per_row
        self.overlay_relheight = rows * 1/maxpx*zone_button_height + 1/maxpx*extra_space_height + 1/maxpx*control_button_height

        self.in_menu_mode = True
        self.overlay = Frame(self.root, bg = overlay_bgcolor)
        self.overlay.grid_columnconfigure(0, weight = 1)
        self.overlay.place(relx = 0, rely = 1 - self.overlay_relheight, relwidth = 1, relheight = self.overlay_relheight)

        # container for zone buttons (top)
        zone_frame = Frame(self.overlay, bg = overlay_bgcolor)
        zone_frame.pack(side = 'top', fill = 'x')
        zone_frame.place(relx = 0, rely = 0, relwidth = 1, height = rows * zone_button_height)

        # divide columns for upper buttons (consider max_per_row)
        for col in range(max_per_row):
            zone_frame.grid_columnconfigure(col, weight = 1)
    
        for idx, label in enumerate(self.buttons):
            row = idx // max_per_row
            col = idx % max_per_row
            btn = Button(zone_frame, text = label, command = lambda l = label: self._on_button_click(l), pady = 20)
            btn.grid(row = row, column = col, padx = 10, pady = 10, sticky = "ew")

        # container for play control buttons (bottom)
        control_frame = Frame(self.overlay, bg = overlay_bgcolor)
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
        self.shuffle_btn = Button(self.overlay, image = icon, bg = overlay_bgcolor, bd = 0, command = self._toggle_shuffle, takefocus = 0, activebackground = overlay_bgcolor, height = corner_btn_size, width = corner_btn_size)
        self.shuffle_btn.place(relx = 0.0, rely = 1.0, anchor = "sw", x = 0, y = 0)

        # back button at the bottom right
        back_btn = Button(self.overlay, image = self.control_icons["close"], bg = overlay_bgcolor, bd = 0, command = self._hide_overlay, height = corner_btn_size, width = corner_btn_size)
        back_btn.place(relx = 1.0, rely = 1.0, anchor = "se", x = 0, y = 0)

    def _control(self, action):
        self._start_overlay_timer()
        if self.control_callback:
            self.control_callback(action)

    def _toggle_play(self):
        self._start_overlay_timer()
        self.is_playing = not self.is_playing
        icon = self.control_icons["pause"] if self.is_playing else self.control_icons["play"]
        self.play_btn.config(image = icon)
        self._control("play" if self.is_playing else "pause")

    def _toggle_shuffle(self):
        self._start_overlay_timer()
        self.shuffle_on = not self.shuffle_on
        icon = self.control_icons["shuffle_on"] if self.shuffle_on else self.control_icons["shuffle_off"]
        self.shuffle_btn.config(image = icon)
        self._control("shuffle_on" if self.shuffle_on else "shuffle_off")

    def _on_button_click(self, value):
        if self.callback:
            self.callback(value)
        self._hide_overlay()

    def _hide_overlay(self):
        self._cancel_overlay_timer()
        if self.overlay:
            self.overlay.destroy()
            self.overlay = None
            self.in_menu_mode = False

    def _poll_queue(self):
        try:
            while True:
                path, is_playing, shuffle_on, text, buttons, callback, control_callback = self._queue.get_nowait()
                self.is_playing = is_playing
                self.shuffle_on = shuffle_on
                self.buttons = buttons
                self.callback = callback
                self.control_callback = control_callback
                img = self._load_image(path, text)
                if img:
                    self.label.config(image = img)
                    self.label.image = img
                else:
                    self.label.config(text = "Image not found", image = "")
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
    def _load_image(cls, path_or_url = None, text = None):
        try:
            if path_or_url is None:
            	path_or_url = path.dirname(__file__) + '/cover_fallback.png'
            if path_or_url.startswith("http"):
                response = requests.get(path_or_url, timeout = 5)
                img = Image.open(BytesIO(response.content))
            else:
                img = Image.open(path_or_url)

            img = img.resize((720, 720), Image.ANTIALIAS)
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
            print(f"[Error on image loading] {e}")
            return None


#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# VirtualKeyboard Class - display virtual keyboard
# Roonmatrix extension class
# version 1.2.0, date: 08.11.2025
#
# © Abhineet Kelley, coded @ 2022
# © Stephan Wilhelm, Bielefeld, Germany, based on code of Abhineet Kelley, coded @ 2025
#
# copy to /home/coverplayer/FTP
#

import tkinter.ttk as ttk
import tkinter.font as tkFont
from tkinter import *
from sys import exit as end
from os import path, system
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich import print
import sys
import logging

# if user has the keyboard module installed
has_keyboard = True

class TouchFriendlyButton(Button):
    def __init__(self, master, bg_normal, bg_active, fg_normal, fg_active, **kwargs):
        self.bg_normal = bg_normal
        self.bg_active = bg_active
        self.fg_normal = fg_normal
        self.fg_active = fg_active
        super().__init__(master, **kwargs)
        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<Leave>", self.on_leave)
        self.bind("<ButtonRelease-1>", self.on_release)

    def on_press(self, event):
        self.config(activebackground=self.bg_active, activeforeground=self.fg_active)

    def on_leave(self, event):
        self.config(activebackground=self.bg_normal, activeforeground=self.fg_normal)

    def on_release(self, event):
        self.config(activebackground=self.bg_normal, activeforeground=self.fg_normal)
        #self.invoke()  # Ruft das command auf

class VirtualKeyboard:
    def __init__(self,log,maxpx_x,maxpx_y):
        self.log = log			# log infos on or off
        self.maxpx_x = maxpx_x  # screen width in px
        self.maxpx_y = maxpx_y  # screen height in px
        self.logger = logging.getLogger('vkeyboard')
        
        self.on_close = None

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

    def circleProgress(self):
        self.center_x, self.center_y = self.maxpx_x / 2, self.maxpx_y / 2
        self.dots = 8
        self.colors = ["#888888", "#BBBBBB", "#FFFFFF"]

        master = Tk()
        master.attributes('-alpha', self.trans_value)
        master.attributes('-topmost', True)
        master.overrideredirect(True)
        master.geometry(str(self.maxpx_x) + 'x' + str(self.maxpx_y) + '+0+0')
        master.config(cursor="none")
        master.resizable(False, False)
    
        canvas = Canvas(master, width=self.maxpx_x, height=self.maxpx_y, background=self.infopage_bg_color, bd=0, highlightthickness=0, relief='ridge')
        canvas.pack(fill=BOTH, expand=1)
        searchkey = self.search
        if self.search == '':
            self.search = self.lang[self.searchtype]
        canvas.create_text(self.maxpx_x / 2, self.maxpx_y / 2, width = self.maxpx_x / 3 * 2, fill = self.infopage_fg_color, font = "Times 36 italic bold", anchor = 'center', justify = 'center', text = self.lang['searchfor'] + '\n' + self.search)
                        
        # Radius in pixels of a single dot.
        self.dot_radius = self.maxpx_x * 0.05
        # Radius of the ring of dots from the center of the window.
        self.dots_radius = self.maxpx_x / 2 - self.dot_radius * 2

        # Helper function to calculate dot position on each update.

        # Create all the dots.
        t0 = time.monotonic()
        for c, color in enumerate(self.colors):
            for n in range(self.dots):
                coords = self.get_dot_coords(n, t0, c)
                canvas.create_oval(
                    *coords,
                    fill=color,
                    width=0,  # Border width.
                    tags=f"dot_{c}_{n}",
                )

        # Set up a custom main loop to animate the moving dots.
        while self.showSpinner == True:
            # Check the time of this update.
            t = time.monotonic()
            for c, color in enumerate(self.colors):
                for n in range(self.dots):
                    # Get the desired coords for this dot at this time.
                    coords = self.get_dot_coords(n, t, c)
                    # Move the dot on the canvas, finding it by its tag.
                    canvas.coords(
                        f"dot_{c}_{n}",
                        *coords,
                    )
            # Call the required tkinter update function.
            master.update()
            # Attempt to stabilize the timing of this loop by targeting 60Hz.
            while t0 < t:
                t0 += 1 / 60
            time.sleep(t0 - t)
        master.destroy()

    def get_dot_coords(self, n: int, t: float, c: int):
        """Get the x0, y0, x1, y1 coords of dot at index 'n' at time 't'.
        Inflate the radius by color index 'c'."""
        angle = (n / self.dots) * math.pi * 2 + t
        x = math.cos(angle) * self.dots_radius + self.center_x
        y = math.sin(angle) * self.dots_radius + self.center_y
        # Invert the color index and add to the radius.
        radius = self.dot_radius + (len(self.colors) - c) * 0.75
        #radius = self.dot_radius + c
        return x - radius, y - radius, x + radius, y + radius

    def update_keyboard(self):
        if self.alt_key_pressed is True:
            # alt row 1
            idx = 1 if self.alternative_layout is False else 0
            for key in self.row1keyb_alt:
                self.row1buttons[idx].config(text=key, command=lambda x=key: self.vpresskey(x))
                idx += 1
                if idx == (11 if self.alternative_layout is False else 10):
                    break

            # alt row 2
            idx = 0
            for key in self.row2keyb_alt:
                self.row2buttons[idx].config(text=key, command=lambda x=key: self.vpresskey(x))
                idx += 1
                if idx == (11 if self.alternative_layout is False else 10):
                    break

            # alt row 3
            idx = 1 if self.alternative_layout is False else 0
            for key in self.row3keyb_alt:
                self.row3buttons[idx].config(text=key, command=lambda x=key: self.vpresskey(x))
                idx += 1
                if idx == (10 if self.alternative_layout is False else 9):
                    break
           
            # alt row 4
            idx = 1 if self.alternative_layout is False else 0
            for key in self.row4keyb_alt:
                self.row4buttons[idx].config(text=key, command=lambda x=key: self.vpresskey(x))
                idx += 1
        else:
            # shift row 1
            idx = 1 if self.alternative_layout is False else 0
            for key in (self.row1keyb_shift if (self.capslock_key_enabled is True or self.shift_key_pressed is True) else self.row1keyb):
                self.row1buttons[idx].config(text=key, command=lambda x=key: self.vpresskey(x))
                idx += 1
                if idx == (11 if self.alternative_layout is False else 10):
                    break

            # shift row 2
            if self.alternative_layout is False:
                keysrc = (self.row2keyb_shift if (self.capslock_key_enabled is True or self.shift_key_pressed is True) else self.row2keyb)
                self.row2buttons[0].config(text=keysrc[0], command=lambda x=keysrc[0]: self.vpresskey(x))
            idx = 0
            for key in self.row2keyb if self.alternative_layout is False else self.row2keyb[1:]:
                if idx == 0:
                    if self.alternative_layout is False:
                        idx += 1
                        continue
                self.row2buttons[idx].config(text=key, command=lambda x=key: self.vpresskey(x))
                idx += 1
                if idx == (11 if self.alternative_layout is False else 10):
                    break

            # shift row 3
            idx = 0
            for key in self.row3keyb if self.alternative_layout is False else self.row3keyb[1:]:
                if idx == 0:
                    if self.alternative_layout is False:
                        idx += 1
                        continue
                self.row3buttons[idx].config(text=key, command=lambda x=key: self.vpresskey(x))
                idx += 1
                if idx == (10 if self.alternative_layout is False else 9):
                    break

             # shift row 4
            idx = 0
            for key in self.row4keyb if self.alternative_layout is False else self.row4keyb[1:]:
                if idx == 0:
                    if self.alternative_layout is False:
                        idx += 1
                        continue
                self.row4buttons[idx].config(text=key, command=lambda x=key: self.vpresskey(x))
                idx += 1
                if idx == (8 if self.alternative_layout is False else 7):
                    break
            idx = (8 if self.alternative_layout is False else 7)
            for key in (self.row4keyb_shift if (self.capslock_key_enabled is True or self.shift_key_pressed is True) else self.row4keyb[-3:]):
                if idx == 0:
                    if self.alternative_layout is False: # or (self.capslock_key_enabled is True or self.shift_key_pressed is True)
                        idx += 1
                        continue
                self.row4buttons[idx].config(text=key, command=lambda x=key: self.vpresskey(x))
                idx += 1   

            for key in self.buttons.keys():
                if len(key) == 1:
                    ascode = ord(key)
                    if ascode >= 97 and ascode <= 122:
                        if self.capslock_key_enabled is True or self.shift_key_pressed is True or self.alt_key_pressed is True:
                            self.buttons[key].config(text = key.title())
                        else:
                            self.buttons[key].config(text = key)
        
    # function to press and release keys
    def vpresskey(self, x):
        value = None
        cursor_pos = self.inp.index(INSERT)
        #self.flexprint("The cursor is at: ", cursor_pos)
        #self.master.withdraw()
        actualValue = str(self.inpstr.get())
        x = self.buttonsTranslate[x] if x in self.buttonsTranslate else x
        #self.flexprint('vpresskey x: ' + str(x) + ', buttonsTranslate: ' + str(self.buttonsTranslate))
        if x == 'lock':
            self.capslock_key_enabled = (self.capslock_key_enabled is False)
            self.update_keyboard()
            value = None
        elif x == 'back':
            if len(actualValue) > 0:
                value = ''
                if cursor_pos > 1:
                    value = actualValue[0:cursor_pos - 1]
                if cursor_pos < len(actualValue):
                    value += actualValue[cursor_pos:]
                self.inpstr.set(value)
                self.inp.delete(0, END) #deletes the current value
                self.inp.insert(0, value) #inserts new value assigned by 2nd parameter
                self.inp.icursor(cursor_pos - 1)
                return
        elif x == 'del':
            if len(actualValue) > 0:
                value = ''
                if cursor_pos > 0:
                    value = actualValue[0:cursor_pos]
                if cursor_pos < len(actualValue):
                    value += actualValue[cursor_pos + 1:]
                self.inpstr.set(value)
                self.inp.delete(0, END) #deletes the current value
                self.inp.insert(0, value) #inserts new value assigned by 2nd parameter
                self.inp.icursor(cursor_pos)
                return
        elif x == 'left':
            self.shift_cursor_left()
            value = None
        elif x == 'right':
            self.shift_cursor_right()
            value = None
        elif x == 'close':
            self.on_close()
            value = None
            self.master.destroy()
            return
        else:
            if x == 'spacebar':
                x = ' '
            if x == 'enter':
                value = actualValue
            else:
                value = ''
                if cursor_pos > 0:
                    value = actualValue[0:cursor_pos]
                #self.flexprint('shift: ' + str(self.shift_key_pressed) + ', alt: ' + str(self.alt_key_pressed) + ', capslock: ' + str(self.capslock_key_enabled))
                if (self.capslock_key_enabled is True or self.shift_key_pressed):
                    ascode = ord(x)
                    if x == '/':
                        value += '?'
                    elif ascode >= 97 and ascode <= 122:
                        value += chr(ascode - 32)
                    else:
                        value += x
                else:
                    value += x
                if cursor_pos < len(actualValue):
                    value += actualValue[cursor_pos:]
        if value is not None:
            self.inpstr.set(value)
            self.inp.delete(0, END) #deletes the current value
            self.inp.insert(0, value) #inserts new value assigned by 2nd parameter
            self.inp.icursor(cursor_pos + 1)
            self.search = value
        if x == 'enter' and len(value) >= (0 if (self.zonetype!='Apple Music' and (self.searchtype=='playlist' or self.searchtype=='genre' or self.searchtype=='radio')) else self.minLength):
            self.showSpinner = True
            self.master.destroy()
            executor = ThreadPoolExecutor(max_workers=1)
            job = executor.submit(self.circleProgress)
            self.on_search(self.stream_on, self.searchtype, value)
            self.showSpinner = False
        else:
            self.master.after(10, self.master.wm_deiconify())
        if self.shift_key_pressed is True and self.capslock_key_enabled is False:
            self.shift_key_pressed = False
            self.update_keyboard()
        if self.alt_key_pressed is True:
            self.alt_key_pressed = False
            self.update_keyboard()

    def shift_cursor_left(self):
        position = self.inp.index(INSERT)

        # Changing position of cursor one character left
        self.inp.icursor(position - 1)

    def shift_cursor_right(self):
        position = self.inp.index(INSERT)

        # Changing position of cursor one character right
        self.inp.icursor(position + 1)

    # function to hold SHIFT, CTRL, ALT or WIN keys
    def vupdownkey(self, event, type):
        if type == 'shift':
            self.shift_key_pressed = self.shift_key_pressed is False
            self.capslock_key_enabled = False
            #self.flexprint('shift_key_pressed: ' + str(self.shift_key_pressed))
            self.update_keyboard()
        if type == 'alt':
            self.alt_key_pressed = self.alt_key_pressed is False
            #self.flexprint('alt_key_pressed: ' + str(self.alt_key_pressed))
            self.update_keyboard()

    def get_next_playtype(self, searchtype):
        searchtypes = ['artist','track','playlist','genre']
        if self.hasRadioSearch is True:
            searchtypes.append('radio')
        idx = searchtypes.index(searchtype)
        idx += 1
        if idx >= len(searchtypes):
            idx = 0
        return searchtypes[idx]
    
    def on_labelTap(self):
        s_type = self.get_next_playtype(self.searchtype)
        
        if self.zonetype=='Apple Music' and self.stream_on is True and s_type=='genre':
            s_type = self.get_next_playtype(s_type)

        if self.zonetype=='Apple Music' and self.stream_on is False and s_type=='radio':
            s_type = self.get_next_playtype(s_type)
        
        #self.flexprint('on_labelTap => s_type: ' + str(s_type) + ', zonetype: ' + str(self.zonetype) + ', stream_on: ' + str(self.stream_on))
        self.searchtype = s_type
        self.label.config(text=self.lang[self.searchtype])

    def unescape(self, el):
        if el=='[q]':
            el = '\''
        if el=='[dq]':
            el = '\"'
        return el

    def _load_control_icons(self):
        from tkinter import PhotoImage
        try:
            self.control_icons = {
                "stream_on": PhotoImage(master = self.master, file = self.scriptpath + "icons/stream-on.png",),
                "stream_off": PhotoImage(master = self.master, file = self.scriptpath + "icons/stream-off.png"),
        }
        except Exception as e:
            self.flexprint(f"[red]Icon loading error:[/red] {e}")
        
    # start keyboard
    def start(self, type, data, keyb_list, lang, hasRadioSearch, zonetype, sourcetype, alternative_layout, kp_callback, close_callback):
        self.flexprint('vkeyboard ==> start, zonetype: ' + str(zonetype) + ', sourcetype: ' + str(sourcetype))
        self.type = type
        self.data = data
        
        self.row1keyb = keyb_list[0]
        self.row1keyb = list(map(lambda el: self.unescape(el), keyb_list[0]))
        self.row2keyb = list(map(lambda el: self.unescape(el), keyb_list[1]))
        self.row3keyb = list(map(lambda el: self.unescape(el), keyb_list[2]))
        self.row4keyb = list(map(lambda el: self.unescape(el), keyb_list[3]))
        self.row1keyb_shift = list(map(lambda el: self.unescape(el), keyb_list[4]))
        self.row2keyb_shift = list(map(lambda el: self.unescape(el), keyb_list[5]))
        self.row4keyb_shift = list(map(lambda el: self.unescape(el), keyb_list[6]))
        self.row1keyb_alt = list(map(lambda el: self.unescape(el), keyb_list[7]))
        self.row2keyb_alt = list(map(lambda el: self.unescape(el), keyb_list[8]))
        self.row3keyb_alt = list(map(lambda el: self.unescape(el), keyb_list[9]))
        self.row4keyb_alt = list(map(lambda el: self.unescape(el), keyb_list[10]))

        self.lang = lang
        self.control_icons = {}
        self.hasRadioSearch = hasRadioSearch
        self.zonetype = zonetype
        self.sourcetype = sourcetype
        self.alternative_layout = alternative_layout
        self.on_search = kp_callback
        self.on_close = close_callback
        self.scriptpath = path.dirname(__file__) + '/'

        self.init()
        self.engine()
        
        self.master.mainloop()

    def _control(self, action):
        if action == 'stream_off' or action == 'stream_on':
            bg = None
            icon = self.control_icons["stream_on"] if self.stream_on else self.control_icons["stream_off"]
            self.sourcetype_btn.config(image = icon, bg=bg, activebackground=bg)
            if self.zonetype=='Apple Music' and self.stream_on is True and self.searchtype=='genre':
                self.on_labelTap()
            if self.zonetype=='Apple Music' and self.stream_on is False and self.searchtype=='radio':
                self.on_labelTap()

    def toggle_sourcetype(self):
        self.stream_on = self.stream_on is False
        self._control("stream_off" if self.stream_on else "stream_on")

    def init(self):
        # Main Window
        self.master = Tk()
        self.inpstr = StringVar()
        self.minLength = 3
        self.showSpinner = False
        self.buttons = {}
        self.buttonsTranslate = {}

        # Colors
        self.darkgray = "#242424"
        self.gray = "#383838"
        self.lightgray = "#bababa"
        self.darkred = "#9e1717"
        self.red = "#822626"
        self.white = "white"
        self.black = "black"
        #self.darkpurple = "#7151c4"
        #self.purple = "#9369ff"
        #self.darkblue = "#386cba"
        #self.blue = "#488bf0"
        #self.darkyellow = "#bfb967"
        #self.yellow = "#ebe481"
        
        self.bg_normal = self.gray          # background color of released buttons
        self.bg_active = self.darkgray      # background color of pressed buttons
        self.fg_normal = self.white         # foreground color of released buttons
        self.fg_active = self.lightgray     # foreground color of pressed buttons
        
        self.close_bg_normal = self.red     # background color of released close button
        self.close_bg_active = self.darkred # background color of pressed close button
        
        self.infopage_bg_color = self.black # background color of error and circle progress info pages
        self.infopage_fg_color = self.white # foreground color of error and circle progress info text
        
        self.icon_btn_size = 48		# button size in px

        self.searchlabel = self.lang['artist']
        self.searchtype = 'artist'
        self.stream_on = self.sourcetype=='stream'
        
        self.master.configure(bg=self.gray)

        self.user_scr_width = int(self.master.winfo_screenwidth())
        self.user_scr_height = int(self.master.winfo_screenheight())

        self.trans_value = 0.7
        self.master.attributes('-alpha', self.trans_value)
        self.master.attributes('-topmost', True)

        self.size_values = [int(0.98 * self.user_scr_width), int(0.56 * self.user_scr_height)]

        # open keyboard in medium size by default (not resizable)
        self.master.overrideredirect(True)
        self.master.geometry(str(self.maxpx_x) + 'x' + str(self.maxpx_y) + '+0+0')
        self.master.config(cursor="none")
        self.master.resizable(False, False)

        self._load_control_icons()
        
        self.row1keys = ["close"] if self.alternative_layout is False else [] #["close", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "back"]
        self.row1keys.extend(self.row1keyb if self.alternative_layout is False else self.row1keyb[:-1])

        self.row2keys = self.row2keyb if self.alternative_layout is False else self.row2keyb[1:-1] # [";", "q", "w", "e", "r", "t", "z", 'u', 'i', 'o', 'p', 'enter']

        self.row3keys = self.row3keyb if self.alternative_layout is False else self.row3keyb[1:] # ["lock", 'a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', 'del']

        self.row4keys = self.row4keyb if self.alternative_layout is False else self.row4keyb[1:] # ["left shift", 'y', 'x', 'c', 'v', 'b', 'n', 'm', ',', '.', '/']

        self.row5keys = ['spacebar', 'alt gr', 'left', 'right'] if self.alternative_layout is False else ['close', self.row3keyb[0], self.row4keyb[0], 'spacebar', 'alt gr', 'back', 'left', 'right', 'enter']

        # buttons for each row
        self.row1buttons = []
        self.row2buttons = []
        self.row3buttons = []
        self.row4buttons = []
        self.row5buttons = []
        
        self.capslock_key_enabled = False

        # prevents frames having inconsistent relative dimensions
        self.master.columnconfigure(0, weight=1)
        for i in range(7):
            self.master.rowconfigure(i, weight=1)

        # shift_key_pressed is True if ALT, CTRL, SHIFT or WIN are held down using right click
        # if it is False, the 4 mentioned keys get released on clicking any other key
        self.shift_key_pressed = False
        self.alt_key_pressed = False

        # create a frame for searchtype info field
        self.infoField = Frame(self.master, height=0.5)
        self.infoField.rowconfigure(0, weight=1)
        self.label = Label(self.infoField, text=self.searchlabel, font = "Arial 36", anchor="w", padx = 10)
        self.label.bind("<Button-1>",lambda e:self.on_labelTap())
        self.label.pack(side='left', expand = True, fill = 'both')
        
        if self.zonetype=='Apple Music':        
            icon = self.control_icons["stream_on"] if self.stream_on else self.control_icons["stream_off"]
            self.sourcetype_btn = TouchFriendlyButton(
                self.infoField,
                None,
                None,
                None,
                None,
                image = icon,
                bg = None,
                fg = None,
                bd = 0,
                command = lambda: self.toggle_sourcetype(), 
                takefocus = 0, 
                activebackground = None,
                activeforeground = None, 
                height = self.icon_btn_size, 
                width = self.icon_btn_size
            )
            self.sourcetype_btn.pack(side='right', fill="y", ipadx = 20)

        # create a frame for input field
        style = ttk.Style(self.master)
        style.configure('My.TEntry', padding=(5,0, 5,0), foreground="blue", insertwidth=4)
        inputField = Frame(self.master, height=1)
        inputField.rowconfigure(0, weight=1)
        self.inp = ttk.Entry(inputField, style='My.TEntry', font=("Arial",30), textvariable = self.inpstr, text="")        
        self.inp.pack(side='left', expand = True, fill = 'both')
        self.inp.focus_force()
        
        #   ROW 1   #

        # create a frame for row1buttons
        keyframe1 = Frame(self.master, height=1)
        keyframe1.rowconfigure(0, weight=1)

        # create row1buttons
        for key in self.row1keys:
            origKey = key
            ind = self.row1keys.index(key)
            if ind == len(self.row1keys) - 1 and self.alternative_layout is False: # back key
                keyframe1.columnconfigure(ind, weight=3)
                key = 'back'
            else:
                keyframe1.columnconfigure(ind, weight=1)
            btn = TouchFriendlyButton(
                keyframe1,
                self.close_bg_normal if key == "close" else self.bg_normal,
                self.close_bg_active if key == "close" else self.bg_active,
                self.fg_normal, 
                self.fg_active,
                font=("Arial", 24),
                border=7,
                bg=self.bg_normal,
                activebackground=self.bg_normal,
                activeforeground=self.fg_normal,
                fg=self.fg_normal,
                width=1,
                relief=RAISED
            )
            self.row1buttons.append(btn)
            self.buttons[key] = self.row1buttons[ind]

            if key == "close":
                self.row1buttons[ind].config(font=("Arial", 24), text="\u2716", bg=self.close_bg_normal, activebackground=self.close_bg_active, padx=12)
            elif key == 'back': # back key
                self.buttonsTranslate[origKey] = key
                if origKey.startswith('u+'):
                    self.row1buttons[ind].config(font=("Arial", 20), text=chr(int(origKey.lower()[2:], 16)), width=5, padx=0, pady=0)
                else:
                    self.row1buttons[ind].config(font=("Arial", 20), text=origKey.title(), width=5)
            else:
                self.row1buttons[ind].config(text = key if len(key) == 1 else key.title())
         
            self.row1buttons[ind].grid(row=0, column=ind, sticky="NSEW")

        #   ROW 2   #

        # create a frame for row2buttons
        keyframe2 = Frame(self.master, width=1)
        keyframe2.rowconfigure(0, weight=1)

        # create row2buttons
        for key in self.row2keys:
            origKey = key
            ind = self.row2keys.index(key)
            if ind == len(self.row2keys) - 1 and self.alternative_layout is False: # enter key
                keyframe2.columnconfigure(ind, weight=2)
                key = "enter"
            else:
                keyframe2.columnconfigure(ind, weight=1)
            btn = TouchFriendlyButton(
                keyframe2,
                self.bg_normal,
                self.bg_active,
                self.fg_normal, 
                self.fg_active,
                font=("Arial", 24),
                border=7,
                bg=self.bg_normal,	# background color is not clicked
                activebackground=self.bg_normal,
                activeforeground=self.fg_normal,
                fg=self.fg_normal,
                width=1,
                relief=RAISED
            )
            self.row2buttons.append(btn)
            self.buttons[key] = self.row2buttons[ind]
            if key == "enter":
                self.buttonsTranslate[origKey] = key
                if origKey.startswith('u+'):
                    self.row2buttons[ind].config(font=("Arial", 25), text=chr(int(origKey.lower()[2:], 16)), width=2)
                else:
                    self.row2buttons[ind].config(font=("Arial", 20), text=origKey.title(), width=3)
            else:
                self.row2buttons[ind].config(text = key if len(key) == 1 else key.title())

            self.row2buttons[ind].grid(row=0, column=ind, sticky="NSEW")

        #   ROW 3   #

        # create a frame for row3buttons
        keyframe3 = Frame(self.master, height=1)
        keyframe3.rowconfigure(0, weight=1)

        # create row3buttons
        for key in self.row3keys:
            origKey = key
            ind = self.row3keys.index(key)
            if ind == 0 and self.alternative_layout is False: # lock key
                key = "lock"
                keyframe3.columnconfigure(ind, weight=2)
            if ind == len(self.row3keys) - 1: # del key
                keyframe3.columnconfigure(ind, weight=2)
                key = "del"
            else:
                keyframe3.columnconfigure(ind, weight=1)
            btn = TouchFriendlyButton(
                keyframe3,
                self.bg_normal,
                self.bg_active,
                self.fg_normal, 
                self.fg_active,
                font=("Arial", 24),
                border=7,
                bg=self.bg_normal,
                activebackground=self.bg_normal,
                activeforeground=self.fg_normal,
                fg=self.fg_normal,
                width=2,
                relief=RAISED
            )                
            self.row3buttons.append(btn)
            self.buttons[key] = self.row3buttons[ind]
            if key == "lock":
                self.buttonsTranslate[origKey] = key
                if origKey.startswith('u+'):
                    self.row3buttons[ind].config(font=("Arial", 28), text=chr(int(origKey.lower()[2:], 16)), width=4, padx=0, pady=0)
                else:
                    self.row3buttons[ind].config(font=("Arial", 20), text=origKey.title(), width=3)
            elif key == "del":
                self.buttonsTranslate[origKey] = key
                self.row3buttons[ind].config(font=("Arial", 20), text=origKey.title(), width=4)
            else:
                self.row3buttons[ind].config(text = key if len(key) == 1 else key.title())

            self.row3buttons[ind].grid(row=0, column=ind, sticky="NSEW")

        #   ROW 4   #

        # create a frame for row4buttons
        keyframe4 = Frame(self.master, height=1)
        keyframe4.rowconfigure(0, weight=1)

        # create row4buttons
        for key in self.row4keys:
            origKey = key
            ind = self.row4keys.index(key)
            if ind == 0 and self.alternative_layout is False: # shift key
                keyframe4.columnconfigure(ind, weight=1)
                key = 'shift'
            else:
                keyframe4.columnconfigure(ind, weight=1)
            btn = TouchFriendlyButton(
                keyframe4,
                self.bg_normal,
                self.bg_active,
                self.fg_normal, 
                self.fg_active,
                font=("Arial", 24),
                border=7,
                bg=self.bg_normal,
                activebackground=self.bg_normal,
                activeforeground=self.fg_normal,
                fg=self.fg_normal,
                width=1,
                relief=RAISED
            )
            self.row4buttons.append(btn)
            self.buttons[key] = self.row4buttons[ind]
            if key == "shift":
                self.buttonsTranslate[origKey] = key
                if origKey.startswith('u+'):
                    self.row4buttons[ind].config(font=("Arial", 28), text=chr(int(origKey.lower()[2:], 16)), width=5, padx=0, pady=0)
                else:
                    self.row4buttons[ind].config(font=("Arial", 20), text=origKey.title(), width=4)                
            else:
                self.row4buttons[ind].config(text = key if len(key) == 1 else key.title())

            self.row4buttons[ind].grid(row=0, column=ind, sticky="NSEW")

        #   ROW 5   #

        # create a frame for row5buttons
        keyframe5 = Frame(self.master, height=1)
        keyframe5.rowconfigure(0, weight=1)

        # create row5buttons
        for key in self.row5keys:
            origKey = key
            ind = self.row5keys.index(key)
            if key == 'spacebar':
                keyframe5.columnconfigure(ind, weight=12 if self.alternative_layout is False else 2) # space key
            else:
                keyframe5.columnconfigure(ind, weight=1)
                
            if ind == 1 and self.alternative_layout is True: # lock key
                key = "lock"
                keyframe5.columnconfigure(ind, weight=2)
            if ind == 2 and self.alternative_layout is True: # shift key
                keyframe5.columnconfigure(ind, weight=1)
                key = 'shift'
                
            btn = TouchFriendlyButton(
                keyframe5,
                self.close_bg_normal if key == "close" else self.bg_normal,
                self.close_bg_active if key == "close" else self.bg_active,
                self.fg_normal, 
                self.fg_active,
                font=("Arial", 24),
                border=7,
                bg=self.bg_normal,
                activebackground=self.bg_normal,
                activeforeground=self.fg_normal,
                fg=self.fg_normal,
                width=1,
                relief=RAISED
            )
            self.row5buttons.append(btn)
            self.buttons[key] = self.row5buttons[ind]

            if key == "lock" or key == "shift":
                self.row5buttons[ind].config(font=("Arial", 20))

            if key == "close":
                self.row5buttons[ind].config(font=("Arial", 24), text="\u2716", bg=self.close_bg_normal, activebackground=self.close_bg_active, padx=12)
            elif key == "lock":
                origKey = self.row3keyb[0]
                self.buttonsTranslate[origKey] = key
                if origKey.startswith('u+'):
                    self.row5buttons[ind].config(font=("Arial", 28), text=chr(int(origKey.lower()[2:], 16)), padx=0, pady=0)
                else:
                    self.row5buttons[ind].config(font=("Arial", 20), text=origKey.title())
            elif key == "shift":
                origKey = self.row4keyb[0]
                self.buttonsTranslate[origKey] = key
                if origKey.startswith('u+'):
                    self.row5buttons[ind].config(font=("Arial", 28), text=chr(int(origKey.lower()[2:], 16)), padx=10, pady=0)
                else:
                    self.row5buttons[ind].config(font=("Arial", 20), text=origKey.title())                
            elif key == "left":
                self.row5buttons[ind].config(text="←")
            elif key == "right":
                self.row5buttons[ind].config(text="→")
            elif key == "spacebar":
                self.row5buttons[ind].config(text="\n")
            elif key == "alt gr":
                self.row5buttons[ind].config(font=("Arial", 20), text="Alt")
            elif key == 'back': # back key
                if self.alternative_layout is True:
                    origKey = self.row1keyb[len(self.row1keyb)-1]
                self.buttonsTranslate[origKey] = key
                if origKey.startswith('u+'):
                    self.row5buttons[ind].config(font=("Arial", 20), text=chr(int(origKey.lower()[2:], 16)), width=2, padx=5)
                else:
                    self.row5buttons[ind].config(font=("Arial", 20), text=origKey.title())
            elif key == "enter":
                if self.alternative_layout is True:
                    origKey = self.row2keyb[len(self.row2keyb)-1]
                self.buttonsTranslate[origKey] = key
                if origKey.startswith('u+'):
                    self.row5buttons[ind].config(font=("Arial", 25), text=chr(int(origKey.lower()[2:], 16)))
                else:
                    self.row5buttons[ind].config(font=("Arial", 20), text=origKey.title())
            else:
                self.row5buttons[ind].config(text=key.title())

            self.row5buttons[ind].grid(row=0, column=ind, sticky="NSEW")

        # add the frames to the main window
        self.infoField.grid(row=0, sticky="NSEW", padx=9, pady=1)
        inputField.grid(row=1, sticky="NSEW", padx=9, pady=1)
        keyframe1.grid(row=2, sticky="NSEW", padx=9, pady=6)
        keyframe2.grid(row=3, sticky="NSEW", padx=9)
        keyframe3.grid(row=4, sticky="NSEW", padx=9)
        keyframe4.grid(row=5, sticky="NSEW", padx=9)
        keyframe5.grid(row=6, padx=9, sticky="NSEW")

    # add functionality to keyboard
    def engine(self):
        self.master.title("Virtual Keyboard")
        for key in self.row1keys:
            ind = self.row1keys.index(key)
            self.row1buttons[ind].config(command=lambda x=key: self.vpresskey(x))

        for key in self.row2keys:
            ind = self.row2keys.index(key)
            self.row2buttons[ind].config(command=lambda x=key: self.vpresskey(x))

        for key in self.row3keys:
            ind = self.row3keys.index(key)
            self.row3buttons[ind].config(command=lambda x=key: self.vpresskey(x))

        for key in self.row4keys:
            ind = self.row4keys.index(key)
            key = self.buttonsTranslate[key] if key in self.buttonsTranslate else key
            self.row4buttons[ind].config(command=lambda x=key: self.vpresskey(x))
            if key == "shift":
                self.row4buttons[ind].config(command=lambda: self.vupdownkey(event="<Button-1>", type='shift'))
                self.row4buttons[ind].bind('<Button-3>', lambda event="<Button-3>", type='shift': self.vupdownkey(event, type))

        for key in self.row5keys:
            ind = self.row5keys.index(key)
            key = self.buttonsTranslate[key] if key in self.buttonsTranslate else key
            self.row5buttons[ind].config(command=lambda x=key: self.vpresskey(x))
            if key == "shift":
                self.row5buttons[ind].config(command=lambda: self.vupdownkey(event="<Button-1>", type='shift'))
                self.row5buttons[ind].bind('<Button-3>', lambda event="<Button-3>", type='shift': self.vupdownkey(event, type))
            if key == "alt gr":
                self.row5buttons[ind].config(command=lambda: self.vupdownkey("<Button-1>", type='alt'))
                self.row5buttons[ind].bind('<Button-3>', lambda event="<Button-3>", type='alt': self.vupdownkey(event, type))

    def error_message(self, message):
        self.flexprint('vkeyb ==> error_message: ' + message)
        self.showSpinner = False
        self.master = Tk()
        self.trans_value = 0.7
        self.master.attributes('-alpha', self.trans_value)
        self.master.attributes('-topmost', True)
        self.master.overrideredirect(True)
        self.master.geometry(str(self.maxpx_x) + 'x' + str(self.maxpx_y) + '+0+0')
        self.master.config(cursor="none", background=self.infopage_bg_color)
        self.master.resizable(False, False)
        parent = Frame(self.master)
        fontsize = int(self.maxpx_x / len(message))
        Label(parent, text = message, font = "Arial " + str(fontsize), fg=self.infopage_fg_color, bg=self.infopage_bg_color).pack(fill="x")
        parent.pack(expand=1)
        self.master.after(4000, self.close)
        self.master.mainloop()

    def close(self):
        self.showSpinner = False
        self.master.destroy()
        self.on_close()

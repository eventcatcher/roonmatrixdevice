#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# ItemList Class - display list of selectable items
# Roonmatrix extension class
# version 1.0.0, date: 18.07.2025
#
# © Stephan Wilhelm, coded @ 2025
#
# copy to /home/coverplayer/FTP
#

from tkinter import *
import tkinter.ttk as ttk
import tkinter.font as tkFont
from tkinter import messagebox
from sys import exit as end
from os import system, path
from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import time
from rich import print
import sys
import logging

# if user has the keyboard module installed
has_keyboard = True

class TouchTreeview(ttk.Treeview):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self._start_y = 0
        self._scroll_start = 0.0
        self._moved = False
        self._tap_item = None
        self.ignore_select = False
        self.maxRowCount = 7 # too much rows and maxsize too big results in a exception: BadAlloc (insufficient resources for operation)
        self.rowheight = 90 # maxsize, for bigger height exception throws: BadAlloc (insufficient resources for operation)
        #self.scroll_speed = 1.0 / ((self.rowheight * self.maxRowCount) / 0.7)
        self.scroll_speed = 0.001111111

        self.bind("<ButtonPress-1>", self.on_touch_start)
        self.bind("<B1-Motion>", self.on_touch_scroll)
        self.bind("<ButtonRelease-1>", self.on_touch_end)
        self.bind("<<TreeviewSelect>>", self.on_select_event)

    def setItems(self, items):
        self.scroll_speed = 1.0 / self.rowheight / items

    def on_touch_start(self, event):
        self._start_y = event.y
        self._scroll_start = self.yview()[0]
        self._moved = False
        self._tap_item = self.identify_row(event.y)
        self.ignore_select = False
        return "break"

    def on_touch_scroll(self, event):
        dy = event.y - self._start_y
        delta_fraction = -dy * self.scroll_speed
        new_view = min(max(self._scroll_start + delta_fraction, 0.0), 1.0)
        self.yview_moveto(new_view)

        if abs(dy) > 5:
            self._moved = True
            self.ignore_select = True  # Auswahl unterdrücken
        return "break"

    def on_touch_end(self, event):
        if not self._moved and self._tap_item:
            self.ignore_select = False  # Selektion erlauben
            self.selection_set(self._tap_item)
            self.focus(self._tap_item)
        else:
            self.ignore_select = True  # Auswahl ignorieren
            self.selection_remove(self.selection())
        return "break"

    def on_select_event(self, event):
        if self.ignore_select:
            self.selection_remove(self.selection())
            return "break"

class ItemList:
    def init(self):

        # Main Window
        self.master = Tk()
        self.inpstr = StringVar()
        self.minLength = 3
        self.maxRowCount = 7 # too much rows and maxsize too big results in a exception: BadAlloc (insufficient resources for operation)
        self.rowheight = 90 # maxsize, for bigger height exception throws: BadAlloc (insufficient resources for operation)
        self.fontSize = 24
        self.gray = "#383838"
        self.maxpx_x = 720 # screen width in px
        self.maxpx_y = 720 # screen height in px

        self.master.configure(bg=self.gray)

        self.trans_value = 0.7
        self.master.attributes('-alpha', self.trans_value)
        self.master.attributes('-topmost', True)

        # open keyboard in medium size by default (not resizable)
        self.master.overrideredirect(True)
        self.master.geometry(str(self.maxpx_x) + 'x' + str(self.maxpx_y) + '+0+0')
        self.master.config(cursor="none")
        self.master.resizable(False, False)

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
    
        canvas = Canvas(master, width=self.maxpx_x, height=self.maxpx_y, background="black", bd=0, highlightthickness=0, relief='ridge')
        canvas.pack(fill=BOTH, expand=1)
        canvas.create_text(self.maxpx_x / 2, self.maxpx_y / 2, width = self.maxpx_x / 3 * 2, fill = "white", font = "Times 36 italic bold", anchor = 'center', justify = 'center', text = self.lang['searchfor'] + '\n' + self.search)
                        
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
    
    # an exception to get the symbols ? and _ from the keyboard module's virtual hotkeys
    # for some reason "SHIFT+-" or "SHIFT+/" don't work :/
    def quest_press(self, x):
        if self.row5buttons[0].cget('relief') == SUNKEN:
            if x == "-":
                self.vpresskey("shift+_")
            elif x == "/":
                self.vpresskey("shift+?")
        else:
            self.vpresskey(x)

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

    def refresh_row_tags(self):
        children = self.listbox.get_children()
        for index, item in enumerate(children):
            tag = 'evenrow' if index % 2 == 0 else 'oddrow'
            self.listbox.item(item, tags=(tag,))

    def engine(self):
        self.master.columnconfigure(0, weight=1)
        style = ttk.Style(self.master)
        style.configure('My.TEntry', padding=(10,0, 10,0), foreground="blue")
        style.configure("mystyle.Treeview", highlightthickness=0, bd=0, background="white", foreground="black", fieldbackground="white", font=('Arial', self.fontSize), rowheight=self.rowheight)

        labelField = Frame(self.master, height=1.4)
        labelField.rowconfigure(0, weight=1)
        Label(labelField, text = self.meta['label'], font = "Arial 36", anchor="w", padx = 10).pack(side='left', expand = True, fill = 'both', ipady = 15)

        if self.meta['listname'] is not None:
            listNameField = Frame(self.master, height=1)
            listNameField.rowconfigure(0, weight=1)
            self.inp = ttk.Entry(listNameField, style='My.TEntry', font=("Arial",24), textvariable = self.inpstr, text="bebe")
            self.inp.pack(side='left', expand = True, fill = 'both', ipady = 20)
            self.inpstr.set(self.meta['listname'])
            self.inp.delete(0, END) #deletes the current value
            self.inp.insert(0, self.meta['listname']) #inserts new value assigned by 2nd parameter

        #   ROW 1
        listFrame = Frame(self.master, height=1)
        listFrame.rowconfigure(0, weight=1)

        self.listbox = TouchTreeview(listFrame, style="mystyle.Treeview", show="tree", height=self.maxRowCount)
                        
        self.listbox.pack(side="left", fill="both", expand=True)

        for index, item in enumerate(self.items):
            tag = 'evenrow' if index % 2 == 0 else 'oddrow'
            if isinstance(item, str) is True:
                self.listbox.insert('', END, text=item, tags = (tag,))
            else:
                if self.meta['type']=='tracks' and 'artist' in item and item['artist'] is not None:
                    self.listbox.insert('', END, text=item['name'] + ' [' + item['artist'] + ']', iid = item['id'])
                else:
                    self.listbox.insert('', END, text=item['name'], iid = item['id'])
        self.listbox.setItems(len(self.items))
    
        self.listbox.tag_configure('evenrow', background='#f0f0f0')
        self.listbox.tag_configure('oddrow', background='white')
        self.listbox.bind('<<TreeviewSelect>>', self.on_select)

        self.listbox.bind("<Visibility>", lambda e: self.refresh_row_tags())
        #self.listbox.bind("<<TreeviewSelect>>", self.on_select)
        self.listbox.bind("<Motion>", lambda e: self.refresh_row_tags())

        # add the frames to the main window
        labelField.grid(row=0, sticky="NSEW", padx=9, pady=1)
        if self.meta['listname'] is None:
            listFrame.grid(row=1, sticky="NSEW", padx=9, pady=2)
        else:
            listNameField.grid(row=1, sticky="NSEW", padx=9, pady=1)
            listFrame.grid(row=2, sticky="NSEW", padx=9, pady=2)

		# close button at the bottom right        
        btn_size = 60
        bgcolor = "#222222"
        scriptpath = path.dirname(__file__) + '/'
        iconpath = scriptpath + "icons/close.png"
        
        self.close_icon_image = PhotoImage(master = self.master, file = iconpath)
        self.close_btn = Button(
            self.master,
            image = self.close_icon_image,
            bg = bgcolor,
            activebackground = bgcolor, 
            bd = 0,
            command = self.do_close,
            takefocus = False, 
            width = btn_size,
            height = btn_size
        )        
        self.close_btn.place(relx = 1.0, rely = 1.0, anchor = "se", x = 0, y = 0, width = btn_size, height = btn_size)

    def on_select(self, event):
        if self.listbox.ignore_select:
            return

        self.refresh_row_tags()
        selected_item = self.listbox.focus()  # ID des selektierten Elements
        item_text = self.listbox.item(selected_item, 'text')
        self.flexprint(f"itemlist ==> type: {self.meta['type']}, on_select: {item_text}, iid: {selected_item}")

        if self.meta['type'] == 'tracks' or self.meta['type'] == 'radios':
            self.flexprint('itemlist ==> track selected: ' + str(item_text))
            #self.master.destroy()
        else:         
            self.showSpinner = True
            self.master.destroy()
            self.search = item_text
            executor = ThreadPoolExecutor(max_workers=2)
            job = executor.submit(self.circleProgress)

        if isinstance(self.items[0], str) is True:
            self.on_list_selection(self.meta, item_text)
        else:
            self.on_list_selection(self.meta, item_text, selected_item)
        self.showSpinner = False

    def do_close(self):
        self.flexprint('itemlist ==> do_close (and destroy)')
        self.on_close()
        self.master.destroy()

    def error_message(self, message):
        self.flexprint('itemlist ==> error_message: ' + message)
        self.showSpinner = False
        self.master = Tk()
        self.trans_value = 0.7
        self.master.attributes('-alpha', self.trans_value)
        self.master.attributes('-topmost', True)
        self.master.overrideredirect(True)
        self.master.geometry(str(self.maxpx_x) + 'x' + str(self.maxpx_y) + '+0+0')
        self.master.config(cursor="none", background="black")
        self.master.resizable(False, False)
        parent = Frame(self.master)
        fontsize = int(self.maxpx_x / len(message))
        Label(parent, text = message, font = "Arial " + str(fontsize), fg="white", bg="black").pack(fill="x")
        parent.pack(expand=1)
        self.master.after(4000, self.close)
        self.master.mainloop()

    def close(self):
        self.showSpinner = False
        self.master.destroy()
        self.on_close()
    
    # start item list
    def start(self, width, height, meta, items, lang, itemclick_callback, close_callback):
        self.log = True      # log infos on or off
        
        self.flexprint('itemlist ==> start, meta' + str(meta) + ', items: ' + str(len(items)))

        self.maxpx_x = width
        self.maxpx_y = height
        self.meta = meta
        self.items = items
        self.lang = lang
        self.on_list_selection = itemclick_callback
        self.on_close = close_callback
        
        self.search = ''
        
        self.init()
        self.engine()
        
        #self.master.mainloop()


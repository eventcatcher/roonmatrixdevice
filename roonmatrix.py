#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Roonmatrix App - display roon, spotify and apple music playout informations and more on 8x8 led matrix display
# version 1.1.0, date: 11.07.2025
#
# show what is playing on roon zones and via webservers on Spotify and Apple Music
# show actual weather, rss feeds and clock
#
# © Stephan Wilhelm, Bielefeld, Germany, coded @ 2024 - 2025
#
# copy to /home/rmuser/FTP
# config file: /usr/local/Roon/etc/roon_api.ini
#
# stop service:  sudo systemctl stop roonmatrix.service
# start service: sudo systemctl start roonmatrix.service
# live log:      journalctl -f

scriptVersion = '1.1.0, date: 11.07.2025'

from threading import Timer
from datetime import datetime, timedelta, timezone
from dateutil import tz
import time
import requests
import argparse
import RPi.GPIO as GPIO
from ast import literal_eval
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib import parse
import configparser
import json
from os import path, system, environ, stat, remove, rename
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio
from functools import wraps
import threading
from math import ceil
import psutil
import sdnotify
import socket
import ssl
import urllib3
from unidecode import unidecode
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import uvicorn
import subprocess
import shlex
import crypt
from rich import print
import traceback
import logging
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from collections import OrderedDict
from operator import is_not
from functools import partial
from pathlib import Path
import hashlib
from aiohttp import ClientSession, ClientTimeout

from luma.led_matrix.device import max7219
from luma.core.interface.serial import spi, noop
from luma.core.legacy import text, textsize
from luma.core.legacy.font import proportional, CP437_FONT
from luma.core.render import canvas
from luma.core.virtual import viewport
from luma.core.sprite_system import framerate_regulator

from roonapi import RoonApi, RoonDiscovery
from weatherbit.api import Api
import feedparser

debug = False   # log debug messages (memory and variable information)
startlog = True # log start and config information
log = True      # log infos on or off
errorlog = True # log errors
display_cover = False
downloadserver = 'https://www.wilhelm-devblog.de/translations_device/'
base_translations_path = '../FTP/translations/'

def init_logging():
    max_size_in_mb = 10
    fn = '/home/rmuser/FTP/logs/roonmatrix.log'
    if display_cover is True:
        fn = '/home/coverplayer/FTP/logs/roonmatrix.log'
    
    rfh = logging.handlers.RotatingFileHandler(
        filename = fn, 
        mode = 'a',
        maxBytes = max_size_in_mb * 1024 * 1024,
        backupCount = 2,
        encoding = None,
        delay=0
    )
        
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)-25s %(levelname)-8s %(message)s",
        datefmt="%y-%m-%d %H:%M:%S",
        handlers=[
            rfh
        ]
    )

base_path = '/usr/local/Roon/etc/'
# core id and token files
idfile = base_path + 'coreid.txt'
tokenfile = base_path + 'roontoken.txt'
# read config file
configFile = base_path + 'roon_api.ini'
print('read main ini')
config = configparser.ConfigParser()
config.read(configFile)

if 'display_cover' in config['SYSTEM']:
    display_cover = eval(config['SYSTEM']['display_cover']) # true: show cover on screen (device is started in desktop mode), false: work as led scrollbar (device is started in cli mode)
else:
    display_cover = False

# init cover image viewer
try:
    # imports to display image on screen
    if display_cover is True:
        environ["DISPLAY"] = ":0"

    if "DISPLAY" not in environ:
        display_cover = False
        raise EnvironmentError("No display available")

    import tkinter as tk
    from PIL import Image, ImageTk # install PIL with: pip3 install pillow, and: sudo apt-get install python3-pil.imagetk
    from io import BytesIO
    from coverplayer import Coverplayer
    root = tk.Tk()
    root.destroy()
except EnvironmentError as e:
    print(f"[magenta][INFO] GUI not found (headless system): {e}[/magenta]")
    display_cover = False
except Exception as e:
    print(f"[magenta][ERROR] Error on import of packages to display cover image: {e}[/magenta]")
    display_cover = False

if display_cover is True:
    init_logging()
    logger = logging.getLogger('main')
    serial = None
else:
    logger = None
    serial = spi(port=0, device=0, gpio=noop()) # object of serial connection (luna)

def flexprint(str, objStr = None):
    if objStr is None:
        if sys.stdout.isatty() or logger is None:
            print(str)
        else:
            logger.info(str)
    else:
        if sys.stdout.isatty() or logger is None:
            print(str, objStr)
        else:
            logger.info(str, objStr)

async def head_url(session, reqobj):
   # Helper function to fetch a single URL asynchronously
    try:
        name = reqobj['name']
        url = reqobj['url']
        async with session.head(url) as response:
            text = await response.text()
            return {
                'url': url,
                'name': name,
                'status': response.status,
                'length': len(text),
                'text': text
            }
    except Exception as e:
        return {
            'url': url,
            'name': name,
            'error': str(e)
        }

async def fetch_url(session, reqobj):
   # Helper function to fetch a single URL asynchronously
    try:
        name = reqobj['name']
        url = reqobj['url']
        if 'data' in reqobj:
            async with session.post(url, data=reqobj['data']) as response:
                text = await response.text()
                return {
                    'url': url,
                    'name': name,
                    'status': response.status,
                    'length': len(text),
                    'text': text
                }
        else:
            async with session.get(url) as response:
                text = await response.text()
                return {
                    'url': url,
                    'name': name,
                    'status': response.status,
                    'length': len(text),
                    'text': text
                }
    except Exception as e:
        return {
            'url': url,
            'name': name,
            'error': str(e)
        }

async def async_web_requests(requestlist, get_head, timeout):
    # Non-blocking implementation that fetches URLs concurrently
    timeout_obj = ClientTimeout(total = timeout)
    async with ClientSession(timeout = timeout_obj) as session:
        if get_head is True:
            tasks = [head_url(session, reqobj) for reqobj in requestlist]
        else:
            tasks = [fetch_url(session, reqobj) for reqobj in requestlist]
        return await asyncio.gather(*tasks)

def async_web_requests_with_timing(requestlist):
    req_start_time = time.time()
    async_results = asyncio.run(async_web_requests(requestlist, False, webserver_url_request_timeout))
    req_end_time = time.time()
    if debug is True:
        print(f"async_web_requests results ({req_end_time - req_start_time:.2f} seconds):", async_results)
    else:
        print(f"async_web_requests time: ({req_end_time - req_start_time:.2f} seconds)")
    return async_results

def get_countrycode_from_public_ip():
    cc = 'en'
    try:
        requestlist = [{'name':'ident.me','url':'https://ident.me/json'}]            
        async_web_response = async_web_requests_with_timing(requestlist)
        if len(async_web_response) > 0 and 'error' not in async_web_response[0]:
            ipdata = async_web_response[0]['text']
    
            if len(ipdata) > 2 and ipdata[:1] == '{' and ipdata[-1:] == '}':
                jsonObj = json.loads(ipdata)
                cc = str(jsonObj['cc']).lower()
        else:
            flexprint('[red]setHostname with empty response[/red]')
    except Exception as e:
        flexprint('[red]setHostname error: ' + str(e) + '[/red]')
    return cc

def creation_date(path_to_file):
    return path.getctime(path_to_file)
    

def translation_exist(cc, update):
    current_path = Path(__file__).parent
    fileName = 'translations_' + cc + '.ini'
    relative_path = base_translations_path + (('update_' + fileName) if update is True else fileName)
    
    file_path = str((current_path / relative_path).resolve())
    exist = Path(file_path).is_file()
    if exist is False:
        return [exist]
    
    creationDate = creation_date(file_path)
    creationDate = datetime.fromtimestamp(creationDate)
    if debug is True:
        flexprint('creationDate_' + ('update' if update is True else 'main') + ': ' + str(format(creationDate.isoformat())))

    return [exist, creationDate]

def translation_fileinfo(cc, update):
    current_path = Path(__file__).parent
    fileName = 'translations_' + cc + '.ini'
    relative_path = base_translations_path + (('update_' + fileName) if update is True else fileName)
    
    file_path = str((current_path / relative_path).resolve())
    exist = Path(file_path).is_file()
    
    if exist is True:
        creationDate = creation_date(file_path)
        creationDate = datetime.fromtimestamp(creationDate)

        with open(file_path, 'r') as fileRead:
            langdata = fileRead.read()
        hash = hashlib.md5(langdata.encode()).hexdigest()

        return [exist, creationDate, hash, file_path]
    else:
        return [exist]

def get_translation_path(cc):
    current_path = Path(__file__).parent
    relative_path = base_translations_path + 'translations_' + cc + '.ini'
    
    file_path = (current_path / relative_path).resolve()
    return file_path

def delete_translation(cc, update):
    current_path = Path(__file__).parent
    filename = 'translations_' + cc + '.ini'
    local_filename = ('update_' + filename) if update is True else filename
    relative_path = base_translations_path + local_filename
    file_path = str((current_path / relative_path).resolve())
    remove(file_path)

def update_translation(cc):
    current_path = Path(__file__).parent
    relative_path_old = base_translations_path + 'update_translations_' + cc + '.ini'
    relative_path_new = base_translations_path + 'translations_' + cc + '.ini'

    file_path_old = str((current_path / relative_path_old).resolve())
    file_path_new = str((current_path / relative_path_new).resolve())

    delete_translation(cc, False)
    rename(file_path_old, file_path_new)

def download_translation(cc, update):
    remote_filename = 'translations_' + cc + '.ini'
    local_filename = ('update_' + remote_filename) if update is True else remote_filename
    try:
        requestlist = [{'name':'devblog','url':downloadserver + remote_filename}]            
        async_web_response = async_web_requests_with_timing(requestlist)
        if len(async_web_response) > 0 and 'error' not in async_web_response[0]:
            langdata = async_web_response[0]['text']

            current_path = Path(__file__).parent
            relative_path = base_translations_path + local_filename
    
            file_path = str((current_path / relative_path).resolve())
            with open(file_path, 'w') as fileRes:
                fileRes.write(langdata)
            fileinfo = translation_exist(cc, update)
            exist = fileinfo[0]
            if exist:
                creationDate = fileinfo[1]
                hash = hashlib.md5(langdata.encode()).hexdigest()

                return [exist, creationDate, hash, file_path]
            else:
                return [exist]
        else:
            flexprint('[red]translation download error: empty response[/red]')
            return None
    except Exception as e:
        flexprint('[red]translation download error: ' + str(e) + '[/red]')
    return None

translation_hash = config['LANGUAGE']['translation_hash']
countrycode = config['SYSTEM']['countrycode']
webserver_url_request_timeout = int(config['WEBSERVERS']['webserver_url_request_timeout'])

if countrycode == 'auto' or countrycode == '':
    countrycode = get_countrycode_from_public_ip()
flexprint('countrycode: ' + countrycode)

updateHash = ''
fileinfo = translation_exist(countrycode, False)
exist = fileinfo[0]
if exist:
    translation_changed = False
    hash_main = ''
    max_download_age_in_days = -1
    download_age_in_days = -1
    fileinfo_main = translation_fileinfo(countrycode, False)
    if len(fileinfo_main) > 2:
        creationDate_main = fileinfo[1]
        hash_main = fileinfo_main[2]
        delta = datetime.now() - creationDate_main
        download_age_in_days = delta.days
        flexprint('days since last translation download: ' + str(download_age_in_days))
    if debug is True:
        flexprint('fileinfo_main: ' + str(fileinfo_main))
    
    if download_age_in_days > max_download_age_in_days:
        fileinfo = download_translation(countrycode, True)
        if fileinfo is not None:
            if debug is True:
                flexprint('fileinfo: ' + str(fileinfo))
            exist = fileinfo[0]
            creationDate = fileinfo[1] if len(fileinfo) > 1 else ''
            hash = fileinfo[2] if len(fileinfo) > 2 else ''
            updateFile = fileinfo[3] if len(fileinfo) > 3 else ''
            if hash_main == hash:
                flexprint('hash is equal (' + hash + ') => file not changed')
                delete_translation(countrycode, True)
            else:
                flexprint('hash is NOT equal (' + hash_main + ' / ' + hash + ') => take updated file')
                translation_changed = True
                update_translation(countrycode)
                hash_main = hash

    overrideFile = get_translation_path(countrycode)
    updateHash = hash_main
    load_with_override = (translation_hash != updateHash)
    flexprint('read main ini with override, translation_changed: ' + str(translation_changed) + ', load_with_override: ' + str(load_with_override))
    if load_with_override is True:
        config.read([configFile, str(overrideFile)])
    else:
        config.read([configFile])

else:
    fileinfo = download_translation(countrycode, False)
    if fileinfo is not None:
        if debug is True:
            flexprint('fileinfo: ' + str(fileinfo))
        exist = fileinfo[0]
        creationDate = fileinfo[1] if len(fileinfo) > 1 else ''
        hash = fileinfo[2] if len(fileinfo) > 2 else ''
        overrideFile = fileinfo[3] if len(fileinfo) > 3 else ''
        if exist is True and overrideFile is not None and len(overrideFile) > 0:
            updateHash = hash
            config.read([configFile, overrideFile])

hostName = socket.gethostname()

sys.stdout.reconfigure(encoding='utf-8')
from_zone = tz.tzutc()
to_zone = tz.tzlocal()

n = sdnotify.SystemdNotifier() # init watchdog notifier

weather_show = eval(config['WEATHER']['weather_show']) # show weather data (True) or no (False)
location = config['WEATHER']['location'] # city name to display weather data for
weatherbit_api_key = config['WEATHER']['weatherbit_api_key'] # weatherbit api key
weather_update_interval = int(config['WEATHER']['weather_update_interval']) * 60 # time interval in seconds to update weather data (max. 50 API calls per day)
weather_api = Api(weatherbit_api_key) # weatherbit api key
with_feel_temperature = eval(config['WEATHER']['with_feel_temperature']) # true: show feel temperature in celsius
with_rain = eval(config['WEATHER']['with_rain']) # true: show rain in mm/hr if rain data is available
with_wind_spd = eval(config['WEATHER']['with_wind_spd']) # true: show wind speed in km/h
with_wind_dir = eval(config['WEATHER']['with_wind_dir']) # true: show wind direction
with_humidity = eval(config['WEATHER']['with_humidity']) # true: show humidity in percent
with_pressure = eval(config['WEATHER']['with_pressure']) # true: show pressure in hPa
with_clouds = eval(config['WEATHER']['with_clouds']) # true: show clouds in percent if cloud data is available
with_snow = eval(config['WEATHER']['with_snow']) # true: show snow in mm/hr if snow data is available
with_uv = eval(config['WEATHER']['with_uv']) # true: show ultraviolet radiation in a range of 0-11 
with_sunrise = eval(config['WEATHER']['with_sunrise']) # true: show time of sunrise
with_sunset = eval(config['WEATHER']['with_sunset']) # true: show time of sunset
with_description = eval(config['WEATHER']['with_description']) # true: show short weather description text

webservers_show = eval(config['WEBSERVERS']['webservers_show']) # show spotify or apple music data (True) or not (False)
force_webserver_update = eval(config['WEBSERVERS']['force_webserver_update']) # true: force updating output message if webserver data (local running Spotify and Apple Music) is updated (interrupt and refresh output instantly)
force_active_webserver_zone_only = eval(config['WEBSERVERS']['force_active_webserver_zone_only']) # true: force updating output message only if the active zone is of webserver type and is updating
webcheck_update_interval = int(config['WEBSERVERS']['webcheck_update_interval']) # interval in seconds the webservers will check for playouts if force_webserver_update is True
webservers_zones = literal_eval(config['WEBSERVERS']['zones']) # list of webservers zones (fields: name,  url) to get playout data from local running apple music and spotify
webserver_head_request_timeout = int(config['WEBSERVERS']['webserver_head_request_timeout']) # time in seconds a webserver should send a response to head request (onlinecheck)
webserver_url_request_timeout = int(config['WEBSERVERS']['webserver_url_request_timeout']) # time in seconds a webserver should send a response to url request
spotify_client_id = config['WEBSERVERS']['spotify_client_id'] if 'spotify_client_id' in config['WEBSERVERS'] else '' # spotify web api client id
spotify_client_secret = config['WEBSERVERS']['spotify_client_secret'] if 'spotify_client_secret' in config['WEBSERVERS'] else '' # spotify web api client secret

roon_show = eval(config['ROON']['roon_show']) # show roon data (True) or not (False)
force_roon_update = eval(config['ROON']['force_roon_update']) # true: force updating output message if roon zone info is updated (interrupt and refresh output instantly)
force_active_roon_zone_only = eval(config['ROON']['force_active_roon_zone_only']) # true: force updating output message only if the active zone is of roon type and is updating
discovery_delay = int(config['ROON']['discovery_delay']) # delay after first roon discover call to wait a discover.stop is completed
core_ip = config['ROON']['core_ip'] # ip of the roon core (server). if empty the ip and port is searched and saved automatically by RoonDiscovery call
core_port = config['ROON']['core_port'] # port of the roon core (server). if empty the ip and port is searched and saved automatically by RoonDiscovery call

config['SYSTEM']['hostname'] = hostName # override roonmatrix hostname with actual value
config['SYSTEM']['password'] = '********' # set roonmatrix password placeholder with default value

led_modules = int(config['SYSTEM']['led_modules']) # number of led matrix modules (8x8 led)

led_block_orientation = int(config['SYSTEM']['led_block_orientation']) # led block_orientation in degrees
led_rotate = int(config['SYSTEM']['led_rotate']) # led rotation
led_inreverse = int(config['SYSTEM']['led_inreverse']) # led blocks arranged in reverse order
led_scroll_delay = float(config['SYSTEM']['led_scroll_delay']) # delay time in milliseconds to delay next column scroll
led_vertical_scroll_delay = float(config['SYSTEM']['led_vertical_scroll_delay']) # delay time in milliseconds to delay next vertical line  scroll
led_contrast = int(config['SYSTEM']['led_contrast']) # led contrast between 0-255

controlswitch_gpio_top = int(config['SYSTEM']['controlswitch_gpio_top']) # button gpio number, for direction top
controlswitch_gpio_down = int(config['SYSTEM']['controlswitch_gpio_down']) # button gpio number, for direction down
controlswitch_gpio_left = int(config['SYSTEM']['controlswitch_gpio_left']) # button gpio number, for direction left
controlswitch_gpio_center = int(config['SYSTEM']['controlswitch_gpio_center']) # button gpio number, for direction center
controlswitch_gpio_right = int(config['SYSTEM']['controlswitch_gpio_right']) # button gpio number, for direction right
controlswitch_bouncetime = int(config['SYSTEM']['controlswitch_bouncetime']) # button debounce time in ms

internet_connection_timeout = int(config['SYSTEM']['internet_connection_timeout']) # request timeout in seconds
internet_connection_url = config['SYSTEM']['internet_connection_url'] # url used to check if internet is available
separator = ' ' + config['SYSTEM']['separator'] + ' ' # string which is used to separate the different content messages
control_zone = config['SYSTEM']['control_zone'] # name of default roon or webserver zone (example: MacStudio-Spotify, which is a concatenation of webserver zone name, hyphen, and app name like Spotify or AppleMusic) the buttons will control (play, pause, next, track before, shuffle)
zone_control_map = literal_eval(config['SYSTEM']['zone_control_map']) # map names of control zones to shorter variant (for matrix with less modules)
zone_control_timeout = int(config['SYSTEM']['zone_control_timeout']) # max time in seconds the zone control mode is displayed (before the message playout restarts)
map_zone_control = eval(config['SYSTEM']['map_zone_control']) # true: map zone control names, false: no mapping
exclusive_audio_mode = eval(config['SYSTEM']['exclusive_audio_mode']) # true: display audio messages, show other content (rss, weather) if no audio is played, false: show all
exclusive_active_zone = eval(config['SYSTEM']['exclusive_active_zone']) # true: display only active zone
music_required = eval(config['SYSTEM']['music_required']) # true: music playing is required to display anything (silent if no music is playing)
show_zone = eval(config['SYSTEM']['show_zone']) # true: show zone name of audio channel, false: show no zone name
show_album = eval(config['SYSTEM']['show_album']) # true: show album, false: show only artist and track
vertical_output = eval(config['SYSTEM']['vertical_output']) # true: display vertical (with vertical scrolling line by line)
vertical_scroll_delay = int(config['SYSTEM']['vertical_scroll_delay']) # vertical scroll delay in seconds
show_vertical_music_label = eval(config['SYSTEM']['show_vertical_music_label']) # true: show music label (artist, album, track), false: show without music label (supported only in vertical scrolling mode)
datetime_show = eval(config['SYSTEM']['datetime_show']) # true: show date and time in output message
datetime_only_time = eval(config['SYSTEM']['datetime_only_time']) # true: show only time part of datetime in output message
socket_timeout = int(config['SYSTEM']['socket_timeout']) # socket timeout in seconds
screensaver_seconds = int(config['SYSTEM']['screensaver_seconds']) # screensaver timeout in seconds (0 = screensaver off)
display_auto_wakeup = eval(config['SYSTEM']['display_auto_wakeup']) # wakeup display on track updates
countrycode = config['SYSTEM']['countrycode'] # two char country code like de or en to load the translations specific for this language. auto = get code from public ip address

playing_headline = config['LANGUAGE']['playing_headline'] # headline text to display in front of audio informations
conversions = literal_eval(config['LANGUAGE']['conversions']) # language specific special utf-8 code char replacing to ascii code
translate_map = {} # define key value map to use for language translation
for key, val in conversions.items():
    translate_map[ord(key)] = val
deg_to_compass = literal_eval(config['LANGUAGE']['deg_to_compass']) # language specific transformation of degrees to compass like direction names in ascii code
weather_description = literal_eval(config['LANGUAGE']['weather_description']) # translation of weather descriptions text
weather_properties = literal_eval(config['LANGUAGE']['weather_properties']) # translation of weather properties text
messages = literal_eval(config['LANGUAGE']['messages']) # translation of messages text

coverplayer_lang = literal_eval(config['LANGUAGE']['coverplayer']) # translation of text for coverplayer device
row1keyb = literal_eval(config['LANGUAGE']['row1keyb']) if 'row1keyb' in config['LANGUAGE'] else [] # language specific virtual keyboard row 1
row2keyb = literal_eval(config['LANGUAGE']['row2keyb']) if 'row2keyb' in config['LANGUAGE'] else [] # language specific virtual keyboard row 2
row3keyb = literal_eval(config['LANGUAGE']['row3keyb']) if 'row3keyb' in config['LANGUAGE'] else [] # language specific virtual keyboard row 3
row4keyb = literal_eval(config['LANGUAGE']['row4keyb']) if 'row4keyb' in config['LANGUAGE'] else [] # language specific virtual keyboard row 4
row1keyb_shift = literal_eval(config['LANGUAGE']['row1keyb_shift']) if 'row1keyb_shift' in config['LANGUAGE'] else [] # language specific virtual keyboard shift row 1
row2keyb_shift = literal_eval(config['LANGUAGE']['row2keyb_shift']) if 'row2keyb_shift' in config['LANGUAGE'] else [] # language specific virtual keyboard shift row 2
row4keyb_shift = literal_eval(config['LANGUAGE']['row4keyb_shift']) if 'row4keyb_shift' in config['LANGUAGE'] else [] # language specific virtual keyboard shift row 4
row1keyb_alt = literal_eval(config['LANGUAGE']['row1keyb_alt']) if 'row1keyb_alt' in config['LANGUAGE'] else [] # language specific virtual keyboard alt row 1
row2keyb_alt = literal_eval(config['LANGUAGE']['row2keyb_alt']) if 'row2keyb_alt' in config['LANGUAGE'] else [] # language specific virtual keyboard alt row 2
row3keyb_alt = literal_eval(config['LANGUAGE']['row3keyb_alt']) if 'row3keyb_alt' in config['LANGUAGE'] else [] # language specific virtual keyboard alt row 3
row4keyb_alt = literal_eval(config['LANGUAGE']['row4keyb_alt']) if 'row4keyb_alt' in config['LANGUAGE'] else [] # language specific virtual keyboard alt row 4

clock_show = eval(config['CLOCK']['clock_show']) # show clock after idle time (True) or not (False)
clock_without_idle_time = eval(config['CLOCK']['clock_without_idle_time']) # true: show clock always is no audio is played and only in music_required mode, false: show clock only for max time (clock_max_show_time)
clock_refresh_per_second = int(config['CLOCK']['clock_refresh_per_second']) # clock refresh per second (should be more than once per second to prevent time glitches)
clock_max_idle_time = int(config['CLOCK']['max_idle_time']) # idle time in minutes before clock will be displayed
clock_max_show_time = int(config['CLOCK']['max_show_time']) # maximum time in minutes the clock will be displayed
audioinfo_timer = int(config['CLOCK']['audioinfo_timer']) # time in seconds the audio playout channel check is called again

rss_show = eval(config['RSS']['rss_show']) # show rss feeds (true) or not (False)
rss_feeds = literal_eval(config['RSS']['feeds']) # list of rss feeds (fields: name, count, url), count = number of messages to display

if startlog is True:
    flexprint('[bold green4]start roonmatrix service for ' + hostName + ' @ ' + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + '[/bold green4]')
    flexprint('')
    flexprint('[bold deep_sky_blue4]display cover: ' + str(display_cover) + '[/bold deep_sky_blue4]')
    flexprint("[bold green4]default control zone (buttons): " + control_zone + '[/bold green4]')
    flexprint('')
    flexprint('[green4]exclusive_audio_mode: ' + str(exclusive_audio_mode is True) + '[/green4]')
    flexprint('[green4]music_required: ' + str(music_required is True) + '[/green4]')
    flexprint('[green4]show datetime: ' + str(datetime_show is True) + ', time only: ' + str(datetime_only_time is True) + '[/green4]')
    flexprint('')
    flexprint('[green4]show roon: ' + str(roon_show is True) + ', force update: ' + str(force_roon_update is True) + ', force active zone only: ' + str(force_active_roon_zone_only is True) + '[/green4]')
    flexprint('[green4]show spotify and apple music: ' + str(webservers_show is True) + ', force update: ' + str(force_webserver_update is True) + ', force active zone only: ' + str(force_active_webserver_zone_only is True) + ', update interval: ' + str(webcheck_update_interval) + ' sec[/green4]')
    flexprint('[green4]show weather: ' + str(weather_show is True) + ', for location: ' + location + ', update interval: ' + str(weather_update_interval) + ' sec[/green4]')
    flexprint('[green4]show rss: ' + str(rss_show is True) + '[/green4]')
    flexprint('[green4]show clock: ' + str(clock_show is True) + ', clock_without_idle_time: ' + str(clock_without_idle_time is True) + ', max idle time: ' + str(clock_max_idle_time) + ' min, max show time: ' + str(clock_max_show_time) + ' min[/green4]')
    flexprint('')
    flexprint('=======================================================================================')
    flexprint('')

initialization_done = False # flag: initialization part is done (before threads are started)
check_audioinfo = False # flag: automatic background check of zones is enabled or not while clock will be displayed
audioinfo_available = False # flag: updated zone is found
roonapi = None # roonapi object variable
control_id = None # id of actual control (selected) zone
do_set_zone_control = False # display is set into zone control mode to select another zone to control with the buttons (all other display activities are set into standby)
weatherstr = '' # string to hold the weather data to display (updated in intervals of minutes => weather_update_interval)
weatherlines = [] # list to hold the weather data to display in vertical scrolling mode (updated in intervals of minutes => weather_update_interval)
last_idle_time = None # datetime of last time the playout message was empty
control_id_update = None # temp zone control id to hold this value while zone control setup. this value will be taken if enter button is pressed
displaystr = '' # string to hold the whole message which is actually output to led matrix
app_displaystr = '' # string of new generated audio message part prepared to get info about all audio zones which are playing
vert_strlines = [] # list of message lines for actually output to led matrix in vertical display mode (exclusive_vertical is True)
prepared_displaystr = '' # string of new generated playout message prepared for next run of led matrix output before it will be takeover into displaystr and output to the led matrix
prepared_vert_strlines = [] # string lines of new generated playout message prepared for next run of vertical scrolling led matrix output before it will be takeover into vert_strlines and vertical output to the led matrix
audio_playing = '' # string of new generated audio message part prepared to get info about all audio zones which are playing
weather_fetch_count = 0 # count number of weather api fetches (free acount has a limited number of fetches for a day. for weatherbit its limited to 50 fetches per day)
build_seconds = 0 # time in seconds to fetch and build output data
interrupt_message = False # flag: set true to interrupt message output
fetch_output_in_progress = False # flag: set to true if data fetching and output generation is in progress
output_in_progress = False # flag: set to true if output to led matrix is in progress
clock_in_progress = False # flag: set if clock displaying is in progress (clock starts if max_idle_time is reached, stops if clock display time of max_show_time in minutes is done)
fetch_output_done = False # flag: set if fetching and generating of output message is done
fetch_output_time = None # datetime to fetch and build output data (None: as soon as possible)
zone_control_last_update_time = None # datetime the zone control mode is entered or a button is clicked
playmode = {} # playmode is a dictionary of play state of each roon- or webserver zone (key = control_id, value = play mode (play,stop)
shufflemode = {} # shufflemode is a dictionary of shuffle state of each webserver zone (key = control_id, value = shuffle mode (shuffle,noshuffle)
repeatmode = {} # repeatmode is a dictionary of repeat state of each webserver zone (key = control_id, value = repeat mode (repeat,norepeat)
channels = {} # channels is a dictionary of control_id (key) and zone name (value)
roon_playouts_raw = {} # zone name and their raw jsonString variant of three_line data (track,artist,album) of played song
roon_playouts = {} # zone name and their json variant of three_line data (track,artist,album) of played song
web_playouts_raw = {} # webserver zone name and their raw jsonString variant of data (track,artist,album) of played song
web_playouts = {} # webserver zone name and their json variant of data (track,artist,album) of played song
jobs = {} # map of running threads
jobcount = 0
playcount = 0 # number of playouts
reboot = False # set true to reboot
roon_servers = [] # ip list of roon servers
custom_message = '' # custom message received from app to integrate into playout
custom_message_option = '' # custom message option (force: force updating, playout: standard playout with integrated custom message, exclusive: show only the custom message)
is_playing = True # playing state of actual zone
is_playing_last = None # playing state before of actual zone
shuffle_on = False # shuffle state of actual zone
shuffle_on_last = None # shuffle state before of actual zone
repeat_on = False # repeat state of actual zone
repeat_on_last = None # repeat state before of actual zone
last_cover_url = '' # cover url of active zone (backup to check for changes)
last_zones = [] # list of zone names (backup to check for changes)
last_cover_text_line_parts = [] # list of coverplayer text line parts (backup to check for changes)
playpos_last = -1 # play position of active zone (backup to check for changes)
playlen_last = -1 # play length of active zone (backup to check for changes)
data_changed = False # switch to true if data has changed (playmode,shufflemode,repeatmode,cover,artist,album, or title)
roon_zones = [] # list of actual roon zones

test_roon_discover = False # true: call RoonDiscovery to check for roon servers

socket.setdefaulttimeout(socket_timeout) # set socket timeout

if display_cover is True:
    Coverplayer.config(coverplayer_lang, webserver_url_request_timeout, display_auto_wakeup)
    Coverplayer.set_keyboard_codes([row1keyb, row2keyb, row3keyb, row4keyb, row1keyb_shift, row2keyb_shift, row4keyb_shift, row1keyb_alt, row2keyb_alt, row3keyb_alt, row4keyb_alt])
    Coverplayer.disable_spotify(spotify_client_id=='' or spotify_client_secret=='')
    if spotify_client_id!='' and spotify_client_secret!='':
        try:
            environ['SPOTIPY_CLIENT_ID'] = spotify_client_id
            environ['SPOTIPY_CLIENT_SECRET'] = spotify_client_secret
        except EnvironmentError as e:
            print(f"[magenta][INFO] error on set of env vars for Spotify: {e}[/magenta]")
        except Exception as e:
            print(f"[magenta][ERROR] error on set of env vars for Spotify: {e}[/magenta]")

# --- REST SERVER START ---

app = FastAPI()
clients = set()

@app.get("/")
async def rest_index():
    return {
        "type": 'coverplayer' if display_cover is True else 'roonmatrix',
        "name": hostName,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

@app.get("/info/")
async def rest_info():
    return getInfoData()

@app.get("/config/")
async def rest_config():
    if display_cover is True:
        return {
            "config": config,
            "definitions": {
                "area": [
                    {
                        "name": "SYSTEM",
                        "items": [
                            {"name": "hostname", "editable": True, "type": {"type": "string(5,32)", "structure": []}, "label": "Hostname (Important)", "unit": "5-32", "value": hostName},
                            {"name": "password", "editable": True, "type": {"type": "string(8,64)", "structure": []}, "label": "Password (Important)", "unit": "8-64", "value": "********"},
                            {"name": "countrycode", "editable": True, "type": {"type": "string(2,4)", "structure": []}, "label": "Countrycode (auto or 2 chars code)", "unit": "2-4", "value": config['SYSTEM']['countrycode']},
                            {"name": "internet_connection_timeout", "editable": True, "type": {"type": "int", "structure": []}, "label": "Internet connection timeout", "unit": "seconds", "value": config['SYSTEM']['internet_connection_timeout']},
                            {"name": "internet_connection_url", "editable": True, "type": {"type": "url(http,https)", "structure": []}, "label": "Internet connection check url", "unit": "url", "value": config['SYSTEM']['internet_connection_url'], "link": "*"},
                            {"name": "control_zone", "editable": True, "type": {"type": "string", "structure": []}, "label": "Default control zone", "unit": "", "value": config['SYSTEM']['control_zone']},
                            {"name": "zone_control_timeout", "editable": True, "type": {"type": "int", "structure": []}, "label": "Zone control timeout", "unit": "seconds", "value": config['SYSTEM']['zone_control_timeout']},
                            {"name": "show_album", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Show album name", "unit": "", "value": config['SYSTEM']['show_album']},
                            {"name": "socket_timeout", "editable": True, "type": {"type": "int", "structure": []}, "label": "Socket timeout", "unit": "seconds", "value": config['SYSTEM']['socket_timeout']},
                            {"name": "screensaver_seconds", "editable": True, "type": {"type": "int", "structure": []}, "label": "Screensaver timeout", "unit": "seconds", "value": config['SYSTEM']['screensaver_seconds']},
                            {"name": "display_auto_wakeup", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Display wakeup on updates", "unit": "", "value": config['SYSTEM']['display_auto_wakeup']},
                        ]
                    },
                    {
                        "name": "LANGUAGE",
                        "items": [
                            {"name": "playing_headline", "editable": True, "type": {"type": "string", "structure": []}, "label": "Playing headline text to display in front of audio informations", "unit": "", "value": config['LANGUAGE']['playing_headline']},
                            {"name": "conversions", "editable": True, "type": {"type": "list", "structure": [{"name": "key", "type": "string"},{"name": "val", "type": "string"}]}, "label": "Conversions", "unit": "", "value": config['LANGUAGE']['conversions']},
                            {"name": "messages", "editable": True, "type": {"type": "list", "structure": [{"name": "key", "type": "string"},{"name": "val", "type": "string"}]}, "label": "Messages", "unit": "json", "value": config['LANGUAGE']['messages']},
                            {"name": "coverplayer", "editable": True, "type": {"type": "list(13)", "structure": [{"name": "key", "type": "string"},{"name": "val", "type": "string"}]}, "label": "Coverplayer", "unit": "json", "value": config['LANGUAGE']['coverplayer']},
                            {"name": "row1keyb", "editable": True, "type": {"type": "list(12)", "structure": []}, "label": "Keyboard Row1", "unit": "", "value": config['LANGUAGE']['row1keyb']},
                            {"name": "row2keyb", "editable": True, "type": {"type": "list(12)", "structure": []}, "label": "Keyboard Row2", "unit": "", "value": config['LANGUAGE']['row2keyb']},
                            {"name": "row3keyb", "editable": True, "type": {"type": "list(11)", "structure": []}, "label": "Keyboard Row3", "unit": "", "value": config['LANGUAGE']['row3keyb']},
                            {"name": "row4keyb", "editable": True, "type": {"type": "list(11)", "structure": []}, "label": "Keyboard Row4", "unit": "", "value": config['LANGUAGE']['row4keyb']},
                            {"name": "row1keyb_shift", "editable": True, "type": {"type": "list(11)", "structure": []}, "label": "Keyboard Shift Row1", "unit": "", "value": config['LANGUAGE']['row1keyb_shift']},
                            {"name": "row2keyb_shift", "editable": True, "type": {"type": "list(1)", "structure": []}, "label": "Keyboard Shift Row2", "unit": "", "value": config['LANGUAGE']['row2keyb_shift']},
                            {"name": "row4keyb_shift", "editable": True, "type": {"type": "list(3)", "structure": []}, "label": "Keyboard Shift Row4", "unit": "", "value": config['LANGUAGE']['row4keyb_shift']},
                            {"name": "row1keyb_alt", "editable": True, "type": {"type": "list(11)", "structure": []}, "label": "Keyboard Alt Row1", "unit": "", "value": config['LANGUAGE']['row1keyb_alt']},
                            {"name": "row2keyb_alt", "editable": True, "type": {"type": "list(11)", "structure": []}, "label": "Keyboard Alt Row2", "unit": "", "value": config['LANGUAGE']['row2keyb_alt']},
                            {"name": "row3keyb_alt", "editable": True, "type": {"type": "list(9)", "structure": []}, "label": "Keyboard Alt Row3", "unit": "", "value": config['LANGUAGE']['row3keyb_alt']},
                            {"name": "row4keyb_alt", "editable": True, "type": {"type": "list(10)", "structure": []}, "label": "Keyboard Alt Row4", "unit": "", "value": config['LANGUAGE']['row4keyb_alt']}
                        ]
                    },
                    {
                        "name": "ROON",
                        "items": [
                            {"name": "roon_show", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Show roon zone informations", "unit": "", "value": config['ROON']['roon_show']},
                            {"name": "discovery_delay", "editable": True, "type": {"type": "int", "structure": []}, "label": "Roon Discovery delay", "unit": "seconds", "value": config['ROON']['discovery_delay']},
                            {"name": "core_ip", "editable": True, "noValidation": True, "type": {"type": "string", "structure": []}, "label": "Core IP address (empty ip and port to reset)", "unit": "", "value": config['ROON']['core_ip']},
                            {"name": "core_port", "editable": True, "noValidation": True, "type": {"type": "string", "structure": []}, "label": "Core port (empty ip and port to reset)", "unit": "", "value": config['ROON']['core_port']}
                        ]
                    },
                    {
                        "name": "WEBSERVERS",
                        "items": [
                            {"name": "webservers_show", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Show webserver zone informations", "unit": "", "value": config['WEBSERVERS']['webservers_show']},
                            {"name": "webcheck_update_interval", "editable": True, "type": {"type": "int", "structure": []}, "label": "Webcheck update interval", "unit": "seconds", "value": config['WEBSERVERS']['webcheck_update_interval']},
                            {"name": "zones", "editable": True, "type": {"type": "list", "structure": [{"name": "name", "type": "string"},{"name": "url", "type": "url(http,https)"}]}, "label": "Zones", "unit": "json list", "value": config['WEBSERVERS']['zones']},
                            {"name": "webserver_head_request_timeout", "editable": True, "type": {"type": "int", "structure": []}, "label": "Head request timeout", "unit": "seconds", "value": config['WEBSERVERS']['webserver_head_request_timeout']},
                            {"name": "webserver_url_request_timeout", "editable": True, "type": {"type": "int", "structure": []}, "label": "URL request timeout", "unit": "seconds", "value": config['WEBSERVERS']['webserver_url_request_timeout']},
                            {"name": "spotify_client_id", "editable": True, "type": {"type": "string", "structure": []}, "label": "Spotify Web API client id", "unit": "", "value": config['WEBSERVERS']['spotify_client_id'], "link": "https://developer.spotify.com/documentation/web-api/concepts/apps"},
                            {"name": "spotify_client_secret", "editable": True, "type": {"type": "string", "structure": []}, "label": "Spotify Web API secret", "unit": "", "value": config['WEBSERVERS']['spotify_client_secret']}
                        ]
                    },
                ]
            }
        }    
    
    return {
        "config": config,
        "definitions": {
            "area": [
                {
                    "name": "SYSTEM",
                    "items": [
                        {"name": "hostname", "editable": True, "type": {"type": "string(5,32)", "structure": []}, "label": "Hostname (Important)", "unit": "5-32", "value": hostName},
                        {"name": "password", "editable": True, "type": {"type": "string(8,64)", "structure": []}, "label": "Password (Important)", "unit": "8-64", "value": "********"},
                        {"name": "countrycode", "editable": True, "type": {"type": "string(2,4)", "structure": []}, "label": "Countrycode (auto or 2 chars code)", "unit": "2-4", "value": config['SYSTEM']['countrycode']},
                        {"name": "led_modules", "editable": True, "type": {"type": "int", "structure": []}, "label": "LED modules", "unit": "", "value": config['SYSTEM']['led_modules']},
                        {"name": "led_block_orientation", "editable": False, "type": {"type": "int", "structure": []}, "label": "LED Block Orientation", "unit": "", "value": config['SYSTEM']['led_block_orientation']},
                        {"name": "led_rotate", "editable": False, "type": {"type": "int", "structure": []}, "label": "LED rotation", "unit": "", "value": config['SYSTEM']['led_rotate']},
                        {"name": "led_inreverse", "editable": False, "type": {"type": "int", "structure": []}, "label": "LED in-reverse", "unit": "", "value": config['SYSTEM']['led_inreverse']},
                        {"name": "led_scroll_delay", "editable": True, "type": {"type": "int", "structure": []}, "label": "LED scroll delay", "unit": "ms", "value": config['SYSTEM']['led_scroll_delay']},
                        {"name": "led_vertical_scroll_delay", "editable": True, "type": {"type": "int", "structure": []}, "label": "LED vertical scroll delay (line by line)", "unit": "ms", "value": config['SYSTEM']['led_vertical_scroll_delay']},
                        {"name": "led_contrast", "editable": True, "type": {"type": "int(1,255)", "structure": []}, "label": "LED contrast", "unit": "1-255", "value": config['SYSTEM']['led_contrast']},
                        {"name": "controlswitch_gpio_top", "editable": False, "type": {"type": "int", "structure": []}, "label": "GPIO channel button top", "unit": "", "value": config['SYSTEM']['controlswitch_gpio_top']},
                        {"name": "controlswitch_gpio_down", "editable": False, "type": {"type": "int", "structure": []}, "label": "GPIO channel button down", "unit": "", "value": config['SYSTEM']['controlswitch_gpio_down']},
                        {"name": "controlswitch_gpio_left", "editable": False, "type": {"type": "int", "structure": []}, "label": "GPIO channel button left", "unit": "", "value": config['SYSTEM']['controlswitch_gpio_left']},
                        {"name": "controlswitch_gpio_center", "editable": False, "type": {"type": "int", "structure": []}, "label": "GPIO channel button center", "unit": "", "value": config['SYSTEM']['controlswitch_gpio_center']},
                        {"name": "controlswitch_gpio_right", "editable": False, "type": {"type": "int", "structure": []}, "label": "GPIO channel button right", "unit": "", "value": config['SYSTEM']['controlswitch_gpio_right']},
                        {"name": "controlswitch_bouncetime", "editable": True, "type": {"type": "int", "structure": []}, "label": "Button bounce time", "unit": "ms", "value": config['SYSTEM']['controlswitch_bouncetime']},
                        {"name": "internet_connection_timeout", "editable": True, "type": {"type": "int", "structure": []}, "label": "Internet connection timeout", "unit": "seconds", "value": config['SYSTEM']['internet_connection_timeout']},
                        {"name": "internet_connection_url", "editable": True, "type": {"type": "url(http,https)", "structure": []}, "label": "Internet connection check url", "unit": "url", "value": config['SYSTEM']['internet_connection_url'], "link": "*"},
                        {"name": "separator", "editable": True, "type": {"type": "string", "structure": []}, "label": "Message Separator", "unit": "", "value": config['SYSTEM']['separator']},
                        {"name": "control_zone", "editable": True, "type": {"type": "string", "structure": []}, "label": "Default control zone", "unit": "", "value": config['SYSTEM']['control_zone']},
                        {"name": "zone_control_map", "editable": True, "type": {"type": "list", "structure": [{"name": "key", "type": "string"},{"name": "val", "type": "string"}]}, "label": "Zone control conversion map", "unit": "json", "value": config['SYSTEM']['zone_control_map']},
                        {"name": "zone_control_timeout", "editable": True, "type": {"type": "int", "structure": []}, "label": "Zone control timeout", "unit": "seconds", "value": config['SYSTEM']['zone_control_timeout']},
                        {"name": "map_zone_control", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Zone control conversion", "unit": "", "value": config['SYSTEM']['map_zone_control']},
                        {"name": "exclusive_audio_mode", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Exclusive audio mode", "unit": "", "value": config['SYSTEM']['exclusive_audio_mode']},
                        {"name": "exclusive_active_zone", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Show only the active_zone", "unit": "", "value": config['SYSTEM']['exclusive_active_zone']},
                        {"name": "music_required", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Active music zone required", "unit": "", "value": config['SYSTEM']['music_required']},
                        {"name": "show_zone", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Show zone name", "unit": "", "value": config['SYSTEM']['show_zone']},
                        {"name": "show_album", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Show album name", "unit": "", "value": config['SYSTEM']['show_album']},
                        {"name": "vertical_output", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Vertical output line by line", "unit": "", "value": config['SYSTEM']['vertical_output']},
                        {"name": "vertical_scroll_delay", "editable": True, "type": {"type": "int", "structure": []}, "label": "Scroll delay for vertical output", "unit": "seconds", "value": config['SYSTEM']['vertical_scroll_delay']},
                        {"name": "show_vertical_music_label", "editable": True, "type": {"type": "bool", "structure": []}, "label": "show label (artist, album, track) in vertical scrolling mode", "unit": "", "value": config['SYSTEM']['show_vertical_music_label']},
                        {"name": "datetime_show", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Show date and time", "unit": "", "value": config['SYSTEM']['datetime_show']},
                        {"name": "datetime_only_time", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Show only time part", "unit": "", "value": config['SYSTEM']['datetime_only_time']},
                        {"name": "socket_timeout", "editable": True, "type": {"type": "int", "structure": []}, "label": "Socket timeout", "unit": "seconds", "value": config['SYSTEM']['socket_timeout']}
                    ]
                },
                {
                    "name": "LANGUAGE",
                    "items": [
                        {"name": "playing_headline", "editable": True, "type": {"type": "string", "structure": []}, "label": "Playing headline text to display in front of audio informations", "unit": "", "value": config['LANGUAGE']['playing_headline']},
                        {"name": "conversions", "editable": True, "type": {"type": "list", "structure": [{"name": "key", "type": "string"},{"name": "val", "type": "string"}]}, "label": "Conversions", "unit": "", "value": config['LANGUAGE']['conversions']},
                        {"name": "deg_to_compass", "editable": True, "type": {"type": "list(16)", "structure": []}, "label": "Degree to direction unit", "unit": "", "value": config['LANGUAGE']['deg_to_compass']},
                        {"name": "weather_description", "editable": True, "type": {"type": "list", "structure": [{"name": "key", "type": "string"},{"name": "val", "type": "string"}]}, "label": "Weather description [Weatherbit]", "unit": "json", "value": config['LANGUAGE']['weather_description']},
                        {"name": "weather_properties", "editable": True, "type": {"type": "list", "structure": [{"name": "key", "type": "string"},{"name": "val", "type": "string"}]}, "label": "Weather properties", "unit": "json", "value": config['LANGUAGE']['weather_properties']},
                        {"name": "messages", "editable": True, "type": {"type": "list", "structure": [{"name": "key", "type": "string"},{"name": "val", "type": "string"}]}, "label": "Messages", "unit": "json", "value": config['LANGUAGE']['messages']}
                    ]
                },
                {
                    "name": "ROON",
                    "items": [
                        {"name": "roon_show", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Show roon zone informations", "unit": "", "value": config['ROON']['roon_show']},
                        {"name": "force_roon_update", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Force roon updates", "unit": "", "value": config['ROON']['force_roon_update']},
                        {"name": "force_active_roon_zone_only", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Force active roon zone only", "unit": "", "value": config['ROON']['force_active_roon_zone_only']},
                        {"name": "discovery_delay", "editable": True, "type": {"type": "int", "structure": []}, "label": "Roon Discovery delay", "unit": "seconds", "value": config['ROON']['discovery_delay']},
                        {"name": "core_ip", "editable": True, "noValidation": True, "type": {"type": "string", "structure": []}, "label": "Core IP address (empty ip and port to reset)", "unit": "", "value": config['ROON']['core_ip']},
                        {"name": "core_port", "editable": True, "noValidation": True, "type": {"type": "string", "structure": []}, "label": "Core port (empty ip and port to reset)", "unit": "", "value": config['ROON']['core_port']}
                    ]
                },
                {
                    "name": "WEBSERVERS",
                    "items": [
                        {"name": "webservers_show", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Show webserver zone informations", "unit": "", "value": config['WEBSERVERS']['webservers_show']},
                        {"name": "force_webserver_update", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Force webserver updates", "unit": "", "value": config['WEBSERVERS']['force_webserver_update']},
                        {"name": "force_active_webserver_zone_only", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Force active webserver zone only", "unit": "", "value": config['WEBSERVERS']['force_active_webserver_zone_only']},
                        {"name": "webcheck_update_interval", "editable": True, "type": {"type": "int", "structure": []}, "label": "Webcheck update interval", "unit": "seconds", "value": config['WEBSERVERS']['webcheck_update_interval']},
                        {"name": "zones", "editable": True, "type": {"type": "list", "structure": [{"name": "name", "type": "string"},{"name": "url", "type": "url(http,https)"}]}, "label": "Zones", "unit": "json list", "value": config['WEBSERVERS']['zones']},
                        {"name": "webserver_head_request_timeout", "editable": True, "type": {"type": "int", "structure": []}, "label": "Head request timeout", "unit": "seconds", "value": config['WEBSERVERS']['webserver_head_request_timeout']},
                        {"name": "webserver_url_request_timeout", "editable": True, "type": {"type": "int", "structure": []}, "label": "URL request timeout", "unit": "seconds", "value": config['WEBSERVERS']['webserver_url_request_timeout']}
                    ]
                },
                {
                    "name": "WEATHER",
                    "items": [
                        {"name": "weather_show", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Show weather informations", "unit": "", "value": "", "value": config['WEATHER']['weather_show']},
                        {"name": "location", "editable": True, "type": {"type": "string", "structure": []}, "label": "Location", "unit": "", "value": config['WEATHER']['location']},
                        {"name": "weatherbit_api_key", "editable": True, "type": {"type": "string", "structure": []}, "label": "Weatherbit API key", "unit": "", "value": config['WEATHER']['weatherbit_api_key'], "link": "https://www.weatherbit.io/account/create"},
                        {"name": "weather_update_interval", "editable": True, "type": {"type": "int", "structure": []}, "label": "Update interval", "unit": "seconds", "value": config['WEATHER']['weather_update_interval']},
                        {"name": "with_feel_temperature", "editable": True, "type": {"type": "bool", "structure": []}, "label": "with feel temperature", "unit": "", "value": config['WEATHER']['with_feel_temperature']},
                        {"name": "with_rain", "editable": True, "type": {"type": "bool", "structure": []}, "label": "with rain information (if available)", "unit": "", "value": config['WEATHER']['with_rain']},
                        {"name": "with_wind_spd", "editable": True, "type": {"type": "bool", "structure": []}, "label": "with wind speed in km/h", "unit": "", "value": config['WEATHER']['with_wind_spd']},
                        {"name": "with_wind_dir", "editable": True, "type": {"type": "bool", "structure": []}, "label": "with wind direction", "unit": "", "value": config['WEATHER']['with_wind_dir']},
                        {"name": "with_humidity", "editable": True, "type": {"type": "bool", "structure": []}, "label": "with air humidity", "unit": "", "value": config['WEATHER']['with_humidity']},
                        {"name": "with_pressure", "editable": True, "type": {"type": "bool", "structure": []}, "label": "with air pressure in hPa", "unit": "", "value": config['WEATHER']['with_pressure']},
                        {"name": "with_clouds", "editable": True, "type": {"type": "bool", "structure": []}, "label": "with clouds information in percent (if available)", "unit": "", "value": config['WEATHER']['with_clouds']},
                        {"name": "with_snow", "editable": True, "type": {"type": "bool", "structure": []}, "label": "with snow information in mm/hr (if available)", "unit": "", "value": config['WEATHER']['with_snow']},
                        {"name": "with_uv", "editable": True, "type": {"type": "bool", "structure": []}, "label": "with ultraviolet radiation information", "unit": "", "value": config['WEATHER']['with_uv']},
                        {"name": "with_sunrise", "editable": True, "type": {"type": "bool", "structure": []}, "label": "with sunrise time", "unit": "", "value": config['WEATHER']['with_sunrise']},
                        {"name": "with_sunset", "editable": True, "type": {"type": "bool", "structure": []}, "label": "with sunset time", "unit": "", "value": config['WEATHER']['with_sunset']},
                        {"name": "with_description", "editable": True, "type": {"type": "bool", "structure": []}, "label": "with short weather description text", "unit": "", "value": config['WEATHER']['with_description']}
                    ]
                },
                {
                    "name": "RSS",
                    "items": [
                        {"name": "rss_show", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Show RSS feeds", "unit": "", "value": config['RSS']['rss_show']},
                        {"name": "feeds", "editable": True, "type":{"type": "list", "structure": [{"name": "name", "type": "string"},{"name": "count", "type": "int(1,99)"},{"name": "url", "type": "url(http,https)"}]}, "label": "Feeds", "unit": "json list", "value": config['RSS']['feeds']}
                    ]
                },
                {
                    "name": "CLOCK",
                    "items": [
                        {"name": "clock_show", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Show clock", "unit": "", "value": config['CLOCK']['clock_show']},
                        {"name": "clock_without_idle_time", "editable": True, "type": {"type": "bool", "structure": []}, "label": "Show clock always is no audio is played (in music_required mode only)", "unit": "", "value": config['CLOCK']['clock_without_idle_time']},
                        {"name": "clock_refresh_per_second", "editable": True, "type": {"type": "int", "structure": []}, "label": "Display refresh rate", "unit": "frames/s", "value": config['CLOCK']['clock_refresh_per_second']},
                        {"name": "max_idle_time", "editable": True, "type": {"type": "int", "structure": []}, "label": "Max idle time from inactive output to next time to display clock", "unit": "minutes", "value": config['CLOCK']['max_idle_time']},
                        {"name": "max_show_time", "editable": True, "type": {"type": "int", "structure": []}, "label": "Max show time [automatically quit by activity of zones]", "unit": "minutes", "value": config['CLOCK']['max_show_time']},
                        {"name": "audioinfo_timer", "editable": True, "type": {"type": "int", "structure": []}, "label": "Check audio zones refresh time", "unit": "seconds", "value": config['CLOCK']['audioinfo_timer']}
                    ]
                }
            ]
        }
    }


class LogParams(BaseModel):
    hours: int

@app.post("/log/")
async def rest_log(params: LogParams):
    hours = params.hours
    if display_cover is True:
        result = filter_lines_by_hours('/home/coverplayer/FTP/logs/roonmatrix.log', hours)
        return result
    else:
        cmd = '/usr/bin/journalctl --unit=roonmatrix.service --no-pager --since \"' + str(hours) + 'hours ago\"'
        flexprint('LOG CMD: ' + cmd)
        result = subprocess.run(shlex.split(cmd), capture_output=True)
        return result.stdout

class SetupParams(BaseModel):
    data: str

@app.post("/setup/")
async def rest_setup(params: SetupParams):
    global config, reboot, screensaver_seconds
    jsonObj = json.loads(params.data)
    doReboot = False

    for idx,areaKey in enumerate(jsonObj,1):
        for idx,fieldKey in enumerate(jsonObj[areaKey],1):
            fieldValue = str(jsonObj[areaKey][fieldKey])
            if '%' in fieldValue and '%%' not in fieldValue: 
                fieldValue = fieldValue.replace('%','%%') # masking of percent char
            if '\\' in fieldValue and '\\\\' not in fieldValue: 
                fieldValue = fieldValue.replace('\\','\\\\') # masking of quotes char
            if config[areaKey][fieldKey]!=fieldValue:
                if fieldKey!='screensaver_seconds':
                    config_str_masked = config[areaKey][fieldKey]
                    if '%' in config_str_masked and '%%' not in config_str_masked: 
                        config_str_masked = config_str_masked.replace('%','%%') # masking of percent char
                    if '\\' in config_str_masked and '\\\\' not in config_str_masked: 
                        config_str_masked = config_str_masked.replace('\\','\\\\') # masking of percent char
                    if config_str_masked!=fieldValue:
                        config[areaKey][fieldKey] = fieldValue
                        #print('fieldValue changed: ' + str(fieldValue) + ' vs. ' + str(config[areaKey][fieldKey]))
                        doReboot = True
            if areaKey!='SYSTEM' or fieldKey!='password':
                flexprint('setup received, set [' + areaKey + '][' + fieldKey + '] => ' + fieldValue)
            if areaKey=='SYSTEM' and fieldKey=='hostname' and config[areaKey][fieldKey]!='' and config[areaKey][fieldKey]!=hostName:
                setHostname(config[areaKey][fieldKey])
            if areaKey=='SYSTEM' and fieldKey=='screensaver_seconds' and fieldValue!=str(screensaver_seconds):
                config[areaKey][fieldKey] = fieldValue
                screensaver_seconds = int(fieldValue)
                setScreensaver(config[areaKey][fieldKey])
            if areaKey=='SYSTEM' and fieldKey=='password' and config[areaKey][fieldKey]!='' and config[areaKey][fieldKey]!='********':
                if display_cover is True:
                    setUserPassword('coverplayer',config[areaKey][fieldKey])
                else:
                    setUserPassword('rmuser',config[areaKey][fieldKey])

    pwbackup = config['SYSTEM']['password']
    del config['SYSTEM']['password']
        
    fileinfo = translation_exist(countrycode, False)
    exist = fileinfo[0]
    if exist:
        flexprint('translation file ' + countrycode + 'exist')    # hash in ini speichern, wenn bei start der hash vorhanden ist, dann NICHT integrieren! (Ändert sich der countrycode, dann muss die neue Sprache die config überschreiben. Wurde die Sprache einmal übernommen, dann darf bei config read NICHT das translation file verwendet werden.)
        if updateHash!='':
            config['LANGUAGE']['translation_hash'] = updateHash

    with open(configFile, 'w') as fileRes:
        config.write(fileRes)

    config['SYSTEM']['password'] = pwbackup
    if doReboot is True:
        flexprint('successfully write of config file => do reboot now')
        reboot = True
    else:
        flexprint('successfully write of config file')

    return True

class ZoneControlParams(BaseModel):
    control_id: str
    cmd: str
    enable: bool

@app.post("/zone_control/")
async def rest_zone_control(params: ZoneControlParams):
    global control_id

    cmd = params.cmd
    enable = params.enable
    if log is True: 
        msg = '[bold magenta]POST zone_control => control_id: ' + params.control_id + ', cmd: ' + cmd
        if cmd == 'playmode' or cmd == 'shufflemode' or cmd == 'repeatmode':
            msg += ', enable:' + str(enable)
        msg += '[/bold magenta]'
        flexprint(msg)

    if cmd=='previous':
        play_previous(params.control_id)
        return True
    if cmd=="next":
        play_next(params.control_id)
        return True
    if cmd=="playmode":
        set_play_mode(params.control_id, enable, True)
        return True
    if cmd=="shufflemode":
        set_shuffle_mode(params.control_id, enable, True)
        return True
    if cmd=="repeatmode":
        set_repeat_mode(params.control_id, enable, True)
        return True
    if cmd=="switch":
        control_id = params.control_id
        return True

    return False

class CustomMessageParams(BaseModel):
    message: str
    option: str

@app.post("/message/")
async def rest_custom_message(params: CustomMessageParams):
    global custom_message, custom_message_option

    custom_message = params.message
    custom_message_option = params.option
    if log is True: flexprint('POST message => message: ' + custom_message + ', option: ' + custom_message_option)

    if custom_message != ''  and custom_message_option != 'playout':
        force_custom_message()

    return True

class LiveControlParams(BaseModel):
    control: str
    value: str

@app.post("/livecontrol/")
async def rest_live_control(params: LiveControlParams):
    global led_scroll_delay, led_vertical_scroll_delay, vertical_scroll_delay, led_contrast, config

    livecontrol_control = params.control
    livecontrol_value = params.value
    if log is True: flexprint('POST livecontrol => control: ' + livecontrol_control + ', value: ' + livecontrol_value)

    if livecontrol_control != '' and livecontrol_value != '':
        if livecontrol_control == 'led_scroll_delay':
            led_scroll_delay = float(livecontrol_value)
            config['SYSTEM']['led_scroll_delay'] = livecontrol_value
        if livecontrol_control == 'vertical_scroll_delay':
            vertical_scroll_delay = int(livecontrol_value)
            config['SYSTEM']['vertical_scroll_delay'] = livecontrol_value
        if livecontrol_control == 'led_vertical_scroll_delay':
            led_vertical_scroll_delay = float(livecontrol_value)
            config['SYSTEM']['led_vertical_scroll_delay'] = livecontrol_value
        if livecontrol_control == 'led_contrast':
            led_contrast = int(livecontrol_value)
            config['SYSTEM']['led_contrast'] = livecontrol_value
            device.contrast(led_contrast)

    config['SYSTEM']['password'] = '********' # set roonmatrix password placeholder with default value
    del config['SYSTEM']['password']

    with open(configFile, 'w') as fileRes:
        config.write(fileRes)
    flexprint('successfully write of config file')

    config['SYSTEM']['password'] = '********' # set roonmatrix password placeholder with default value

    return True

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global data_changed
    await websocket.accept()
    clients.add(websocket)
    flexprint(f"websocket client connected: {websocket.client}")
    try:
        while True:
            await asyncio.sleep(1)
            if data_changed is True:
                data_changed = False
                data = getInfoData()
                flexprint('websocket sending info data')
                await websocket.send_json(data)
    except WebSocketDisconnect:
        flexprint(f"websocket client disconnected: {websocket.client}")
    except Exception as e:
        flexprint(f"websocket error: {e}")
        flexprint(str(data))
    finally:
        clients.discard(websocket)

def start_restserver():
    uvicorn.run(app, host="0.0.0.0", port=8000)

# --- REST SERVER END ---

def do_reboot():
    time.sleep(3)
    subprocess.run(["sudo", "/usr/sbin/reboot", "-f"], check=True)

def setHostname(newhostname):
    flexprint('setHostname: ' + newhostname)
    try:
        temp_path = '/var/tmp/roonmatrix_temp.txt'
        with open('/etc/hosts', 'r') as file:
            data = file.readlines()
        data[5] = '127.0.1.1       ' + newhostname

        with open(temp_path, 'w') as file:
            file.writelines( data )

        subprocess.run(["sudo", "/usr/bin/mv", temp_path, "/etc/hosts"], check=True)

        with open('/etc/hostname', 'r') as file:
            data = file.readlines()
        data[0] = newhostname

        with open(temp_path, 'w') as file:
            file.writelines( data )

        subprocess.run(["sudo", "/usr/bin/mv", temp_path, "/etc/hostname"], check=True)
        subprocess.run(["sudo", "/usr/bin/hostnamectl", "set-hostname", newhostname], check=True)
    except Exception as e:
        flexprint('[red]setHostname error: ' + str(e) + '[/red]')

def setUserPassword(login,password):
    flexprint('setUserPassword')
    shadow_password = crypt.crypt(password, crypt.mksalt(crypt.METHOD_SHA512))

    r = subprocess.call(['sudo', '/usr/sbin/usermod', '-p', shadow_password, login])
    if r != 0:
        flexprint('[red]error changing password[/red]')

def setScreensaver(seconds):
    flexprint('setScreensaver: ' + str(seconds))
    autostart_path = '/home/coverplayer/.config/autostart/xset.desktop'
    data = []
    data.append('[Desktop Entry]\n')
    data.append('Type=Application\n')
    try:
        if int(seconds) == 0:
            subprocess.run(["sh", "-c", "export DISPLAY=:0;xset s off;xset -dpms"], check=True)
            data.append('Exec=sh -c "sleep 5; xset s off; xset -dpms"\n')
            data.append('Hidden=false\n')
            data.append('NoDisplay=false\n')
            data.append('X-GNOME-Autostart-enabled=true\n')
            data.append('Name=Disable DPMS\n')
            data.append('Comment=Disables DPMS and screen blanking\n')
        else:
            subprocess.run(["sh", "-c", "export DISPLAY=:0;xset s " + str(seconds) + ";xset +dpms"], check=True)
            data.append('Exec=sh -c "sleep 5; xset s ' + str(seconds) + '; xset +dpms"\n')
            data.append('Hidden=false\n')
            data.append('NoDisplay=false\n')
            data.append('X-GNOME-Autostart-enabled=true\n')
            data.append('Name=Enable DPMS\n')
            data.append('Comment=Enables DPMS and screen blanking\n')
        with open(autostart_path, 'w') as file:
            file.writelines( data )
    except Exception as e:
        flexprint('[red]setScreensaver error: ' + str(e) + '[/red]')

def filter_lines_by_hours(base_filepath, hours_back):
    try:
        flexprint('filter_lines_by_hours, hours: ' + str(hours_back))
        now = datetime.now()
        time_limit = now - timedelta(hours=hours_back)
        matched_lines = []

        if not path.exists(base_filepath):
            return ""

        log_files = []
        index = 0
        while True:
            filename = base_filepath if index == 0 else f"{base_filepath}.{index}"
            if path.exists(filename):
                log_files.append(filename)
                index += 1
            else:
                break

        for filepath in reversed(log_files):
            with open(filepath, 'r', encoding='utf-8') as file:
                for line in file:
                    try:
                        timestamp_str = line[:17].strip()
                        timestamp = datetime.strptime(timestamp_str, '%y-%m-%d %H:%M:%S')
                        if time_limit <= timestamp <= now:
                            matched_lines.append(line)
                    except ValueError:
                        continue
            if matched_lines and timestamp < time_limit:
                break

        flexprint('filter_lines_by_hours, lines: ' + str(len(matched_lines)))
        return "\n".join(line.rstrip() for line in matched_lines) if matched_lines else ""
    except Exception as e:
        flexprint('[red]filter_lines_by_hours error: ' + str(e) + '[/red]')

def init_matrix():
    global serial

    if display_cover is True:
        return None

    device = max7219(serial, cascaded=led_modules or 1, block_orientation=led_block_orientation,
                     rotate=led_rotate or 0, blocks_arranged_in_reverse_order=led_inreverse)
    device.contrast(led_contrast)
    return device

def output():
    global output_in_progress

    if display_cover is True:
        time.sleep(3) # wait 3sec to give the thread routine enough time to recognize the change of output_in_progress flag, and a time slot to do nothing before next data fetch starts
        output_in_progress = False
        return

    if (vertical_output == False and displaystr is not None and displaystr != '') or (vertical_output == True and len(vert_strlines) > 0):
        if log is True: flexprint('Output => ' + str(vert_strlines) if vertical_output == True else displaystr)

        if vertical_output is True:
            delaySec = led_vertical_scroll_delay/1000
            show_message_vertical_interruptable(device, vert_strlines, fill="white", font=proportional(CP437_FONT), scroll_delay=delaySec)
        else:
            delaySec = led_scroll_delay/1000
            show_message_interruptable(device, displaystr, fill="white", font=proportional(CP437_FONT), scroll_delay=delaySec)
        if log is True: flexprint(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ' => playout done')

    output_in_progress = False

def clear_display(type):
    if debug is True: flexprint('clear display, called from [' + type + ']')
    if display_cover is True:
        return

    with canvas(device) as draw:
        text(draw, (0, 0), '', fill="white", font=proportional(CP437_FONT))

def roon_discover_all_test():
    if test_roon_discover is True:
        discover = RoonDiscovery(None)
        servers = discover.all()
        flexprint('[bold red]roon_discover_all_test: ' + str(servers) + '[/bold red]')
        discover.stop()
        time.sleep(1)

def roon_discover_first_test():
    if test_roon_discover is True:
        discover = RoonDiscovery(None)
        servers = discover.first()
        flexprint('[bold red]roon_discover_first_test: ' + str(servers) + '[/bold red]')
        discover.stop()
        time.sleep(1)

def roon_discover_active_test():
    if test_roon_discover is True:
        if path.exists(idfile):
            with open(idfile, "r") as f:
                core_id = f.read()
                f.close()
        else:
            core_id = None

        if path.exists(tokenfile):
            with open(tokenfile, "r") as f:
                token = f.read()
                f.close()
        else:
            token = None

        if core_id is not None and token is not None:
            discover = RoonDiscovery(core_id)
            servers = discover.first()
            flexprint('[bold red]roon_discover_active_test: ' + str(servers) + '[/bold red]')
            discover.stop()
            time.sleep(1)

def roon_discover():
    global roon_servers, core_ip, core_port, config

    if roonapi is not None:
        return

    if path.exists(idfile):
        with open(idfile, "r") as f:
            core_id = f.read()
            f.close()
    else:
        core_id = None

    if path.exists(tokenfile):
        with open(tokenfile, "r") as f:
            token = f.read()
            f.close()
    else:
        token = None

    if core_id is None or token is None or core_ip == '' or core_port == '':
        discover = RoonDiscovery(None)
        roon_servers = discover.all()

        if log is True: flexprint("roon_discover => Shutdown discovery")
        discover.stop()

        flexprint("roon_discover => Found the following servers")
        flexprint(roon_servers)
        if len(roon_servers) > 0:
            core_ip = roon_servers[0][0]
            core_port = roon_servers[0][1]
            
            api = RoonApi(appinfo, None, core_ip, core_port, False)
            
            if api is not None:
                config['ROON']['core_ip'] = core_ip # set roon server ip
                config['ROON']['core_port'] = str(core_port) # set roon server port
                del config['SYSTEM']['password']
                with open(configFile, 'w') as fileRes:
                    config.write(fileRes)
                config['SYSTEM']['password'] = '********' # set roonmatrix password placeholder with default value
            
                # This is what we need to reconnect
                core_id = api.core_id
                token = api.token

                with open(idfile, "w") as f:
                    f.write(str(core_id))
                    f.close()

                with open(tokenfile, "w") as f:
                    f.write(str(token))
                    f.close()

                if log is True: flexprint("roon_discover => Shutdown api")
                api.stop()

        flexprint('roon_discover => [bright_magenta]try to discover roon server @ ' + str(datetime.now().strftime("%Y-%m-%d %H:%M:%S")) + ': ' + str(len(roon_servers)) + ' => ' + str (roon_servers) + ' [/bright_magenta]')
        time.sleep(discovery_delay)

def get_roon_api():
    global roonapi, roon_servers

    if path.exists(tokenfile):
        with open(tokenfile, "r") as f:
            token = f.read()
            f.close()
    else:
        token = None

    if core_ip !='' and core_port != '' and token is not None:
        roonapi = RoonApi(appinfo, token, core_ip, int(core_port), True)
        time.sleep(1)
        if roonapi is not None:
            data = [core_ip, int(core_port)]
            if len(roon_servers) == 0:
                roon_servers = [data]
            if log is True: 
                flexprint("roon api connected => (host, core_name, core_id)")
                flexprint(roonapi.host)
                flexprint(roonapi.core_name)
                flexprint(roonapi.core_id)
                
            # This is what we need to reconnect
            core_id = roonapi.core_id
            token = roonapi.token

            with open(idfile, "w") as f:
                f.write(str(core_id))
                f.close()

            with open(tokenfile, "w") as f:
                f.write(str(token))
                f.close()
                
            set_default_zone()
            if force_roon_update is True:
                roonapi.register_state_callback(roon_state_callback)

def getInfoData():
    timeStr = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    outputTimeStr = fetch_output_time.strftime("%Y-%m-%d %H:%M:%S") if fetch_output_time is not None else 'None'
    nowStr = str(datetime.now())
    lastIdleTimeStr = last_idle_time.strftime("%Y-%m-%d %H:%M:%S") if last_idle_time is not None else 'None'
    zoneControlLastUpdateTimeStr = zone_control_last_update_time.strftime("%Y-%m-%d %H:%M:%S") if zone_control_last_update_time is not None else 'None'

    return {
        "name": hostName,
        "time": timeStr,
        "debug": debug,
        "startlog": startlog,
        "log": log,
        "errorlog": errorlog,
        "display_cover": display_cover,
        "led_modules": led_modules,
        "led_scroll_delay": led_scroll_delay,
        "led_vertical_scroll_delay": led_vertical_scroll_delay,
        "led_contrast": led_contrast,
        "controlswitch_bouncetime": controlswitch_bouncetime,
        "internet_connection_timeout": internet_connection_timeout,
        "internet_connection_url": internet_connection_url,
        "zone_control_timeout": zone_control_timeout,
        "map_zone_control": map_zone_control,
        "socket_timeout": socket_timeout,
        "screensaver_seconds": screensaver_seconds,
        "control_zone": control_zone,
        "playing_headline" : playing_headline,
        "exclusive_audio_mode": exclusive_audio_mode,
        "exclusive_active_zone": exclusive_active_zone,
        "music_required": music_required,
        "show_zone": show_zone,
        "show_album": show_album,
        "vertical_output": vertical_output,
        "vertical_scroll_delay": vertical_scroll_delay,
        "show_vertical_music_label": show_vertical_music_label,
        "datetime_show": datetime_show,
        "datetime_only_time": datetime_only_time,
        "roon_show": roon_show,
        "force_roon_update": force_roon_update,
        "force_active_roon_zone_only": force_active_roon_zone_only,
        "discovery_delay": discovery_delay,
        "webservers_show": webservers_show,
        "force_webserver_update": force_webserver_update,
        "force_active_webserver_zone_only": force_active_webserver_zone_only,
        "webcheck_update_interval": webcheck_update_interval,
        "webservers_zones": webservers_zones,
        "webserver_head_request_timeout": webserver_head_request_timeout,
        "webserver_url_request_timeout": webserver_url_request_timeout,
        "weather_show": weather_show,
        "location": location,
        "weather_update_interval": weather_update_interval,
        "with_feel_temperature": with_feel_temperature,
        "with_rain": with_rain,
        "with_wind_spd": with_wind_spd,
        "with_wind_dir": with_wind_dir,
        "with_humidity": with_humidity,
        "with_pressure": with_pressure,
        "with_clouds": with_clouds,
        "with_snow": with_snow,
        "with_uv": with_uv,
        "with_sunrise": with_sunrise,
        "with_sunset": with_sunset,
        "with_description": with_description,
        "rss_show": rss_show,
        "rss_feeds": rss_feeds,
        "clock_show": clock_show,
        "clock_without_idle_time": clock_without_idle_time,
        "clock_refresh_per_second": clock_refresh_per_second,
        "clock_max_idle_time": clock_max_idle_time,
        "clock_max_show_time": clock_max_show_time,
        "audioinfo_timer": audioinfo_timer,
        "from_zone": datetime.now(from_zone).tzname(),
        "to_zone": datetime.now(to_zone).tzname(),
        "initialization_done": initialization_done,
        "check_audioinfo": check_audioinfo,
        "audioinfo_available": audioinfo_available,
        "control_id": control_id,
        "do_set_zone_control": do_set_zone_control,
        "datetime": nowStr,
        "last_idle_time": lastIdleTimeStr,
        "control_id_update": control_id_update,
        "weather_fetch_count": weather_fetch_count,
        "build_seconds": build_seconds,
        "interrupt_message": interrupt_message,
        "fetch_output_in_progress": fetch_output_in_progress,
        "output_in_progress": output_in_progress,
        "clock_in_progress": clock_in_progress,
        "fetch_output_done": fetch_output_done,
        "fetch_output_time": outputTimeStr,
        "zone_control_last_update_time": zoneControlLastUpdateTimeStr,
        "playmode": playmode,
        "shufflemode": shufflemode,
        "repeatmode": repeatmode,
        "custom_message": custom_message,
        "custom_message_option": custom_message_option,
        "channels": channels,
        "roon_playouts_raw": roon_playouts_raw,
        "roon_playouts": roon_playouts,
        "web_playouts_raw": web_playouts_raw,
        "web_playouts": web_playouts,
        "jobs": len(jobs),
        "playcount": playcount,
        "roon_servers": roon_servers,
        "core_ip": core_ip,
        "core_port": core_port,
        "weatherstr": weatherstr,
        "weatherlines": weatherlines,
        "prepared_displaystr": prepared_displaystr,
        "displaystr": displaystr,
        "app_displaystr": app_displaystr,
        "prepared_vert_strlines": prepared_vert_strlines,
        "vert_strlines": vert_strlines,
        "audio_playing": audio_playing,
        "is_playing": is_playing,
        "shuffle_on": shuffle_on,
        "repeat_on": repeat_on,
        "clients": list(map(lambda obj: str(obj.client), clients))
    }

def get_next_fetch_output_time(msg, font=None, scroll_delay=0.03):
    font = font or DEFAULT_FONT

    if vertical_output is True:
        estimated_seconds = (2 + len(msg)) * (vertical_scroll_delay + 1/1000 * led_vertical_scroll_delay * 8)
    else:
        fps = 0 if scroll_delay == 0 else 1.0 / scroll_delay
        if display_cover is True:
            estimated_seconds = 20 # fake time to limit api calls in display_cover mode
        else:
            with canvas(device) as draw:
                w, h = textsize(msg, font)
            x = device.width
            fullwidth = w + x
            estimated_seconds = round(fullwidth/fps)
    running_start = datetime.now()
    estimated_end = running_start + timedelta(0,estimated_seconds)
    fetch_output_time = estimated_end - timedelta(0,build_seconds * 2)
    if debug is True: flexprint('get_next_fetch_output_time, estimated_seconds: ' + str(estimated_seconds) + ', fetch_output_time: ' + str(fetch_output_time) + ' [time: ' + str(build_seconds) + ' sec]')

    return fetch_output_time

def show_message_interruptable(device, msg, y_offset=0, fill=None, font=None, scroll_delay=0.03):
    global interrupt_message

    if display_cover is True:
        return

    fps = 0 if scroll_delay == 0 else 1.0 / scroll_delay
    regulator = framerate_regulator(fps)
    font = font or DEFAULT_FONT
    with canvas(device) as draw:
        w, h = textsize(msg, font)
    x = device.width
    fullwidth = w + x

    virtual = viewport(device, width=fullwidth + x, height=device.height)

    with canvas(virtual) as draw:
        text(draw, (x, y_offset), msg, font=font, fill=fill)

    i = 0
    while i <= w + x and interrupt_message is False and do_set_zone_control is False:
        with regulator:
            virtual.set_position((i, 0))
            i += 1
    interrupt_message = False

    if do_set_zone_control is True:
        set_control_zone()

def show_message_vertical_interruptable(device, lines, y_offset=0, fill=None, font=None, scroll_delay=0.03):
    global interrupt_message

    if display_cover is True:
        return

    fps = 0 if scroll_delay == 0 else 1.0 / scroll_delay
    regulator = framerate_regulator(fps)
    font = font or DEFAULT_FONT

    virtual = viewport(device, width=device.width, height=device.height * (len(lines) + 2))

    with canvas(virtual) as draw:
        for idx,line in enumerate(lines):
            w, h = textsize(line, font)
            x_offset = 0
            if w < device.width:
                x_offset = (device.width - w) / 2
            text(draw, (x_offset, y_offset + device.height * (idx+1)), line, font=font, fill=fill)

    y = 0
    for row in range(1, len(lines)+2):
        while y <= device.height * row and interrupt_message is False and do_set_zone_control is False:
            with regulator:
                virtual.set_position((0, y))
                y += 1
        time.sleep(vertical_scroll_delay)
        if interrupt_message is True:
            break

    interrupt_message = False

    if do_set_zone_control is True:
        set_control_zone()

def is_url_active(url,timeout):
    try:
        requests.head(url, timeout=timeout)
        return True
    except requests.ConnectionError:
        return False
    except Exception as e:
        return False

def is_port_on_ip_open(ip,port):
   msg = 'is_port_on_ip_open (ip: ' + ip + ', port: ' + port + '): '
   s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
   try:
      s.connect((ip, int(port)))
      s.shutdown(2)
      flexprint('[green]' + msg + 'true[/green]')
      return True
   except:
      flexprint('[red]' + msg + 'false[/red]')
      return False

def is_roon_server_active(ip,port):
    global roon_servers

    active = is_port_on_ip_open(ip,port)
    if active is False:
        roon_servers = []
    return active

def moveActualPlayerToFirstPosInWebserverZoneList(webservers_zones):
    if control_id is not None and len(webservers_zones) > 0:
        names = [d.get('name') for d in webservers_zones]
        baseName = control_id.split('-')[0]
        if baseName in names and not baseName == webservers_zones[0]['name']:
            index = names.index(baseName)
            webservers_zones.insert(0, webservers_zones.pop(index)) # move actual player to first position in list (check online availability first => possible to fallback to one of the next zones in same loop)
    return webservers_zones

def get_active_zones_from_webserver_onlinecheck(update):
    active_zones = []

    for idx,data in enumerate(webservers_zones,1):
        name = data['name']
        url = data['url']
        online = is_url_active(url,webserver_head_request_timeout)
        if update is True:
            update_webserver_channels(name, online)
        if debug is True: flexprint('online check of webserver ' + name + ': ' + str(online))
        if online is True:
            active_zones.append(data)
        else:
            if log is True: flexprint('Webserver ' + name + ' is down')
    return active_zones

def is_audioinfo_available():
    global roonapi, audioinfo_available, fetch_output_time, fetch_output_in_progress

    time.sleep(1)
    available = False
    debug = True

    try:
        if check_audioinfo is True and webservers_show is True:
            active_zones = get_active_zones_from_webserver_onlinecheck(False)
            async_web_response = async_web_requests_with_timing(active_zones)

            for idx,data in enumerate(async_web_response,1):
                name = data['name']
                url = data['url']
                try:
                    if 'error' in data :
                        if log is True: flexprint('Webserver error: ' + data['error'])
                    if 'status' in data and data['status'] == 200:
                        result = str(data['text']).replace('\n','')
                except Exception as e:
                        time.sleep(1)
                else:
                    if result != '' and result.startswith('[{') and result.endswith('}]'):
                        resultJson = json.loads(result)
                        for obj in resultJson:
                            playing = "status" in obj and (obj['status'] == 'playing' or obj['status'] == 'paused')
                            if debug is True: flexprint('playout check of webserver ' + name + '(zone:' + obj["zone"] + '): ' + str(playing))
                            if playing is True:
                                available = True
                                break
                        if available is True:
                            break

        if check_audioinfo is True and available is False and roon_show is True:
            if debug is True: flexprint('is_audioinfo_available => [bright_magenta]try to discover roon server @ ' + str(datetime.now().strftime("%Y-%m-%d %H:%M:%S")) + ' [/bright_magenta]')
            roon_active = is_roon_server_active(core_ip, core_port) if (core_ip != '' and core_port != '') else False
            if core_ip == '' or core_port == '':
                roon_discover()
            if roonapi is None:
                get_roon_api()
            roon_active = is_roon_server_active(core_ip, core_port) if (core_ip != '' and core_port != '') else False
            roon_discover_first_test()
            if roon_active is True and core_ip != '' and core_port != '' and roonapi is not None:
                for zone in list(roonapi.zones.values()):
                    if debug is True: flexprint('playout check of roon zone ' + zone["display_name"] + ': ' + (zone["state"] if zone["state"] is not None else '-'))
                    if zone["state"] is not None and zone["state"] == 'playing':
                        available = True
                        break
                update_roon_channels()
            if available is True:
                time.sleep(discovery_delay)
    except Exception as e:
        if errorlog is True: 
            flexprint('[red]==> audioinfo available error: [/red]', str(e))
            flexprint(traceback.format_exc())

    if available is True:
        fetch_output_time = None
        fetch_output_in_progress = False

    if log is True: flexprint('is_audioinfo_available: ' + str(available))
    audioinfo_available = available

def refresh_output_data(force = False):
    global fetch_output_time, fetch_output_in_progress, fetch_output_done, prepared_displaystr, prepared_vert_strlines

    fetch_new = fetch_output_time is None or (fetch_output_time + timedelta(0,60)) < datetime.now()
    if fetch_new is True or force is True:
        if log is True: flexprint('fetched output data too old (' + (fetch_output_time.strftime("%Y-%m-%d %H:%M:%S") if fetch_output_time is not None else 'None') + ') => refresh')
        fetch_output_time = None
        fetch_output_done = False
        fetch_output_in_progress = False
    else:
        if vertical_output is False and prepared_displaystr == '':
            prepared_displaystr = displaystr
        if vertical_output is True and len(prepared_vert_strlines) == 0:
            prepared_vert_strlines = vert_strlines
            prepared_displaystr = str(prepared_vert_strlines) if len(prepared_vert_strlines) > 0 else ''

        fetch_output_in_progress = True
        fetch_output_done = True

def getPlaystateFromPlaymode(control_id):
    if control_id is not None and control_id in playmode:
        return playmode[control_id] == 'play'
    else:
        return False

def set_play_mode(control_id, enable, send):
    global data_changed
    if control_id is not None and control_id in channels.keys():
        playmode_last = playmode[control_id] if control_id in playmode else None
        if enable is True:
            playmode[control_id] = 'play'
        else:
            playmode[control_id] = 'stop'
        if control_id in playmode and playmode_last != playmode[control_id]:
            data_changed = True

        if send is True:
            if channels[control_id]=='webserver':
                send_webserver_zone_control(control_id, playmode[control_id])
            else:
                if roon_show == True and roon_servers:
                    roonapi.playback_control(control_id, playmode[control_id])

def getShufflestateFromPlaymode(control_id):
    if control_id is not None and control_id in shufflemode:
        return shufflemode[control_id] == 'shuffle'
    else:
        return False

def set_shuffle_mode(control_id, enable, send):
    global data_changed
    shufflemode_last = shufflemode[control_id] if control_id in shufflemode else None
    if control_id is not None and control_id in channels.keys():
        if channels[control_id]=='webserver':
            if enable is True:
                shufflemode[control_id] = 'shuffle'
            else:
                shufflemode[control_id] = 'noshuffle'
            if send is True:
                send_webserver_zone_control(control_id, shufflemode[control_id])
        else:
            if roon_show == True and roon_servers:
                if control_id is not None:
                    if enable is True:
                        shufflemode[control_id] = 'shuffle'
                        if send is True:
                            roonapi.shuffle(control_id, True)
                    else:
                        shufflemode[control_id] = 'noshuffle'
                        if send is True:
                            roonapi.shuffle(control_id, False)
    if control_id in shufflemode and shufflemode_last != shufflemode[control_id]:
        data_changed = True

def getRepeatstateFromPlaymode(control_id):
    if control_id is not None and control_id in repeatmode:
        return repeatmode[control_id] == 'repeat'
    else:
        return False

def set_repeat_mode(control_id, enable, send):
    global data_changed
    repeatmode_last = repeatmode[control_id] if control_id in repeatmode else None
    if control_id is not None and control_id in channels.keys():
        if channels[control_id]=='webserver':
            if enable is True:
                repeatmode[control_id] = 'repeat'
            else:
                repeatmode[control_id] = 'norepeat'
            if send is True:
                send_webserver_zone_control(control_id, repeatmode[control_id])
        else:
            if roon_show == True and roon_servers:
                if control_id is not None:
                    if enable is True:
                        repeatmode[control_id] = 'repeat'
                        if send is True:
                            roonapi.repeat(control_id, 'loop')	# loop, loop_one, disabled
                    else:
                        repeatmode[control_id] = 'norepeat'
                        if send is True:
                            roonapi.repeat(control_id, 'disabled')
    if control_id in repeatmode and repeatmode_last != repeatmode[control_id]:
        data_changed = True

def play_previous(control_id):
    if control_id is not None:
        if channels[control_id]=='webserver':
            send_webserver_zone_control(control_id, "previous")
        else:
            if roon_show == True and roon_servers:
                roonapi.playback_control(control_id, "previous")

def play_next(control_id):
    if control_id is not None:
        if channels[control_id]=='webserver':
            send_webserver_zone_control(control_id, "next")
        else:
            if roon_show == True and roon_servers:
                roonapi.playback_control(control_id, "next")

def pressed_up(channel):
    global do_set_zone_control, zone_control_last_update_time, clock_in_progress, control_id, control_id_update, control_zone, is_playing_last, shuffle_on_last, repeat_on_last, is_playing, shuffle_on, repeat_on

    if display_cover is True:
        return

    time.sleep(0.1)
    if GPIO.event_detected(controlswitch_gpio_top):
        GPIO.remove_event_detect(controlswitch_gpio_top)
        flexprint('=> pressed up, do_set_zone_control(before): ' + str(do_set_zone_control))
        if do_set_zone_control == False:
            control_id_update = control_id
            zone_control_last_update_time = datetime.now()
            do_set_zone_control = True
            if log is True: flexprint('enter zone control setup')
            if clock_in_progress is True or displaystr=='':
                set_control_zone(False)
        else:
            do_set_zone_control = False
            control_id = control_id_update
            control_zone = control_id
            clear_display('pressed_up')
            refresh_output_data(True)
            if log is True: flexprint('close zone control setup')
            is_playing_last = None
            shuffle_on_last = None
            repeat_on_last = None
            if control_id is not None:
                is_playing = getPlaystateFromPlayouts()
                shuffle_on = getShufflestateFromPlayouts()
                repeat_on = getRepeatstateFromPlayouts()
                if log is True:
                    if channels[control_id]=='webserver':
                        flexprint("[bold magenta]actual control zone (webserver): " + control_id + '[/bold magenta]')
                    else:
                        flexprint("[bold magenta]actual control zone (roon): " + channels[control_id] + '[/bold magenta]')
        time.sleep(0.1)
        GPIO.add_event_detect(controlswitch_gpio_top, GPIO.FALLING, callback=pressed_up, bouncetime=controlswitch_bouncetime)

def pressed_down(channel):
    global do_set_zone_control

    if display_cover is True:
        return

    time.sleep(0.1)
    if GPIO.event_detected(controlswitch_gpio_down):
        GPIO.remove_event_detect(controlswitch_gpio_down)
        if do_set_zone_control == True:
            do_set_zone_control = False
            clear_display('pressed_down')
            refresh_output_data()
            if log is True: flexprint('close zone control setup')
            if control_id is not None and log is True:
                if channels[control_id]=='webserver':
                    flexprint("actual control zone (webserver): " + control_id)
                else:
                    flexprint("actual control zone (roon): " + channels[control_id])
        else:
            mode = getShufflestateFromPlaymode(control_id)
            set_shuffle_mode(control_id, not mode, True)
        time.sleep(0.1)
        GPIO.add_event_detect(controlswitch_gpio_down, GPIO.FALLING, callback=pressed_down, bouncetime=controlswitch_bouncetime)

def pressed_left(channel):
    global control_id_update, zone_control_last_update_time

    if display_cover is True:
        return

    time.sleep(0.1)
    if GPIO.event_detected(controlswitch_gpio_left):
        GPIO.remove_event_detect(controlswitch_gpio_left)
        if do_set_zone_control == True:
            zone_control_last_update_time = datetime.now()
            keys = list(channels.keys())
            keys_len = len(keys)
            if keys_len > 0:
                if control_id_update is not None:
                    idx = keys.index(control_id_update)
                    idx = idx - 1
                else:
                    idx = 0
                if idx < 0:
                    idx = keys_len - 1
                control_id_update = keys[idx]
                name = control_id_update.replace(' ','') if channels[control_id_update]=='webserver' else channels[control_id_update]

                with canvas(device) as draw:
                    text(draw, (0, 0), get_message('control zone') + get_zone_control_shortname(': ') + get_zone_control_shortname(name), fill="white", font=proportional(CP437_FONT))
        else:
            play_previous(control_id)
        time.sleep(0.1)
        GPIO.add_event_detect(controlswitch_gpio_left, GPIO.FALLING, callback=pressed_left, bouncetime=controlswitch_bouncetime)

def pressed_right(channel):
    global control_id_update, zone_control_last_update_time

    if display_cover is True:
        return

    time.sleep(0.1)
    if GPIO.event_detected(controlswitch_gpio_right):
        GPIO.remove_event_detect(controlswitch_gpio_right)
        if do_set_zone_control == True:
            zone_control_last_update_time = datetime.now()
            keys = list(channels.keys())
            keys_len = len(keys)
            if keys_len > 0:
                if control_id_update is not None:
                    idx = keys.index(control_id_update)
                    idx = idx + 1
                else:
                    idx = 0
                if idx >= keys_len:
                    idx = 0
                control_id_update = keys[idx]
                name = control_id_update.replace(' ','') if channels[control_id_update]=='webserver' else channels[control_id_update]

                with canvas(device) as draw:
                    text(draw, (0, 0), get_message('control zone') + get_zone_control_shortname(': ') + get_zone_control_shortname(name), fill="white", font=proportional(CP437_FONT))
        else:
            play_next(control_id)
        time.sleep(0.1)
        GPIO.add_event_detect(controlswitch_gpio_right, GPIO.FALLING, callback=pressed_right, bouncetime=controlswitch_bouncetime)

def pressed_enter(channel):
    global playmode, do_set_zone_control, control_id, control_zone, is_playing_last, shuffle_on_last, repeat_on_last, is_playing, shuffle_on, repeat_on

    if display_cover is True:
        return

    time.sleep(0.1)
    if GPIO.event_detected(controlswitch_gpio_center):
        GPIO.remove_event_detect(controlswitch_gpio_center)
        if do_set_zone_control == True:
            do_set_zone_control = False
            control_id = control_id_update
            control_zone = control_id
            clear_display('pressed_enter')
            refresh_output_data(True)
            if log is True: flexprint('close zone control setup')
            is_playing_last = None
            shuffle_on_last = None
            repeat_on_last = None
            if control_id is not None:
                is_playing = getPlaystateFromPlayouts()
                shuffle_on = getShufflestateFromPlayouts()
                repeat_on = getRepeatstateFromPlayouts()
                if log is True:
                    if channels[control_id]=='webserver':
                        flexprint("[bold magenta]actual control zone (webserver): " + control_id + '[/bold magenta]')
                    else:
                        flexprint("[bold magenta]actual control zone (roon): " + channels[control_id] + '[/bold magenta]')
        else:
            mode = getPlaystateFromPlaymode(control_id)
            set_play_mode(control_id, not mode, True)
        time.sleep(0.1)
        GPIO.add_event_detect(controlswitch_gpio_center, GPIO.FALLING, callback=pressed_enter, bouncetime=controlswitch_bouncetime)

def send_webserver_zone_control(control_id, code, search = '', detail = '', detail2 = ''):
    if webservers_show == True and control_id is not None:
        url = ''
        name_parts = control_id.split('-')

        for idx,data in enumerate(webservers_zones,1):
            name = data['name']
            if name == name_parts[0]:
                url = data['url']
                break
        if channels[control_id] == 'webserver' and url != '':
            payload = {'source':name_parts[1], 'code':code, 'search': search, 'detail': detail, 'detail2': detail2}
            flexprint('send_webserver_zone_control => payload: ' + str(payload))
            
            requestlist = [{'name':name,'url':url,'data':payload}]            
            try:
                async_web_response = async_web_requests_with_timing(requestlist)
                if len(async_web_response) > 0 and 'error' not in async_web_response[0]:
                    result = async_web_response[0]['text']

                    playcontrols = ['previous','next','stop','play','shuffle','noshuffle','repeat','norepeat']
                    if code in playcontrols:
                        print('playcontrol result: ' + str(result))
                        get_webserver_results_and_fast_updating_of_coverplayer_and_app(name_parts[0],url,result)
                    return result
                else:
                    flexprint('send_webserver_zone_control => async response is empty!')
                    return
            except HTTPError as e:
                if errorlog is True:
                    flexprint('The webserver couldn\'t fulfill the request.')
                    flexprint(name + ': error code: ', e.code)
            except URLError as e:
                if errorlog is True: 
                    flexprint(name + ': failed to reach the webserver.')
                    flexprint('reason: ', e.reason)
            except Exception as e:
                if errorlog is True: flexprint('webserver_zone_control error: ', str(e))

def getPlaystateFromPlayouts():
    idle = False
    if control_id is not None and control_id in channels.keys() and channels[control_id]=='webserver':
        name_parts = control_id.split('-')
        serverName = name_parts[0]
        zoneName = name_parts[1]
        if serverName in web_playouts:
            zones = web_playouts[serverName]
            for item in web_playouts[serverName]:
                if 'zone' in item and item['zone'] == zoneName:
                    idle = 'status' in item and item['status'] != 'playing'
                    playmode[control_id] = 'stop' if idle is True else 'play'
                    break
    if control_id is not None and control_id in channels.keys() and channels[control_id]!='webserver':
        zoneName = channels[control_id]
        idle = zoneName in roon_playouts and 'status' in roon_playouts[zoneName] and roon_playouts[zoneName]['status'] == 'not running'
        playmode[control_id] = 'stop' if idle is True else 'play'
    return idle is False

def getShufflestateFromPlayouts():
    shuffle = False
    if control_id is not None and control_id in channels.keys() and channels[control_id]=='webserver':
        name_parts = control_id.split('-')
        serverName = name_parts[0]
        zoneName = name_parts[1]
        if serverName in web_playouts:
            zones = web_playouts[serverName]
            for item in web_playouts[serverName]:
                if 'zone' in item and item['zone'] == zoneName:
                    shuffle = 'shuffle' in item and item['shuffle'] == 'true'
                    shufflemode[control_id] = 'shuffle' if shuffle is True else 'noshuffle'
                    break
    if control_id is not None and control_id in channels.keys() and channels[control_id]!='webserver':
        zoneName = channels[control_id]
        shuffle = zoneName in roon_playouts and 'shuffle' in roon_playouts[zoneName] and roon_playouts[zoneName]['shuffle'] == True
        shufflemode[control_id] = 'shuffle' if shuffle is True else 'noshuffle'
    return shuffle

def getRepeatstateFromPlayouts():
    shuffle = False
    if control_id is not None and control_id in channels.keys() and channels[control_id]=='webserver':
        name_parts = control_id.split('-')
        serverName = name_parts[0]
        zoneName = name_parts[1]
        if serverName in web_playouts:
            zones = web_playouts[serverName]
            for item in web_playouts[serverName]:
                if 'zone' in item and item['zone'] == zoneName:
                    repeat = 'repeat' in item and (item['repeat'] == 'true' or item['repeat'] == 'all' or item['repeat'] == 'one')
                    repeatmode[control_id] = 'repeat' if repeat is True else 'norepeat'
                    break
    if control_id is not None and control_id in channels.keys() and channels[control_id]!='webserver':
        zoneName = channels[control_id]
        repeat = zoneName in roon_playouts and 'repeat' in roon_playouts[zoneName] and roon_playouts[zoneName]['repeat'] == True
        repeatmode[control_id] = 'repeat' if repeat is True else 'norepeat'
    return repeat

def degToCompass(num):
    val=int((num/22.5)+.5)
    return convert_special_chars(deg_to_compass[(val % 16)])

def get_weather(weather_api, location):
    global weatherstr, weatherlines, weather_fetch_count

    weatherstr = ''
    lines = []
    weather_fetch_count += 1
    try:
        weather_data = weather_api.get_current(city=location, units='M').get()
    except Exception as e:
        if errorlog is True: flexprint('[red]weather error: [/red]' + str(e))
    else:
        temperature = weather_data[0]['temp'] # Temperature
        description = weather_data[0]['weather']['description'] # Text weather description.
        feel_temperature = weather_data[0]['app_temp'] # Apparent/Feels Like temperature
        humidity = weather_data[0]['rh'] # Relative humidity (%)
        pressure = weather_data[0]['pres'] # Pressure (mb)
        wind_spd = int(weather_data[0]['wind_spd']*3600/1000) # Wind speed (Default m/s)
        wind_dir = weather_data[0]['wind_dir'] # Wind direction (degrees)
        clouds = weather_data[0]['clouds'] # cloud coverage (%)
        uv = round(weather_data[0]['uv']) # UV Index (0-11+)
        snow = weather_data[0]['snow'] # Snowfall (default mm/hr)
        precip = weather_data[0]['precip'] # Liquid equivalent precipitation rate (default mm/hr)
        sunrise = datetime.strptime(datetime.now().strftime("%Y-%m-%d") + ' ' + weather_data[0]['sunrise'].strftime("%H:%M") + ':00', '%Y-%m-%d %H:%M:%S').replace(tzinfo=from_zone)
        sunrise = sunrise.astimezone(to_zone).strftime("%H:%M") # Sunrise time UTC (HH:MM) conversion to local time
        sunset = datetime.strptime(datetime.now().strftime("%Y-%m-%d") + ' ' + weather_data[0]['sunset'].strftime("%H:%M") + ':00', '%Y-%m-%d %H:%M:%S').replace(tzinfo=from_zone)
        sunset = sunset.astimezone(to_zone).strftime("%H:%M") # Sunset time UTC (HH:MM) conversion to local time

        weatherstr = get_weather_property('Weather') + ' ' + location + ': ' + str(temperature) + ' ' + get_weather_property('degree')
        lines = vertical_longtext_split_and_append(get_weather_property('Weather') + ' ' + convert_special_chars(location),lines)
        lines.append(str(temperature) + ' ' + get_weather_property('degree'))

        if with_feel_temperature is True:
            weatherstr += ', ' + get_weather_property('Feel Temperature') + ' ' + str(feel_temperature) + ' ' + get_weather_property('degree')
            lines = vertical_longtext_split_and_append(get_weather_property('Feel Temperature') + ' ' + str(feel_temperature) + ' ' + get_weather_property('degree'),lines)
        if with_rain is True and precip > 0:
            weatherstr += ', ' + get_weather_property('Rain') + ': ' + str(precip) + ' mm/hr'
            lines = vertical_longtext_split_and_append(get_weather_property('Rain') + ': ' + str(precip) + ' mm/hr',lines)
        if with_wind_spd is True:
            weatherstr += ', ' + get_weather_property('Wind') + ': ' + str(wind_spd) + ' km/h'
            lines = vertical_longtext_split_and_append(get_weather_property('Wind') + ': ' + str(wind_spd) + ' km/h',lines)
        if with_wind_dir is True:
            weatherstr += ' '
            if with_wind_spd is True:
                lines = vertical_longtext_split_and_append(get_weather_property('Direction') + ' ' + degToCompass(wind_dir),lines)
            else:
                weatherstr += get_weather_property('Wind') + ' '
                lines = vertical_longtext_split_and_append(get_weather_property('Wind') + ' ' + get_weather_property('Direction') + ' ' + degToCompass(wind_dir),lines)
            weatherstr += get_weather_property('Direction') + ' ' + degToCompass(wind_dir)
        if with_humidity is True:
            weatherstr += ', ' + get_weather_property('Humidity') + ': ' + str(humidity) + '%'
            lines = vertical_longtext_split_and_append(get_weather_property('Humidity') + ': ' + str(humidity) + '%',lines)
        if with_pressure is True:
            weatherstr += ', ' + get_weather_property('Pressure') + ': ' + str(pressure) + ' hPa'
            lines = vertical_longtext_split_and_append(get_weather_property('Pressure') + ': ' + str(pressure) + ' hPa',lines)
        if with_clouds is True and clouds > 0:
            weatherstr += ', ' + get_weather_property('Clouds') + ': ' + str(clouds) + '%'
            lines = vertical_longtext_split_and_append(get_weather_property('Clouds') + ': ' + str(clouds) + '%',lines)
        if with_snow is True and snow > 0:
            weatherstr += ', ' + get_weather_property('Snow') + ': ' + str(snow) + ' mm/hr'
            lines = vertical_longtext_split_and_append(get_weather_property('Snow') + ': ' + str(snow) + ' mm/hr',lines)
        if with_uv is True:
            weatherstr += ', UV (0-11): ' + str(uv)
            lines = vertical_longtext_split_and_append('UV (0-11): ' + str(uv),lines)
        if with_sunrise is True:
            weatherstr += ', ' + get_weather_property('Sunrise') + ': ' + sunrise + ' ' + get_message('h')
            lines = vertical_longtext_split_and_append(get_weather_property('Sunrise') + ': ' + sunrise + ' ' + get_message('h'),lines)
        if with_sunset is True:
            weatherstr += ', ' + get_weather_property('Sunset') + ': ' + sunset + ' ' + get_message('h')
            lines = vertical_longtext_split_and_append(get_weather_property('Sunset') + ': ' + sunset + ' ' + get_message('h'),lines)
        if with_description is True:
            weatherstr += ', ' + get_weather_descr(description)
            lines = vertical_longtext_split_and_append(get_weather_descr(description),lines)

        weatherstr = convert_special_chars(weatherstr)
        weatherlines = lines

        if log is True: flexprint('weather update ' + str(weather_fetch_count) + ' @ ' + str(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    weather_timer = Timer(weather_update_interval, get_weather, (weather_api,location)) # update every 15minutes
    weather_timer.start()

def get_weather_descr(descr):
    descr = descr.strip()
    keys = list(weather_description.keys())

    try:
        idx = keys.index(descr)
        return convert_special_chars(weather_description[keys[idx]])
    except Exception as e:
        return descr

def get_weather_property(key):
    keys = list(weather_properties.keys())

    try:
        idx = keys.index(key)
        return convert_special_chars(weather_properties[keys[idx]])
    except Exception as e:
        return key

def get_message(key):
    keys = list(messages.keys())

    try:
        idx = keys.index(key)
        return convert_special_chars(messages[keys[idx]])
    except Exception as e:
        return key

def zone_selection(selection):
    global control_id, is_playing_last, shuffle_on_last, repeat_on_last, is_playing, shuffle_on, repeat_on
    flexprint("[bold magenta]zone selection:[/bold magenta]", selection)
    if selection in channels.keys() and channels[selection] == 'webserver':
        control_id = selection
    else:
        if selection in channels.values():
            for id, name in channels.items():
                if channels[id] != 'webserver' and name == selection:
                    control_id = id
                    break
    is_playing_last = None
    shuffle_on_last = None
    repeat_on_last = None
    is_playing = getPlaystateFromPlayouts()
    shuffle_on = getShufflestateFromPlayouts()
    repeat_on = getRepeatstateFromPlayouts()

    return [is_playing, shuffle_on, repeat_on]

def on_control_click(action):
    flexprint("on_control_click:", action)
    if action=='backward':
        play_previous(control_id)
    if action=='pause':
        set_play_mode(control_id, False, True)
    if action=='play': 
        set_play_mode(control_id, True, True)
    if action=='forward':
        play_next(control_id)
    if action=='shuffle_on':
        set_shuffle_mode(control_id, True, True)
    if action=='shuffle_off':
        set_shuffle_mode(control_id, False, True)
    if action=='repeat_on':
        set_repeat_mode(control_id, True, True)
    if action=='repeat_off':
        set_repeat_mode(control_id, False, True)
    return [is_playing, shuffle_on, repeat_on]

def roon_get_artists(output_id, name):
    try:
        artists = roonapi.list_media(output_id, ["Library", "Artists", name ])
        if artists is not None and len(artists) > 0:
            return artists
        artists = roonapi.list_media(output_id, ["Library", "Artists", name.title() ])
        if artists is not None and len(artists) > 0:
            return artists
        artists = roonapi.list_media(output_id, ["Library", "Artists", name.upper() ])
        if artists is not None and len(artists) > 0:
            return artists
        artists = roonapi.list_media(output_id, ["Library", "Artists", name.lower() ])
        return artists
    except Exception as e:
        return []

def roon_get_genres(output_id, name):
    try:
        if name == '':
            name = '__all__'
        genres = roonapi.list_media(output_id, ["Genres", name])
        if genres is not None and len(genres) > 0:
            #genres.sort()
            return genres
        if name == '__all__':
            return []
        genres = roonapi.list_media(output_id, ["Genres", name.title() ])
        if genres is not None and len(genres) > 0:
            #genres.sort()
            return genres
        return []
    except Exception as e:
        return []

def roon_get_genre_artists(output_id, genre):
    try:
        artists = roonapi.list_media(output_id,["Genres", genre, "Artists", '__all__'])
        if artists and len(artists) > 0:
            return artists
        return []
    except Exception as e:
        return []

def roon_get_radios(output_id, name):
    try:
        if name == '':
            name = '__all__'
        radios = roonapi.list_media(output_id, ["My Live Radio", name ])
        if radios is not None and len(radios) > 0:
            return radios
        radios = roonapi.list_media(output_id, ["My Live Radio", name.title() ])
        if radios is not None and len(radios) > 0:
            return radios
        radios = roonapi.list_media(output_id, ["My Live Radio", name.upper() ])
        if radios is not None and len(radios) > 0:
            return radios
        radios = roonapi.list_media(output_id, ["My Live Radio", name.lower() ])
        return radios
    except Exception as e:
        return []

def roon_get_artist_albums(output_id, artist):
    try:
        albums = roonapi.list_media(output_id, ["Library", "Artists", artist, '__all__'])
        if albums:
            if "Play Artist" in albums:
                albums.remove("Play Artist")
        album = None
        if albums and len(albums) > 0:
            album = albums[0]
            return albums
        if album is None:
            flexprint("No albums found")
            return []
        return []
    except Exception as e:
        return []

def roon_get_artist_album_tracks(output_id, artist, album):
    try:
        tracks = roonapi.list_media(output_id, ["Library", "Artists", artist, album, '__all__'])
        if tracks and len(tracks) > 0:
            return tracks
        return []
    except Exception as e:
        return []

def roon_get_tracks(output_id, track):
    try:
        tracks = roonapi.list_media(output_id, ["Library", "Tracks", track])
        if tracks and len(tracks) > 0:
            if "Play Album" in tracks:
                tracks.remove("Play Album")
            return tracks
        tracks = roonapi.list_media(output_id, ["Library", "Tracks", track.title() ])
        if tracks and len(tracks) > 0:
            return tracks
        return []
    except Exception as e:
        return []

def roon_get_playlists(output_id, name):
    try:
        if name == '':
            name = '__all__'
        playlists = roonapi.list_media(output_id, ["Playlists", name])
        if playlists and len(playlists) > 0:
            return playlists
        playlists = roonapi.list_media(output_id, ["Playlists", name.title() ])
        if playlists and len(playlists) > 0:
            return playlists
        playlists = roonapi.list_media(output_id, ["Playlists", name.upper() ])
        if playlists and len(playlists) > 0:
            return playlists
        playlists = roonapi.list_media(output_id, ["Playlists", name.lower() ])
        if playlists and len(playlists) > 0:
            return playlists
        return []
    except Exception as e:
        return []

def roon_get_playlist_tracks(output_id, playlist):
    try:
        tracks = roonapi.list_media(output_id, ["Playlists", playlist, '__all__'])
        if tracks and len(tracks) > 0:
            return tracks
        return []
    except Exception as e:
        return []

def spotipy_init():
    """
    Initializes Spotipy with forced IPv4, custom session and optional access data.
    If no access data is transferred, the environment variables are used.
    """

    if spotify_client_id=='' or spotify_client_secret=='':
        return coverplayer_lang['spotify_no_credentials']

    # IPv4-only Monkeypatch (for DS-Lite as example)
    try:
        import urllib3.util.connection as urllib3_cn
        urllib3_cn.allowed_gai_family = lambda: socket.AF_INET
    except Exception as e:
        flexprint("Warning: IPv4 forcing failed:", e)
        return coverplayer_lang['spotify_ipv4_failed']

    # Prepare session with SSL context
    class IPv4OnlyAdapter(requests.adapters.HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            context = ssl.create_default_context()
            kwargs["ssl_context"] = context
            self.poolmanager = urllib3.poolmanager.PoolManager(*args, **kwargs)

    session = requests.Session()
    session.mount("https://", IPv4OnlyAdapter())

    # Initialize Spotipy with session
    auth_manager = SpotifyClientCredentials()
    try:
        spotify = spotipy.Spotify(auth_manager=auth_manager, requests_session=session)
    except Exception as e:
        flexprint('Spotify auth error')
        return coverplayer_lang['spotify_auth_error']

    return spotify

def spotify_search_artist(artist_name):
    try:
        spotify = spotipy_init()
        if isinstance(spotify, str):
            return spotify

        results = spotify.search(artist_name, limit=10, type='artist')
        artists = results['artists']['items']
        return artists
    except Exception as e:
        return []

def spotify_search_artist_album(artist_name, album_name):
    try:
        spotify = spotipy_init()
        if isinstance(spotify, str):
            return spotify

        query='artist:"'+artist_name+'" album:"'+album_name + '"'
        results = spotify.search(query, limit=10, type='album')
        album = results['albums']['items'][0] if 'albums' in results and 'items' in results['albums'] and len(results['albums']['items']) > 0 else None

        return album
    except Exception as e:
        return []

def spotify_search_artists_by_genre(genre_name):
    try:
        spotify = spotipy_init()
        if isinstance(spotify, str):
            return spotify

        results = spotify.search('' + ' genre:' + genre_name, limit=20, type='artist')
        artists = list(filter(partial(is_not, None), results['artists']['items']))
        return artists
    except Exception as e:
        return []

def spotify_search_playlists_by_genre(genre_name):
    try:
        spotify = spotipy_init()
        if isinstance(spotify, str):
            return spotify

        results = spotify.search('' + ' genre:' + genre_name, limit=20, type='playlist')
        playlists = list(filter(partial(is_not, None), results['playlists']['items']))
        return playlists
    except Exception as e:
        return []

def spotify_get_artist_albums(artist_id):
    try:
        spotify = spotipy_init()
        if isinstance(spotify, str):
            return spotify

        results = spotify.artist_albums('spotify:artist:' + artist_id, album_type='album')
        albums = results['items']
        if len(albums) == 0:
            return []

        while results['next']:
            results = spotify.next(results)
            albums.extend(results['items'])

        return albums
    except Exception as e:
        return []

def spotify_get_playlist_tracks(playlist_id):
    try:
        spotify = spotipy_init()
        if isinstance(spotify, str):
            return spotify

        results = spotify.playlist_items(playlist_id, fields="items", additional_types=('tracks'))
        
        tracks = results['items']
        if len(tracks) == 0:
            return []

        #while results['next']:
            #results = spotify.next(results)
            #tracks.extend(results['items'])

        return tracks
    except Exception as e:
        return []

def spotify_get_album_tracks(album_id):
    try:
        spotify = spotipy_init()
        if isinstance(spotify, str):
            return spotify

        results = spotify.album_tracks(album_id)
        tracks = results['items']

        return tracks
    except Exception as e:
        return []

def spotify_search_track(track_name):
    try:
        spotify = spotipy_init()
        if isinstance(spotify, str):
            return spotify

        results = spotify.search(track_name, limit=10, type='track')
        tracks = results['tracks']['items']
        return tracks
    except Exception as e:
        return []

def spotify_search_playlist(playlist_name):
    try:
        spotify = spotipy_init()
        if isinstance(spotify, str):
            return spotify

        results = spotify.search(playlist_name, limit=10, type='playlist')
        playlists = list(filter(partial(is_not, None), results['playlists']['items']))
        return playlists
    except Exception as e:
        return []

def replace_escaped_item(item):
    return item.replace('[dq]','"')

def replace_escaped_list(items):
    filteredItems = []
    for item in items:
        filteredItems.append(replace_escaped_item(item))
    return filteredItems

def on_search(value, zone, type):
    control_id = None
    albums = None
    is_webserver = False
    zonetype = ''
    if zone in channels.keys() and channels[zone] == 'webserver':
        zonetype = zone.split('-')[1] 
        control_id = zone
        is_webserver = True
    else:
        if zone in channels.values():
            for id, name in channels.items():
                if channels[id] != 'webserver' and name == zone:
                    control_id = id
                    break
    flexprint("roonmatrix => on_search:" + value + ', zone: ' + zone + ', control_id: ' + control_id + ', type:' + type)
    if is_webserver is True:
        if zonetype == 'Spotify':
            if type == 'artist':
                artists = spotify_search_artist(value)
                if isinstance(artists, str):
                    return artists
                if (len(artists) == 0):
                    meta = {"zonetype": zonetype, "type": 'artists', 'search': value}
                    return [meta, []]
                if (len(artists) != 1):
                    artists = list(map(lambda obj: {"name": obj['name'], "id": obj['id']}, artists))
                    meta = {"zonetype": zonetype, "type": 'artists', 'search': value}
                    return [meta, artists]
                artist = artists[0]
                albums = spotify_get_artist_albums(artist['id'])
                if isinstance(albums, str):
                    return albums
            if type == 'genre':
                genretype = 'playlists'
                if genretype=='artists':
                    artists = spotify_search_artists_by_genre(value)
                    if isinstance(artists, str):
                        return artists
                    if (len(artists) == 0):
                        meta = {"zonetype": zonetype, "type": 'artists', 'search': value}
                        return [meta, []]
                    artists = list(map(lambda obj: {"name": obj['name'] + ((' [' + ','.join(obj['genres']) + ']') if len(obj['genres']) > 0 else ''), "id": obj['id']}, artists))
                    meta = {"zonetype": zonetype, "type": 'artists', 'search': value}
                    return [meta, artists]
                if genretype=='playlists':
                    playlists = spotify_search_playlists_by_genre(value)
                    if isinstance(playlists, str):
                        return playlists
                    if (len(playlists) == 0):
                        meta = {"zonetype": zonetype, "type": 'playlists', 'search': value}
                        return [meta, []]
                    playlists = list(map(lambda obj: {"name": obj['name'], "id": obj['id']}, playlists))
                    meta = {"zonetype": zonetype, "type": 'playlists', 'search': value}
                    return [meta, playlists]
            if type == 'track':
                tracks = spotify_search_track(value)
                if isinstance(tracks, str):
                    return tracks
                tracks = list(map(lambda obj: {"name": obj['name'], "id": obj['id'], "artist": obj['artists'][0]['name'] if ('artists' in obj and len(obj['artists']) > 0 and 'name' in obj['artists'][0]) else None}, tracks))
            if type == 'playlist':
                playlists = spotify_search_playlist(value)
                if isinstance(playlists, str):
                    return playlists
                if (len(playlists) == 0):
                    meta = {"zonetype": zonetype, "type": 'playlists', 'search': value}
                    return [meta, []]
                if (len(playlists) != 1):
                    playlists = list(map(lambda obj: {"name": obj['name'], "id": obj['id']}, playlists))
                    meta = {"zonetype": zonetype, "type": 'playlists', 'search': value}
                    return [meta, playlists]
                playlist = playlists[0]
                tracks = spotify_get_playlist_tracks(playlist['id'])
                if isinstance(tracks, str):
                    return tracks
        if zonetype == 'Apple Music':
            if type == 'artist':
                value = value.replace('"','\\"')
                flexprint('************ Apple Music artist search value: ' + str(value))
                raw = send_webserver_zone_control(control_id, 'artists', value)
                if raw is None:
                    return [meta, []]
                flexprint('************ Apple Music artist search raw response: ' + str(raw))
                artists = json.loads(raw)
                if (len(artists) == 0):
                    meta = {"zonetype": zonetype, "type": 'artists', 'search': value}
                    return [meta, []]
                artists = replace_escaped_list(artists)
                if (len(artists) != 1):
                    meta = {"zonetype": zonetype, "type": 'artists', 'search': value.title()}
                    return [meta, artists]
                artist = artists[0].replace('"','\\\"')
                raw = send_webserver_zone_control(control_id, 'albums', artist)
                value = artist
                flexprint('artist '+str(artist)+' albums raw: ' + str(raw))
                if raw is None:
                    return [meta, []]
                albums = json.loads(raw)
                albums = replace_escaped_list(albums)
            if type == 'genre':
                value = value.replace('"','\\"')
                flexprint('************ Apple Music genre search value: ' + str(value))
                raw = send_webserver_zone_control(control_id, 'genres', value)
                if raw is None:
                    return [meta, []]
                flexprint('************ Apple Music genre search raw response: ' + str(raw))
                genres = json.loads(raw)
                if (len(genres) == 0):
                    meta = {"zonetype": zonetype, "type": 'genres', 'search': value}
                    return [meta, []]
                genres = replace_escaped_list(genres)
                if (len(genres) != 1):
                    meta = {"zonetype": zonetype, "type": 'genres', 'search': value.title()}
                    return [meta, genres]
                genre = genres[0].replace('"','\\\"')
                raw = send_webserver_zone_control(control_id, 'artists-in-genre', genre)
                value = genre
                flexprint('genre '+str(genre)+' artists raw: ' + str(raw))
                if raw is None:
                    return [meta, []]
                artists = json.loads(raw)
                artists = replace_escaped_list(artists)
            if type == 'playlist':
                value = value.replace('"','\\"')
                #value = value.replace('"','[dq]')
                raw = send_webserver_zone_control(control_id, 'playlists', value)
                if raw is None:
                    return [meta, []]
                flexprint('playlist apple music raw: ' + str(raw))
                playlists = json.loads(raw)
                if (len(playlists) == 0):
                    meta = {"zonetype": zonetype, "type": 'playlists', 'search': value}
                    return [meta, []]
                playlists = replace_escaped_list(playlists)
                if (len(playlists) != 1):
                    meta = {"zonetype": zonetype, "type": 'playlists', 'search': value.title()}
                    return [meta, playlists]
                playlist = playlists[0].replace('"','\\\"')
                flexprint('single playlist: ' + str(playlist))
                raw = send_webserver_zone_control(control_id, 'playlist-tracks', playlist)
                flexprint('#applemusic raw: ' + str(raw))
                if raw is None:
                    return [meta, []]
                flexprint('#applemusic before loads: ' + str(raw))
                tracks = json.loads(raw)
                tracks = replace_escaped_list(tracks)
                #tracks.insert(0, {"name": self.lang['play_playlist'].title(), "id": "[FULLPLAYLIST]"})
                flexprint('#applemusic tracks escaped: ' + str(tracks))
                meta = {"zonetype": zonetype, "type": 'tracks', 'search': playlist, 'playlist': playlist}
                return [meta, tracks]
            if type == 'track':
                value = value.replace('"','\\"')
                flexprint('************ Apple Music track search value: ' + str(value))
                raw = send_webserver_zone_control(control_id, 'tracks-with-artist', value)
                if raw is None:
                    return [meta, []]
                flexprint('************ Apple Music track search raw response: ' + str(raw))
                tracks = json.loads(raw)
                tracks = replace_escaped_list(tracks)
        if type == 'artist':
            meta = {"zonetype": zonetype, "type": 'albums', 'search': value, "artist": value}
            return [meta, albums]
        if type == 'genre':
            meta = {"zonetype": zonetype, "type": 'artists', 'search': value, "genre": value}
            return [meta, artists]
        if type == 'track':
            meta = {"zonetype": zonetype, "type": 'tracks', 'search': value}
            flexprint('track search: ' + str(tracks))
            return [meta, tracks]
    if is_webserver is False and control_id is not None and zone in channels.values():
        zonetype = 'Roon'
        outputs = roonapi.outputs
        output_id = None
        for (k, v) in outputs.items():
            if zone in v["display_name"]:
                output_id = k
                flexprint("roonmatrix => output_id:" + output_id)
        if output_id is not None:
            if type == 'artist':
                artists = roon_get_artists(output_id, value)
                flexprint('roon_get_artists count: ' + str(len(artists)) + ' for search of: ' + value)
                if (len(artists) == 0):
                    meta = {"zonetype": zonetype, "type": 'artists', 'search': value.title()}
                    return [meta, []]
                if (len(artists) != 1):
                    meta = {"zonetype": zonetype, "type": 'artists', 'search': value.title()}
                    return [meta, artists]
                albums = roon_get_artist_albums(output_id, artists[0])
                meta = {"zonetype": zonetype, "type": 'albums', 'search': value.title(), "artist":artists[0]}
                return [meta, albums]
            if type == 'genre':
                genres = roon_get_genres(output_id, value)
                flexprint('roon_get_genres count: ' + str(len(genres)) + ' for search of: ' + value)
                if (len(genres) == 0):
                    meta = {"zonetype": zonetype, "type": 'genres', 'search': value.title()}
                    return [meta, []]
                if (len(genres) != 1):
                    meta = {"zonetype": zonetype, "type": 'genres', 'search': value.title()}
                    return [meta, genres]
                artists = roon_get_genre_artists(output_id, genres[0])
                meta = {"zonetype": zonetype, "type": 'artists', 'search': value.title(), "genre":genres[0]}
                return [meta, artists]
            if type == 'track':
                tracks = roon_get_tracks(output_id, value)
                tracks = list(OrderedDict.fromkeys(tracks)) # remove doubles
                flexprint('roon_get_tracks count: ' + str(len(tracks)) + ' for search of: ' + value)
                if (len(tracks) > 0):
                    meta = {"zonetype": zonetype, "type": 'tracks', 'search': value.title()}
                    return [meta, tracks]
                else:
                    meta = {"zonetype": zonetype, "type": 'tracks', 'search': value.title()}
                    return [meta, []]
            if type == 'playlist':
                playlists = roon_get_playlists(output_id, value)
                flexprint('roon_get_playlists count: ' + str(len(playlists)) + ' for search of: ' + value)
                if (len(playlists) == 0):
                    meta = {"zonetype": zonetype, "type": 'playlists', 'search': value.title()}
                    return [meta, []]
                if (len(playlists) != 1):
                    meta = {"zonetype": zonetype, "type": 'playlists', 'search': value.title()}
                    return [meta, playlists]
                tracks = roon_get_playlist_tracks(output_id, playlists[0])
                meta = {"zonetype": zonetype, "type": 'tracks', 'search': playlists[0], "playlist":playlists[0]}
                return [meta, tracks]
            if type == 'radio':
                radios = roon_get_radios(output_id, value)
                flexprint('roon_get_radios count: ' + str(len(radios)) + ' for search of: ' + value)
                if (len(radios) == 0):
                    meta = {"zonetype": zonetype, "type": 'radios', 'search': value.title()}
                    return [meta, []]
                if (len(radios) != 1):
                    meta = {"zonetype": zonetype, "type": 'radios', 'search': value.title()}
                    return [meta, radios]
                radio = radios[0]
                meta = {"zonetype": zonetype, "type": 'radio', 'search': value.title(), "radio":radios[0]}
                try:
                    roonapi.play_media(output_id, ["My Live Radio", radio], None, False)
                except Exception as e:
                    flexprint('roonapi.play_media error: ' + str(e))
                return [meta, radios]
    meta = {"zonetype": zonetype, "type": 'search', 'search': value.title()}
    return [meta, []]

def on_itemclick(meta, search, itemname, zone):
    control_id = None
    is_webserver = False
    is_spotify = False
    if zone in channels.keys() and channels[zone] == 'webserver':
        is_spotify = zone.split('-')[1] == 'Spotify'
        control_id = zone
        is_webserver = True
    else:
        if zone in channels.values():
            for id, name in channels.items():
                if channels[id] != 'webserver' and name == zone:
                    control_id = id
                    break
    flexprint('roonmatrix => on_itemclick, meta: ' + str(meta) + ', search: ' + search + ', itemname: ' + itemname + ', zone: ' + zone + ', control_id: ' + control_id)
    if is_webserver is True:
        if is_spotify is True:
            if meta['type'] == 'artists':
                albums = spotify_get_artist_albums(itemname)
                if isinstance(albums, str):
                    return albums
                albums = list(map(lambda obj: {"name": obj['name'], "id": obj['id']}, albums))
                return ['albums', search, albums]
            if meta['type'] == 'albums':
                if 'searchtype' in meta and meta['searchtype']=='tracklist':
                    album_obj = spotify_search_artist_album(meta['artist'], meta['album'])
                    if isinstance(album_obj, str):
                        return album_obj
                    if album_obj is None:
                        return ['tracks', search, itemname, []]
                    itemname = album_obj['id']
                tracks = spotify_get_album_tracks(itemname)
                if isinstance(tracks, str):
                    return tracks
                tracknames = list(map(lambda obj: {"name": obj['name'], "id": obj['id'], "track_number": obj['track_number']}, tracks))
                meta['tracks'] = tracknames
                return ['tracks', search, itemname, tracknames]
            if meta['type'] == 'playlists':
                tracks = spotify_get_playlist_tracks(itemname)
                if isinstance(tracks, str):
                    return tracks
                tracknames = list(map(lambda obj: {"name": obj['track']['name'] + ' [' + ', '.join(list(map(lambda obj: obj['name'], obj['track']['artists']))) + ']', "id": obj['track']['uri']}, tracks))
                meta['tracks'] = tracknames
                return ['tracks', search, itemname, tracknames]
            if meta['type'] == 'tracks':
                if 'artist' in meta:
                    send_webserver_zone_control(control_id, 'playtrack', itemname)
                    return ['track', meta['artist'], itemname]
                elif 'playlist' in meta:
                    if len(itemname) > 0 and '"' in itemname and '\\\"' not in itemname:
                        itemname = itemname.replace('"', '\\"')
                    send_webserver_zone_control(control_id, 'play-playlist-track', itemname)
                    return ['track', meta['playlist'], itemname]
                else:
                    send_webserver_zone_control(control_id, 'playtrack', 'spotify:track:' + itemname)
                    return ['track', itemname]
        else:
            if meta['type'] == 'artists':
                raw = send_webserver_zone_control(control_id, 'albums', itemname)
                if raw is None:
                    return ['albums', search, []]
                albums = json.loads(raw)
                albums = replace_escaped_list(albums)
                return ['albums', search, albums]
            if meta['type'] == 'genres':
                raw = send_webserver_zone_control(control_id, 'artists-in-genre', itemname)
                if raw is None:
                    return ['artists', search, []]
                artists = json.loads(raw)
                artists = replace_escaped_list(artists)
                return ['artists', search, artists]
            if meta['type'] == 'albums':
                itemname = itemname.replace('"', '\\\"')
                raw = send_webserver_zone_control(control_id, 'albumtracks', search, itemname)
                if raw is None:
                    return ['tracks', search, itemname, []]
                tracks = json.loads(raw)
                tracks = list(map(lambda string: {"name": replace_escaped_item(string.replace('|','. ')),"id": replace_escaped_item(string.split('|')[1])}, tracks))
                meta['tracks'] = tracks
                flexprint('on_itemclick webserver ==> search: ' + search + ', album: ' + itemname + ', track to play: ' + str(tracks[0]) if len(tracks) > 0 else 'None' + ', tracks('+str(len(tracks))+'): ' + str(tracks))
                return ['tracks', search, itemname, tracks]
            if meta['type'] == 'playlists':
                flexprint('applemusic on_itemclick playlists ===> meta: ' + str(meta) + ', playlist: ' + itemname)
                itemname = itemname.replace('"', '\\\"')
                raw = send_webserver_zone_control(control_id, 'playlist-tracks', itemname)
                if raw is None:
                    return ['tracks', search, itemname, []]
                tracks = json.loads(raw)
                tracks = list(map(lambda name: {"name": replace_escaped_item(name.split('|')[0]) + ' [' + replace_escaped_item(name.split('|')[1]) + ']', "id": replace_escaped_item(name.split('|')[0])}, tracks))
                meta['tracks'] = tracks
                flexprint('on_itemclick webserver playlist applemusic ==> search: ' + search + ', playlist: ' + itemname + ', track to play: ' + str(tracks[0]) if len(tracks) > 0 else 'None' + ', tracks('+str(len(tracks))+'): ' + str(tracks))
                return ['tracks', search, itemname, tracks]
            if meta['type'] == 'tracks':
                flexprint('applemusic on_itemclick tracks ===> meta: ' + str(meta) + ', track: ' + itemname)
                if 'album' in meta:
                    album = meta['album']
                    album = album.replace('"', '\\"')
                    if itemname == '[FULLALBUM]':
                        send_webserver_zone_control(control_id, 'playtrack', meta['artist'], album, meta['tracks'][0]['id'])
                    else:
                        if len(itemname) > 0 and '"' in itemname and '\\\"' not in itemname:
                            itemname = itemname.replace('"', '\\"')
                        send_webserver_zone_control(control_id, 'playtrack', meta['artist'], album, itemname)
                    return ['track', meta['artist'], meta['album'], itemname]
                elif 'playlist' in meta:
                    playlist = meta['playlist']
                    if len(playlist) > 0 and '"' in playlist and '\\\"' not in playlist:
                        playlist = playlist.replace('"', '\\"')                        
                    if itemname == '[FULLPLAYLIST]':
                        send_webserver_zone_control(control_id, 'play-playlist-track', playlist)
                    else:
                        if len(itemname) > 0 and '"' in itemname and '\\\"' not in itemname:
                            itemname = itemname.replace('"', '\\"')
                        send_webserver_zone_control(control_id, 'play-playlist-track', playlist, itemname)
                    return ['track', meta['playlist'], itemname]
                else:
                    if len(itemname) > 0 and '"' in itemname and '\\\"' not in itemname:
                        itemname = itemname.replace('"', '\\"')
                    if len(itemname.split('|')) == 2:
                        itemparts = itemname.split('|')
                        itemname = itemparts[0]
                        artist = itemparts[1]
                        send_webserver_zone_control(control_id, 'playtrack', itemname, artist)
                        return ['track', itemname, artist]
                    else:
                        send_webserver_zone_control(control_id, 'playtrack', itemname)                    
                    return ['track', itemname]
    if is_webserver is False and control_id is not None and zone in channels.values():
        outputs = roonapi.outputs
        output_id = None
        for (k, v) in outputs.items():
            if zone in v["display_name"]:
                output_id = k
                flexprint("roonmatrix => output_id:" + output_id)
        if output_id is not None:
            if meta['type'] == 'artists':
                if 'genre' in meta:
                    try:
                        albums = roon_get_artist_albums(output_id, search)
                    except Exception as e:
                        albums = []
                    return ['albums', itemname, albums]
                else:
                    return ['artist', itemname]
            if meta['type'] == 'genres':
                try:
                    artists = roon_get_genre_artists(output_id, itemname)
                except Exception as e:
                    artists = []
                return ['artists', itemname, artists]
            if meta['type'] == 'playlists':
                try:
                    tracks = roon_get_playlist_tracks(output_id, search)
                except Exception as e:
                    tracks = []
                meta['tracks'] = tracks
                flexprint('playlist tracks: ' + str(tracks))
                return ['tracks', search, itemname, tracks]
            if meta['type'] == 'albums':
                try:
                    tracks = roon_get_artist_album_tracks(output_id, search, itemname)
                except Exception as e:
                    tracks = []
                meta['tracks'] = tracks
                return ['tracks', search, itemname, tracks]
            if meta['type'] == 'tracks':
                if 'album' in meta:
                    flexprint('roonmatrix on_itemclick tracks ===> search: ' + meta['artist'] + ', album: ' + meta['album'] + ', track: ' + itemname)
                    try:
                        roonapi.play_media(output_id, ["Library", "Artists", meta['artist'], meta['album'], itemname], None, False)                        
                    except Exception as e:
                        flexprint('roonapi.play_media error: ' + str(e))
                    return ['track', meta['artist'], meta['album'], itemname]
                elif 'playlist' in meta:
                    flexprint('roonmatrix on_itemclick playlist ===> search: ' + meta['playlist'] + ', track: ' + itemname)
                    try:
                        roonapi.play_media(output_id, ["Playlists", meta['playlist'], itemname], None, False)                        
                    except Exception as e:
                        flexprint('roonapi.play_media error: ' + str(e))
                    return ['track', meta['playlist'], itemname]
                else:
                    flexprint('roonmatrix on_itemclick tracks ===> search: ' + meta['search'] + ', track: ' + itemname)
                    try:
                        roonapi.play_media(output_id, ["Library", "Tracks", itemname], None, False)
                    except Exception as e:
                        flexprint('roonapi.play_media error: ' + str(e))
                    return ['track', itemname]
            if meta['type'] == 'radios':
                try:
                    roonapi.play_media(output_id, ["My Live Radio", itemname], None, False)
                except Exception as e:
                    flexprint('roonapi.play_media error: ' + str(e))
                return ['radio', itemname]
    return

def transform_zone_data_to_string(displaystr, name, controlled, obj):
    if type(displaystr) == list:
        if len(displaystr) == 0 and playing_headline !='':
            displaystr = vertical_longtext_split_and_append(convert_special_chars(playing_headline),displaystr)
        if show_zone is True:
            sourcestr = get_message('Source') + ': ' + convert_special_chars(name)
            font = proportional(CP437_FONT)
            w, h = textsize(sourcestr, font)
            if w > device.width:
                displaystr.append(get_message('Source'))
                displaystr = vertical_longtext_split_and_append(convert_special_chars(name),displaystr)
            else:
                displaystr = vertical_longtext_split_and_append(sourcestr,displaystr)

            zonestr = controlled + get_message('Zone') + ': ' + convert_special_chars(obj["zone"])
            font = proportional(CP437_FONT)
            w, h = textsize(zonestr, font)
            if w > device.width:
                displaystr.append(controlled + get_message('Zone'))
                displaystr = vertical_longtext_split_and_append(convert_special_chars(obj["zone"]),displaystr)
            else:
                displaystr = vertical_longtext_split_and_append(zonestr,displaystr)
        if 'artist' in obj and obj["artist"] != '':
            if show_vertical_music_label is True:
                displaystr.append('< ' + get_message('Artist') + ' >')
            displaystr = vertical_longtext_split_and_append(convert_special_chars(obj["artist"]),displaystr)
        if show_album is True and 'album' in obj and obj["album"] != '':
            if show_vertical_music_label is True:
                displaystr.append('< ' + get_message('Album') + ' >')
            displaystr = vertical_longtext_split_and_append(convert_special_chars(obj["album"]),displaystr)
        if show_vertical_music_label is True:
            displaystr.append('< ' + get_message('Track') + ' >')
            displaystr = vertical_longtext_split_and_append(convert_special_chars(obj["track"]),displaystr)
        else:
            displaystr = vertical_longtext_split_and_append('=> ' + convert_special_chars(obj["track"]),displaystr)
    else:
        if displaystr == '' and playing_headline !='':
            displaystr += playing_headline + ': '
        if show_zone is True:
            displaystr += get_message('Source') + ': ' + name + ' => ' + controlled
            displaystr += get_message('Zone') + ': ' + obj["zone"] + ' / '
        if 'artist' in obj and obj["artist"] != '':
            displaystr += get_message('Artist') + ': "' + convert_special_chars(obj["artist"]) + '" / '
        if show_album is True and 'album' in obj and obj["album"] != '':
            displaystr += get_message('Album') + ': "' + convert_special_chars(obj["album"]) + '" / '
        if 'track' in obj:
            displaystr += get_message('Track') + ': "' + convert_special_chars(obj["track"]) + '"'
            displaystr = convert_special_chars(displaystr)
    return displaystr

def get_force_mode(displaystr):
    force = False
    if type(displaystr) != list and len(displaystr) >= 6 and displaystr[:6]=='force>':
        force = True
    if type(displaystr) == list and len(displaystr) > 0 and displaystr[0]=='force>':
        force = True
    return force

def set_data_changed_and_web_playouts_raw(result, name):
    global data_changed
    playout_changed = name not in web_playouts_raw or web_playouts_raw[name] != result
    if playout_changed is True:
        data_changed = True
    web_playouts_raw[name] = result

def webserver_zone_not_running_coverplayer_updates(result, name, obj):
    if log is True: flexprint('Webserver ' + name + ' (zone: ' + obj["zone"] + ') in status: ' + obj["status"])
    set_data_changed_and_web_playouts_raw(result, name)
    if display_cover is True and control_id is not None and channels[control_id]=='webserver':
        name_parts = control_id.split('-')
        zone = name_parts[1]
        if name == name_parts[0] and obj["zone"] == zone:
            cover_text_line_parts = []
            cover_text_line_parts.append(get_message('Zone') + ': ' + control_id)
            last_cover_url = ''
            last_cover_text_line_parts = '|'.join(cover_text_line_parts)
            zones = get_zone_names()
            is_playing = False
            shuffle_on = False
            repeat_on = False
            flexprint('[bold red]Coverplayer.update (web): not running[/bold red]')
            Coverplayer.update(-1, -1, None, is_playing, shuffle_on, repeat_on, cover_text_line_parts, zones, zone_selection, on_control_click, on_search, on_itemclick)

def prepend_cover_url(obj, url):
    if 'cover' in obj and len(obj["cover"]) > 0 and obj["cover"].startswith('http') is False:
        obj["cover"] = url[:1+url.rfind('/')] + obj["cover"] # cover url from Apple Music needs to prepend with webserver url
    return obj

def get_and_set_play_shuffle_repeat(name, obj):
    playing = 'status' in obj and obj['status'] == 'playing'
    shuffle = 'shuffle' in obj and obj['shuffle'] == 'true'
    repeat = 'repeat' in obj and (obj['repeat'] == 'true' or obj['repeat'] == 'all' or obj['repeat'] == 'one')
    zid = name + '-' + obj["zone"]
    set_play_mode(zid, playing, False)
    set_shuffle_mode(zid, shuffle, False)
    set_repeat_mode(zid, repeat, False)
    return {'playing': playing, 'shuffle':shuffle, 'repeat':repeat}

def add_separator(displaystr, playprops):
    if type(displaystr) == list:
        if playprops['playing'] is True and len(displaystr) > 0 and displaystr[0] != 'force>':
            displaystr.append('')
    else:
        if playprops['playing'] is True and displaystr != '':
            displaystr += separator
    return displaystr

def webserver_zone_running_coverplayer_updates(obj, playprops):
    global last_cover_url, last_cover_text_line_parts, is_playing, is_playing_last, shuffle_on, shuffle_on_last, repeat_on, repeat_on_last
    playpos = int(obj['position'])
    playlen = int(obj['total'])
    is_playing_last = is_playing
    shuffle_on_last = shuffle_on
    repeat_on_last = repeat_on
    is_playing = playprops['playing']
    shuffle_on = playprops['shuffle']
    repeat_on = playprops['repeat']

    if display_cover is True and 'cover' in obj and len(obj["cover"]) > 0:
        cover_text_line_parts = []
        cover_text_line_parts.append(get_message('Zone') + ': ' + control_id)
        if 'artist' in obj and obj["artist"] != '':
            cover_text_line_parts.append(get_message('Artist') + ': ' + filterIllegalChars(obj["artist"]))
        if show_album is True and 'album' in obj and obj["album"] != '':
            cover_text_line_parts.append(get_message('Album') + ': ' + filterIllegalChars(obj["album"]))
        if 'track' in obj and obj["track"] != '':
            cover_text_line_parts.append(get_message('Track') + ': ' + filterIllegalChars(obj["track"]))

        if (last_cover_url != obj["cover"] or last_cover_text_line_parts != '|'.join(cover_text_line_parts)):
            last_cover_url = obj["cover"]
            last_cover_text_line_parts = '|'.join(cover_text_line_parts)
            zones = get_zone_names()
            flexprint('[bold red]Coverplayer.update (web): ' + obj["cover"] + ', playpos: ' + str(playpos) + ', playlen: ' + str(playlen) + ', is_playing: ' + str(is_playing) + ', shuffle_on: ' + str(shuffle_on) + ', repeat_on: ' + str(repeat_on) + '[/bold red]')            
            Coverplayer.update(playpos, playlen, obj["cover"], is_playing, shuffle_on, repeat_on, cover_text_line_parts, zones, zone_selection, on_control_click, on_search, on_itemclick)
        else:
            flexprint('[bold red]Coverplayer.setpos (web): ' + obj["cover"] + ', playpos: ' + str(playpos) + ', playlen: ' + str(playlen) + ', is_playing: ' + str(is_playing) + ', shuffle_on: ' + str(shuffle_on) + ', repeat_on: ' + str(repeat_on) + '[/bold red]')            
            Coverplayer.setpos(playpos, playlen, obj["cover"], is_playing, shuffle_on, repeat_on, cover_text_line_parts)

def remove_prepended_from_displaystr(displaystr):
    if type(displaystr) == list:
        displaystr.pop(0) # remove first list item 'force>'
    else:
        displaystr = displaystr[6:] # remove prepended 'force>'
    return displaystr

def get_name_zone_and_controlled_marker(name, obj, playprops):
    controlled = ''
    if control_id is not None and channels[control_id]=='webserver':
        control_id_parts = control_id.split('-')
        name_part = control_id_parts[0]
        zone = control_id_parts[1]
        if name == name_part and obj["zone"] == zone:
            controlled = '[*] '
            webserver_zone_running_coverplayer_updates(obj, playprops)
        return {'name':name_part, 'zone':zone, 'controlled':controlled}
    return {'name':None, 'zone':None, 'controlled':controlled}

def get_webserver_results_and_fast_updating_of_coverplayer_and_app(name,url,result):
    if log is True: flexprint('get webserver results and fast updating of coverplayer and app => start, name: ' + name + ', url: ' + url)
    
    result = str(result).replace('\n','')
    if result.startswith('[{') and result.endswith('}]'):
        resultJson = json.loads(result)
        for obj in resultJson:
            if "status" in obj and obj["status"] == 'not running':
                webserver_zone_not_running_coverplayer_updates(result, name, obj)                            
            else:
                obj = prepend_cover_url(obj, url)
                playprops = get_and_set_play_shuffle_repeat(name, obj)
                props = get_name_zone_and_controlled_marker(name, obj, playprops)

                if name not in web_playouts_raw or web_playouts_raw[name] != result:
                    set_data_changed_and_web_playouts_raw(result, name)

        web_playouts[name] = resultJson
    else:
        if log is True: flexprint('Webserver ' + name + ' is not available')

    if log is True:
        flexprint('get webserver results and fast updating of coverplayer and app => end')
        flexprint('')

def get_playing_apple_or_spotify(webservers_zones,displaystr):
    if log is True: flexprint('get playing apple or spotify => start')
    breakToo = False
    force = get_force_mode(displaystr)
    webservers_zones = moveActualPlayerToFirstPosInWebserverZoneList(webservers_zones)
    active_zones = get_active_zones_from_webserver_onlinecheck(True)
    async_web_response = async_web_requests_with_timing(active_zones)
    #async_web_response = async_web_requests_with_timing(webservers_zones)
    
    for idx,data in enumerate(async_web_response,1):
        name = data['name']
        result = ''
        
        if 'error' in data :
            if log is True: flexprint('Webserver error: ' + data['error'])
        if 'status' in data and data['status'] == 200:
            result = str(data['text']).replace('\n','')
            if result != '':
                if result.startswith('[{') and result.endswith('}]'):
                    resultJson = json.loads(result)
                    for obj in resultJson:
                        if "status" in obj and obj["status"] == 'not running':
                            webserver_zone_not_running_coverplayer_updates(result, name, obj)                            
                        else:
                            obj = prepend_cover_url(obj, data['url'])
                            playprops = get_and_set_play_shuffle_repeat(name, obj)
                            displaystr = add_separator(displaystr, playprops)
                            props = get_name_zone_and_controlled_marker(name, obj, playprops)

                            if playprops['playing'] is True:
                                displaystr = transform_zone_data_to_string(displaystr, name, props['controlled'], obj)

                            if name not in web_playouts_raw or web_playouts_raw[name] != result:
                                set_data_changed_and_web_playouts_raw(result, name)

                                active = (control_id is not None and channels[control_id]=='webserver' and name == props['name'] and obj["zone"] == props['zone'])
                                if (force_webserver_update is True and force == True  and (force_active_webserver_zone_only is False or active is True)):
                                    if log is True: flexprint('web zone update => zone: ' + control_id + ', zone found: ' + str(active) + ', playing: ' + str(obj))
                                    displaystr = remove_prepended_from_displaystr(displaystr)
                                    breakToo = True # flag to break outer for loop too
                                    break
                    web_playouts[name] = resultJson
                    if breakToo is True:
                        break
                else:
                    if log is True: flexprint('Webserver ' + name + ' is not available')
            else:
                if log is True: flexprint('Webserver ' + name + ' with empty result')
        else:
            if log is True and 'status' in data: flexprint('Webserver with status ' + str(data['status']))
            if log is True and 'error' in data: flexprint('Webserver with error: ' + data['error'])

    if log is True:
        flexprint('get playing apple or spotify => end')
        flexprint('')
    return displaystr

def set_control_zone(waiting = True):
    clear_display('set_control_zone')
    time.sleep(1)

    if log is True: flexprint('control_id_update: ' + str(control_id_update))
    if control_id_update is None:
        channel_name = '-'
    else:
        channel_name = control_id_update.replace(' ','') if channels[control_id_update]=='webserver' else channels[control_id_update]

    if debug is True: flexprint('set_control_zone message')
    if display_cover is False:
        with canvas(device) as draw:
            text(draw, (0, 0), get_message('control zone') + get_zone_control_shortname(': ') + get_zone_control_shortname(channel_name), fill="white", font=proportional(CP437_FONT))

    if waiting is True:
        while do_set_zone_control == True:
            time.sleep(1)
        clear_display('set_control_zone waiting')

def set_fetch_time_before_clock_ends():
    global fetch_output_time

    time_start = datetime.now()
    estimated_end = time_start + timedelta(0,clock_max_show_time * 60)
    fetch_output_time = estimated_end - timedelta(0,build_seconds * 2)
    if log is True: flexprint('show_clock => estimated output fetch time: ' + fetch_output_time.strftime("%H:%M:%S"))

def show_clock():
    global last_idle_time, check_audioinfo, audioinfo_available

    if display_cover is True:
        return

    time_start = datetime.now()
    framecount = 0

    below_maxtime = ((datetime.now() - time_start).total_seconds()) < clock_max_show_time * 60
    while do_set_zone_control is False and audioinfo_available is False and ((music_required is True and ((exclusive_audio_mode is False and displaystr=='') or (exclusive_audio_mode is True and audio_playing == '')) and ((exclusive_audio_mode is False and clock_without_idle_time is True) or below_maxtime is True)) or (music_required is False and below_maxtime is True)):
        if led_modules < 15:
            timestr = datetime.now().strftime("%H:%M:%S")
            offset_x = ceil((led_modules - 7) / 2) * 8 if led_modules > 6 else 0
        else:
            timestr = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            offset_x = ceil((led_modules - 15) / 2) * 8

        with canvas(device) as draw:
            text(draw, (offset_x, 0), timestr, fill="white", font=proportional(CP437_FONT))
        time.sleep(1 / clock_refresh_per_second)
        framecount += 1
        if framecount % clock_refresh_per_second == 0:
            tick()
        below_maxtime = ((datetime.now() - time_start).total_seconds()) < clock_max_show_time * 60

    clear_display('show_clock')
    if music_required is True and clock_without_idle_time is False and displaystr=='':
        last_idle_time = datetime.now()
    else:
        last_idle_time = None
    check_audioinfo = False
    audioinfo_available = False

def split_word(word,lines):
    font = proportional(CP437_FONT)
    w, h = textsize(word, font)

    count = len(word)
    while w > device.width:
        while count > 0 and w > device.width:
            count -= 1
            part = word[:count]
            w, h = textsize(part, font)
        word = word[count:]
        lines.append(part)
        w, h = textsize(word, font)
    if len(word) > 0:
        lines.append(word)
    return lines

def vertical_longtext_split_and_append(text,lines):
    if display_cover is True:
        return lines

    font = proportional(CP437_FONT)

    if len(text) > 0:
        words = text.split(' ')

        line = ''
        for word in words:
            line_before = line
            if len(line) > 0:
                line += ' '
            line += word
            w, h = textsize(line, font)
            if w > device.width and line_before != '':
                lb_w, lb_h = textsize(line_before, font)
                if lb_w <= device.width:
                    lines.append(line_before)
                else:
                    lines = split_word(line_before,lines)
                    last_line = lines.pop()
                    lb_w, lb_h = textsize(last_line + ' ' + word, font)
                    if lb_w <= device.width:
                        last_line += (' ' + word)
                        word = ''
                    lines.append(last_line)
                line = word
        if len(line) > 0:
            if w <= device.width:
                lines.append(line)
            else:
                lines = split_word(line,lines)
    return lines

def get_rss_feed(displaystr):
    for idx,data in enumerate(rss_feeds,1):
        count = 0
        name = data['name']
        max = data['count']

        try:
            feed = feedparser.parse(data['url'])

            for entry in feed.entries:
                count += 1
                if type(displaystr) == list:
                    if len(displaystr) > 0:
                        displaystr.append('')
                else:
                    if displaystr != '':
                        displaystr += separator
                published = ''
                try:
                    published = (datetime.strptime(entry.published, '%a, %d %b %Y %H:%M:%S %z').strftime('%d.%m.%Y ' + get_message('at')+ ' %H:%M ' + get_message('h')))
                except Exception as e:
                    published = ''
                    try:
                        published = (datetime.strptime(entry.published, '%a, %d %b %Y %H:%M:%S %Z').strftime('%d.%m.%Y ' + get_message('at')+ ' %H:%M ' + get_message('h')))
                    except Exception as e:
                        published = ''
                if type(displaystr) == list:
                    displaystr = vertical_longtext_split_and_append(convert_special_chars(name),displaystr)
                    displaystr = vertical_longtext_split_and_append(published,displaystr)
                    displaystr = vertical_longtext_split_and_append(convert_special_chars(entry.title),displaystr)
                    displaystr = vertical_longtext_split_and_append(convert_special_chars(entry.summary),displaystr)
                else:
                    displaystr += convert_special_chars(name + ' @ ' + published + ' => ' + entry.title + ': ' + entry.summary)
                if count == max:
                    break
        except Exception as e:
            if errorlog is True: 
                flexprint('==> rss feed error: ', str(e))
                flexprint(traceback.format_exc())

    return displaystr

def convert_special_chars(str):
    return unidecode(str.translate(translate_map)).encode("ascii", errors="ignore").decode()

def set_default_zone():
    global control_id, channels, playmode, shufflemode, repeatmode
    channels = {}
    playmode = {}
    shufflemode = {}
    repeatmode = {}

    if webservers_show == True:
        for idx,data in enumerate(webservers_zones,1):
            name = data['name']
            url = data['url']
            online = is_url_active(url,webserver_head_request_timeout)
            update_webserver_channels(name, online)

    if roon_show == True and roon_servers:
        update_roon_channels()

    if log is True:
        if control_id is None:
            flexprint("actual control zone: -")
        else:
            if channels[control_id]=='webserver':
                flexprint("actual control zone (webserver): " + control_id)
            else:
                flexprint("actual control zone (roon): " + channels[control_id])

def roon_state_callback(event, changed_ids):
    global roon_playouts_raw, roon_playouts, interrupt_message, check_audioinfo, fetch_output_time, prepared_displaystr, prepared_vert_strlines, shuffle_on, shuffle_on_last, repeat_on, repeat_on_last, last_cover_url, is_playing_last, is_playing, last_cover_text_line_parts, playpos_last, playlen_last, data_changed

    if debug is True:
        flexprint('roon_state_callback start => event: ' + str(event) + ', changed_ids: ' + ','.join(changed_ids))

    if initialization_done is True and not (custom_message != '' and custom_message_option == 'exclusive') and fetch_output_in_progress is False and output_in_progress is True and do_set_zone_control is False:
        update_roon_channels() # TODO: should this be enabled here too?
        for zone_id in changed_ids:
            if zone_id not in roonapi.zones:
                flexprint('[red]zone_id ' + zone_id + ' not found in roonapi_zones![/red]')
                continue
            zone = roonapi.zones[zone_id]

            state = "Unknown"
            name = '-'
            artistFiltered = ''
            albumFiltered = ''
            trackFiltered = ''
            shuffle = False

            if zone["state"] is None:
                continue
            else:
                state = zone["state"]
                name = zone["display_name"]
            flexprint('roon_state_callback (' + name + '): ' + state + ', lines: ' + str(zone["now_playing"]["three_line"] if 'now_playing' in zone else '-'))
            if state == "Unknown" or 'now_playing' not in zone:
                continue
            else:
                playstr = zone["now_playing"]["three_line"]
                artist = json.dumps(playstr["line2"],ensure_ascii=False).encode('utf8')
                album = json.dumps(playstr["line3"],ensure_ascii=False).encode('utf8')
                track = json.dumps(playstr["line1"],ensure_ascii=False).encode('utf8')
                playing = state == "playing"
                shuffle = zone["settings"]["shuffle"]
                repeat = zone["settings"]["loop"] != 'disabled'
                set_play_mode(zone_id, playing, False)
                set_shuffle_mode(zone_id, shuffle, False)
                set_repeat_mode(zone_id, repeat, False)

                artistFiltered = filterIllegalChars(artist.decode())
                albumFiltered = filterIllegalChars(album.decode())
                trackFiltered = filterIllegalChars(track.decode())

                cover_url = ''
                image_key = zone["now_playing"].get("image_key")
                if image_key:
                    cover_url = roonapi.get_image(image_key)

                if display_cover is True and control_id is not None and name == channels[control_id]:
                    cover_text_line_parts = []
                    cover_text_line_parts.append(get_message('Zone') + ': ' + name)
                    if artistFiltered != '':
                        cover_text_line_parts.append(get_message('Artist') + ': ' + artistFiltered[1:-1] if (len(artistFiltered) > 1 and artistFiltered[0:1]=='"' and artistFiltered[-1:]=='"') else artistFiltered)
                    if show_album is True and albumFiltered != '':
                        cover_text_line_parts.append(get_message('Album') + ': ' + albumFiltered[1:-1] if (len(albumFiltered) > 1 and albumFiltered[0:1]=='"' and albumFiltered[-1:]=='"') else albumFiltered)
                    if trackFiltered != '':
                        cover_text_line_parts.append(get_message('Track') + ': ' + trackFiltered[1:-1] if (len(trackFiltered) > 1 and trackFiltered[0:1]=='"' and trackFiltered[-1:]=='"') else trackFiltered)

                    playpos = zone.get("seek_position")
                    playlen = zone["now_playing"].get("length")                                   

                    cover_changed = cover_url != last_cover_url
                    text_changed = last_cover_text_line_parts != '|'.join(cover_text_line_parts)
                    
                    is_playing_changed = playing != is_playing_last
                    shuffle_changed = shuffle != shuffle_on_last
                    repeat_changed = repeat != repeat_on_last
                    playpos_changed = playpos_last != playpos
                    playlen_changed = playlen_last != playlen
                    anything_changed = cover_changed or text_changed or is_playing_changed or shuffle_changed or repeat_changed or playlen_changed
                    
                    if (anything_changed is True or (anything_changed is False and playpos_changed is True)):
                        last_cover_url = cover_url
                        last_cover_text_line_parts = '|'.join(cover_text_line_parts)
                        zones = get_zone_names()                                    
                        playpos_last = playpos
                        playlen_last = playlen
                        is_playing_last = is_playing
                        shuffle_on_last = shuffle_on
                        repeat_on_last = repeat_on
                        is_playing = playing
                        shuffle_on = shuffle
                        repeat_on = repeat
                                    
                        flexprint('[bold red]Coverplayer.setpos (roon_state_callback) => playpos: ' + str(playpos) + ', playlen: ' + str(playlen) + ', is_playing: ' + str(is_playing) + ', shuffle: ' + str(shuffle_on) + ', repeat: ' + str(repeat_on) + '[/bold red]')
                        Coverplayer.setpos(playpos, playlen, cover_url, is_playing, shuffle_on, repeat_on, cover_text_line_parts)


            if name not in channels.values():
                playing = '{"status": "not running"}'

                if name not in roon_playouts_raw or roon_playouts_raw[name] != playing:
                    roon_playouts_raw[name] = playing
                    roon_playouts[name] = json.loads(playing)
                    data_changed = True
                continue
            else:
                if cover_url and len(cover_url) > 0:
                    playing = '{"status": "' + str(state) + '", "artist": ' + artistFiltered + ', "album": ' + albumFiltered + ', "track": ' + trackFiltered + ', "shuffle": ' + str(shuffle).lower() + ', "repeat": ' + str(repeat).lower() + ', "cover": "' + cover_url + '"}'
                else:
                    playing = '{"status": "' + str(state) + '", "artist": ' + artistFiltered + ', "album": ' + albumFiltered + ', "track": ' + trackFiltered + ', "shuffle": ' + str(shuffle).lower() + ', "repeat": ' + str(repeat).lower() + '}'
                playing_data_has_changed = name not in roon_playouts_raw or roon_playouts_raw[name] != playing
                if playing_data_has_changed is True:            
                    roon_playouts_raw[name] = playing
                    roon_playouts[name] = json.loads(playing)
                    data_changed = True

                # state variants: loading, playing, paused, stopped, not running
                if state == 'playing':
                    if ((force_active_roon_zone_only is False or name == channels[control_id]) and playing_data_has_changed is True):
                        allowed = output_in_progress is True and fetch_output_time is not None and (fetch_output_time - datetime.now()).total_seconds() > 2
                        if allowed is True:
                            if log is True: flexprint("roon playout detected for zone: %s playing: %s => interrupt message" % (name, playing))
                            interrupt_message = True
                            time.sleep(1)
                            if do_set_zone_control is False:
                                clear_display('roon_state_callback')
                            fetch_output_time = None
                            if vertical_output is False and prepared_displaystr == '':
                                prepared_displaystr = displaystr
                            if vertical_output is True and len(prepared_vert_strlines) == 0:
                                prepared_vert_strlines = vert_strlines
                                prepared_displaystr = str(prepared_vert_strlines) if len(prepared_vert_strlines) > 0 else ''

                            refresh_output_data()
                            check_audioinfo = False

def check_webserver_for_playouts():
    global interrupt_message, fetch_output_time, prepared_displaystr, prepared_vert_strlines

    if initialization_done is True and not (custom_message != '' and custom_message_option == 'exclusive') and fetch_output_in_progress is False and output_in_progress is True and do_set_zone_control is False:
        if vertical_output == True:
            lines = get_playing_apple_or_spotify(webservers_zones,['force>'])
        else:
            displaystr = get_playing_apple_or_spotify(webservers_zones,'force>')
        allowed = output_in_progress is True and fetch_output_time is not None and (fetch_output_time - datetime.now()).total_seconds() > 2

        if allowed is True and not (vertical_output == False and displaystr[:6] == 'force>') and not (vertical_output == True and lines[0] == 'force>'):
            if log is True: flexprint('webserver playout detected => interrupt message')
            interrupt_message = True
            time.sleep(1)
            if do_set_zone_control is False:
                clear_display('check_webserver_for_playouts')
            fetch_output_time = None
            if vertical_output == False and prepared_displaystr == '':
                prepared_displaystr = displaystr
            if vertical_output == True and len(prepared_vert_strlines) == 0:
                prepared_vert_strlines = lines
                prepared_displaystr = str(prepared_vert_strlines) if len(prepared_vert_strlines) > 0 else ''
            refresh_output_data()

    webcheck_timer = Timer(webcheck_update_interval, check_webserver_for_playouts) # check webserver playouts in interval of seconds (webcheck_update_interval)
    webcheck_timer.start()

def force_custom_message():
    global interrupt_message, fetch_output_time, prepared_displaystr, prepared_vert_strlines

    if display_cover is True:
        return

    if initialization_done is True and fetch_output_in_progress is False and output_in_progress is True and (fetch_output_time - datetime.now()).total_seconds() > 2 and do_set_zone_control is False:
        displaystr = convert_special_chars(custom_message)

        if log is True: flexprint('custom message with force option detected => interrupt message')
        interrupt_message = True
        time.sleep(1)
        if do_set_zone_control is False:
            clear_display('interrupt playout for custom message')
        fetch_output_time = None
        if vertical_output == False and prepared_displaystr == '':
            prepared_displaystr = displaystr
        if vertical_output == True and len(prepared_vert_strlines) == 0:
            prepared_vert_strlines = [displaystr]
            prepared_displaystr = str(prepared_vert_strlines) if len(prepared_vert_strlines) > 0 else ''
        refresh_output_data()

def update_roon_channels():
    global control_id, channels, playmode, shufflemode, repeatmode
    #flexprint('update_roon_channels, zones: ' + str(roonapi.zones))
    #outputs = roonapi.outputs
    outputs = roonapi.zones
    if debug is True: flexprint('update_roon_channels start')

    ch_keys = list(channels.keys())
    out_keys = outputs.keys()

    for (k, v) in outputs.items():
        if debug is True: flexprint('check output: ' + v["display_name"])
        if not k in ch_keys:
            if log is True: flexprint('add ' + v["display_name"])
            channels[k] = v["display_name"]
            playmode[k] = 'stop'
            shufflemode[k] = 'noshuffle'
            repeatmode[k] = 'norepeat'

    for key in ch_keys:
        if not key in out_keys and not channels[key]=='webserver':
            if log is True: flexprint('del key: ' + key + ', name: ' + channels[key])
            del channels[key]
            del playmode[key]
            del repeatmode[key]
            if (control_id==key):
                control_id = None

    get_new_control_id_by_roon_control_zone()
    get_new_control_id_by_webserver_control_zone()
    get_new_control_id_by_roon_zone_playing()
    get_new_control_id_by_webserver_zone_online()
    get_new_control_id_by_roon_zone_online()
    if debug is True: flexprint('update_roon_channels end')

def update_webserver_channels(name, online):
    global control_id, channels, playmode, shufflemode, repeatmode

    if debug is True:
        flexprint('update_webserver_channels => start, control_id: ' + str(control_id) + ', name: ' + (channels[control_id] if control_id in channels else ''))
        flexprint(name + ' online:' + str(online))
    keys = list(channels.keys())
    players = ['Spotify', 'Apple Music']

    for player in players:
        key = name + '-' + player
        if debug is True: flexprint('check player: ' + key)
        if online is True:
            if not key in keys:
                if debug is True: flexprint('add player ' + key)
                channels[key] = 'webserver'
                playmode[key] = 'stop'
                shufflemode[key] = 'noshuffle'
                repeatmode[key] = 'norepeat'
        else:
            if key in keys:
                if debug is True: flexprint('del key: ' + key)
                del channels[key]
                del playmode[key]
                del shufflemode[key]
                del repeatmode[key]
                if (control_id==key):
                    control_id = None

    get_new_control_id_by_webserver_control_zone()
    get_new_control_id_by_roon_control_zone()
    get_new_control_id_by_roon_zone_playing()
    get_new_control_id_by_webserver_zone_online()
    get_new_control_id_by_roon_zone_online()

    if debug is True: flexprint('update_webserver_channels => end, control_id: ' + str(control_id) + ', name: ' + (channels[control_id] if control_id in channels else ''))

def get_new_control_id_by_webserver_control_zone():
    global control_id, control_zone

    if control_zone is not None and webservers_show == True and control_zone in channels.keys() and channels[control_zone]=='webserver':
        control_id = control_zone
        if log is True: flexprint('[bold magenta]set control_id to webserver control-zone: ' + str(control_zone) + '[/bold magenta]')
        control_zone = None

def get_new_control_id_by_webserver_zone_online():
    global control_id

    if control_id is None and webservers_show == True:
        keys = list(channels.keys())
        keys_len = len(keys)
        if keys_len > 0:
            for key in keys:
                if channels[key]=='webserver':
                    control_id = key
                    if log is True: flexprint('[bold magenta]set control_id to online webserver player zone: ' + key + '[/bold magenta]')
                    break

def get_new_control_id_by_roon_control_zone():
    global control_id, control_zone

    if control_zone is not None and roon_show == True:
        keys = list(channels.keys())
        keys_len = len(keys)
        if keys_len > 0:
            for key in keys:
                if not channels[key]=='webserver' and channels[key]==control_zone:
                    control_id = key
                    if log is True: flexprint('[bold magenta]set control_id to roon control-zone: ' + str(control_zone) + '[/bold magenta]')
                    control_zone = None
                    break

def get_new_control_id_by_roon_zone_playing():
    global control_id

    if control_id is None and roon_show == True and len(roon_servers) > 0:
        names = list(channels.values())
        for zone in list(roonapi.zones.values()):
            state = "Unknown"
            if zone["state"] is not None:
                state = zone["state"]
            if state == "playing" and zone["display_name"] in names:
                if log is True: flexprint('zone: ' + str(zone))
                for id, name in channels.items():
                    if name == zone["display_name"]:
                        control_id = id
                        if log is True: flexprint('[bold magenta]set control_id to roon playing zone: ' + name + '[/bold magenta]')
                        return

def get_zone_names():
    global roon_zones

    if (len(roon_zones) == 0 and roonapi != None):
        roon_zones = list(roonapi.zones.values())
    zone_id_list = []
    for zone in roon_zones:
        if zone["state"] is not None and zone["state"] != "Unknown" and 'now_playing' in zone:
            zone_id_list.append(zone['zone_id'])

    zones = []
    for id, name in channels.items():
        if name == 'webserver':
            zones.append(id)
        elif id in zone_id_list:
            zones.append(name)
    zones.sort()
    return zones

def get_new_control_id_by_roon_zone_online():
    global control_id

    if control_id is None and roon_show == True:
        keys = list(channels.keys())
        keys_len = len(keys)
        if keys_len > 0:
            for key in keys:
                if not channels[key]=='webserver':
                    control_id = key
                    if log is True: flexprint('[bold magenta]set control_id to roon online zone: ' + channels[key] + '[/bold magenta]')
                    break

def get_zone_control_shortname(str):
    conv_str = str
    if map_zone_control == True:
        for key, val in zone_control_map.items():
            conv_str = conv_str.replace(key, val)

    return convert_special_chars(conv_str)

def get_ram_info():
    if debug is True:
        ram = psutil.virtual_memory()
        flexprint('Total RAM: ' + str(ram))

def remove_completed_threads():
    global jobs

    if display_cover is False and do_set_zone_control is False:
        try:
            for job in as_completed(jobs):
                if log is True: flexprint('delete job ' + str(jobs[job]))
                del jobs[job]
                if debug is True:
                    get_ram_info()
        except Exception as e:
            if errorlog is True: flexprint('[red]==> remove complete threads error: [/red]', str(e))

def tick():
    global n

    if debug is True:
        flexprint('tick ' + datetime.now().strftime("%H:%M:%S") + ', vars: (cInp:' + str (clock_in_progress) + '|fOinP:' + str(fetch_output_in_progress) + '|fODone:' + str(fetch_output_done) + '|oinP:' + str(output_in_progress) + '|prDispEmpty:' + str(prepared_displaystr=='') + ')')
    n.notify("WATCHDOG=1")

def filterIllegalChars(str):
    filtered = str.replace("\\\"","”") # RIGHT DOUBLE QUOTATION MARK
    return filtered

def build_output():
    global prepared_displaystr, prepared_vert_strlines, audio_playing, last_idle_time, roon_servers, roonapi, build_seconds, fetch_output_done, roon_playouts_raw, roon_playouts, last_cover_url, last_cover_text_line_parts, is_playing, is_playing_last, shuffle_on, shuffle_on_last, repeat_on, repeat_on_last, last_zones, playpos_last, playlen_last, data_changed, app_displaystr, roon_zones
    # global fetch_output_time

    buildstr = ''
    buildlines = []

    build_start = datetime.now()
    fetch_output_done = False
    fetch_output_time = build_start + timedelta(0,3600) # set fetch_output_time 1h into the future to prevent build_output call again and again before output is called
    if log is True:
        flexprint(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ' => build output start')
        flexprint('')

    try:
        if roon_show == True:
            roon_active = is_roon_server_active(core_ip, core_port) if (core_ip != '' and core_port != '') else False
            if core_ip == '' or core_port == '':
                roon_discover()
            if roonapi is None:
                get_roon_api()
            roon_active = is_roon_server_active(core_ip, core_port) if (core_ip != '' and core_port != '') else False
            roon_discover_first_test()

            flexprint('roon_active: ' + str(roon_active) + ', core_ip: ' + str(core_ip) + ', core_port: ' + str(core_port) + ', roonapi: ' + str(roonapi is not None))
            if roon_active is True and core_ip != '' and core_port != '' and roonapi is not None:
                update_roon_channels()
                roon_zones = list(roonapi.zones.values())
                for zone in roon_zones:
                    state = "Unknown"
                    artistFiltered = ''
                    albumFiltered = ''
                    trackFiltered = ''
                    shuffle = False
                    
                    if zone["state"] is not None:
                        state = zone["state"] # state variants: loading, playing, paused, stopped, not running
                    flexprint('### roon state (' + zone["display_name"] + '): ' + state + ', lines: ' + str(zone["now_playing"]["three_line"] if 'now_playing' in zone else 'None'))
                    if state == "Unknown" or 'now_playing' not in zone:
                        continue
                    else:
                        playstr = zone["now_playing"]["three_line"]
                        artist = json.dumps(playstr["line2"],ensure_ascii=False).encode('utf8')
                        album = json.dumps(playstr["line3"],ensure_ascii=False).encode('utf8')
                        track = json.dumps(playstr["line1"],ensure_ascii=False).encode('utf8')
                        playing = state == "playing"
                        shuffle = zone["settings"]["shuffle"]
                        repeat = zone["settings"]["loop"] != 'disabled'
                        zone_id = zone['zone_id']
                        set_play_mode(zone_id, state == "playing", False)
                        set_shuffle_mode(zone_id, shuffle, False)
                        set_repeat_mode(zone_id, repeat, False)

                        artistFiltered = filterIllegalChars(artist.decode())
                        albumFiltered = filterIllegalChars(album.decode())
                        trackFiltered = filterIllegalChars(track.decode())

                        cover_url = ''
                        image_key = zone["now_playing"].get("image_key")
                        if image_key:
                            cover_url = roonapi.get_image(image_key)

                        if display_cover is True:
                            zones = get_zone_names()
                            if last_zones != zones:
                                last_zones = zones
                                flexprint('[bold red]Coverplayer.setZones (roon build_output) => zones: ' + str(zones) + '[/bold red]')
                                Coverplayer.setZones(zones)

                            if control_id is not None and zone["display_name"] == channels[control_id]:
                                cover_text_line_parts = []
                                cover_text_line_parts.append(get_message('Zone') + ': ' + zone["display_name"])
                                if artistFiltered != '':
                                    cover_text_line_parts.append(get_message('Artist') + ': ' + artistFiltered[1:-1] if (len(artistFiltered) > 1 and artistFiltered[0:1]=='"' and artistFiltered[-1:]=='"') else artistFiltered)
                                if show_album is True and albumFiltered != '':
                                    cover_text_line_parts.append(get_message('Album') + ': ' + albumFiltered[1:-1] if (len(albumFiltered) > 1 and albumFiltered[0:1]=='"' and albumFiltered[-1:]=='"') else albumFiltered)
                                if trackFiltered != '':
                                    cover_text_line_parts.append(get_message('Track') + ': ' + trackFiltered[1:-1] if (len(trackFiltered) > 1 and trackFiltered[0:1]=='"' and trackFiltered[-1:]=='"') else trackFiltered)

                                if (cover_url != last_cover_url or last_cover_text_line_parts != '|'.join(cover_text_line_parts) or playing != is_playing_last or shuffle != shuffle_on_last or repeat != repeat_on_last):
                                    last_cover_url = cover_url
                                    last_cover_text_line_parts = '|'.join(cover_text_line_parts)
                                    playpos = zone.get("seek_position")
                                    playlen = zone["now_playing"].get("length")                                   
                                    playpos_last = playpos
                                    playlen_last = playlen
                                    is_playing_last = is_playing
                                    shuffle_on_last = shuffle_on
                                    repeat_on_last = repeat_on
                                    is_playing = playing
                                    shuffle_on = shuffle
                                    repeat_on = repeat
                                    
                                    flexprint('[bold red]Coverplayer.update (roon build_output) => playpos: ' + str(playpos) + ', playlen: ' + str(playlen) + ', is_playing: ' + str(is_playing) + ', shuffle: ' + str(shuffle_on) + ', repeat: ' + str(repeat_on) + '[/bold red]')
                                    Coverplayer.update(playpos, playlen, cover_url, is_playing, shuffle_on, repeat_on, cover_text_line_parts, zones, zone_selection, on_control_click, on_search, on_itemclick)

                    if zone["display_name"] not in channels.values():
                        playing = '{"status": "not running"}'

                        if zone["display_name"] not in roon_playouts_raw or roon_playouts_raw[zone["display_name"]] != playing:
                            roon_playouts_raw[zone["display_name"]] = playing
                            roon_playouts[zone["display_name"]] = json.loads(playing)
                            data_changed = True
                        continue
                    else:
                        if log is True: flexprint('actual control_id: ' + str(control_id) + ', control_zone: ' + str(control_zone))
                        if control_id is not None and zone["display_name"] == channels[control_id]:
                            zone_name = '[*] '
                        else:
                            zone_name = ''
                        zone_name += zone["display_name"]

                        if cover_url and len(cover_url) > 0:
                            playing = '{"status": "' + str(state) + '", "artist": ' + artistFiltered + ', "album": ' + albumFiltered + ', "track": ' + trackFiltered + ', "shuffle": ' + str(shuffle).lower() + ', "repeat": ' + str(repeat).lower() + ', "cover": "' + cover_url + '"}'
                        else:
                            playing = '{"status": "' + str(state) + '", "artist": ' + artistFiltered + ', "album": ' + albumFiltered + ', "track": ' + trackFiltered + ', "shuffle": ' + str(shuffle).lower() + ', "repeat": ' + str(repeat).lower() + '}'
                        flexprint('### playing: ' + str(playing))

                        playing_data_has_changed = zone["display_name"] not in roon_playouts_raw or roon_playouts_raw[zone["display_name"]] != playing
                        if playing_data_has_changed:
                            roon_playouts_raw[zone["display_name"]] = playing
                            roon_playouts[zone["display_name"]] = json.loads(playing)
                            data_changed = True

                        if state == "playing":
                            roonstr = ''
                            if playing_headline !='':
                                roonstr = playing_headline + ': '

                            if show_zone is True:
                                roonstr += get_message('Zone') + ': ' + zone_name + ' => '

                            if show_album is True and albumFiltered != '':
                                roonstr += get_message('Artist') + ': {} / ' + get_message('Album') + ': {} / ' + get_message('Track') + ': {}'
                                tup = (artistFiltered,albumFiltered,trackFiltered,state)
                            else:
                                roonstr += get_message('Artist') + ': {} / ' + get_message('Track') + ': {}'
                                tup = (artist.decode(),trackFiltered,state)

                            if buildstr != '':
                                buildstr += separator
                            buildstr += convert_special_chars(roonstr.format(*tup))
                            flexprint('### buildstr: ' + buildstr)

                        if state == "playing" and vertical_output == True:
                            if len(buildlines) > 0:
                                buildlines.append('')
                            if len(buildlines) == 0 and playing_headline !='':
                                buildlines = vertical_longtext_split_and_append(convert_special_chars(playing_headline),buildlines)
                            if show_zone is True:
                                zonestr = get_message('Zone') + ': ' + convert_special_chars(zone_name)
                                font = proportional(CP437_FONT)
                                w, h = textsize(zonestr, font)
                                if w > device.width:
                                    buildlines.append(get_message('Zone'))
                                    buildlines = vertical_longtext_split_and_append(convert_special_chars(zone_name),buildlines)
                                else:
                                    buildlines = vertical_longtext_split_and_append(zonestr,buildlines)
                            if artistFiltered != '':
                                if show_vertical_music_label is True:
                                    buildlines.append('< ' + get_message('Artist') + ' >')
                                buildlines = vertical_longtext_split_and_append(convert_special_chars(artistFiltered).replace('"',''),buildlines)
                            if show_album is True and albumFiltered != '':
                                if show_vertical_music_label is True:
                                    buildlines.append('< ' + get_message('Album') + ' >')
                                buildlines = vertical_longtext_split_and_append(convert_special_chars(albumFiltered).replace('"',''),buildlines)
                            if show_vertical_music_label is True:
                                buildlines.append('< ' + get_message('Track') + ' >')
                                buildlines = vertical_longtext_split_and_append(convert_special_chars(trackFiltered).replace('"',''),buildlines)
                            else:
                                buildlines = vertical_longtext_split_and_append('=> ' + convert_special_chars(trackFiltered).replace('"',''),buildlines)

        if webservers_show == True:
            if vertical_output == True:
                buildlines = get_playing_apple_or_spotify(webservers_zones,buildlines)
            else:
                buildstr = get_playing_apple_or_spotify(webservers_zones,buildstr)
            flexprint('### buildstr after webserver: ' + buildstr)

        if buildstr != '' or len(buildlines) > 0:
            last_idle_time = None
        else:
            if last_idle_time is None:
                last_idle_time = datetime.now()

        if vertical_output == True and len(buildlines) == 0:
            audio_playing = ''
        else:
            audio_playing = str(buildlines) if vertical_output == True else buildstr

        show_nonaudio_content = (exclusive_audio_mode is False and music_required is False) or (exclusive_audio_mode is True and buildstr == '' and len(buildlines) == 0) or (music_required is True and (buildstr != '' or len(buildlines) > 0))

        if show_nonaudio_content == True and custom_message != '' and custom_message_option != 'exclusive':
            if buildstr != '':
                buildstr += separator
            buildstr += convert_special_chars(custom_message)
            if len(buildlines) > 0:
                buildlines.append('')
            buildlines = vertical_longtext_split_and_append('> ' + convert_special_chars(custom_message),buildlines)

        if show_nonaudio_content == True and weather_show == True and ((vertical_output is False and weatherstr != '') or (vertical_output is True and len(weatherlines) > 0)):
            if buildstr != '':
                buildstr += separator
            buildstr += weatherstr
            if len(buildlines) > 0:
                buildlines.append('')
            buildlines += weatherlines

        if show_nonaudio_content == True and rss_show == True:
            if vertical_output == True:
                buildlines = get_rss_feed(buildlines)
            else:
                buildstr = get_rss_feed(buildstr)

        if show_nonaudio_content == True and datetime_show == True:
            if buildstr != '':
                buildstr += separator
            if len(buildlines) > 0:
                buildlines.append('')

            if datetime_only_time is True:
                dtmessage = get_message('time') + ': ' + datetime.now().strftime("%H:%M:%S")
            else:
                dtmessage = get_message('date') + ': ' + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            buildstr += dtmessage
            buildlines = vertical_longtext_split_and_append(dtmessage,buildlines)

        if custom_message != '' and custom_message_option == 'exclusive':
            buildstr = separator + convert_special_chars(custom_message)
            buildlines = vertical_longtext_split_and_append('> ' + convert_special_chars(custom_message),[])
        flexprint('### buildstr end: ' + buildstr)

    except Exception as e:
        if errorlog is True: 
            flexprint('[red]==> build output error: [/red]', str(e))
            flexprint(traceback.format_exc())

    build_seconds = ceil((datetime.now() - build_start).total_seconds())
    if log is True:
        flexprint(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ' => build output end [time: ' + str(build_seconds) + ' sec]')
        flexprint('')

    if vertical_output == True and len(buildlines) == 0:
        prepared_displaystr = ''
    else:
        to_update = str(buildlines) if vertical_output == True else buildstr
        prepared_displaystr = to_update
        flexprint('### buildstr update: ' + str(app_displaystr != to_update))
        if app_displaystr != to_update:
            app_displaystr = to_update
            data_changed = True
    prepared_vert_strlines = buildlines
    fetch_output_done = True

# --- button setup ---
# button left: play track before
# button right: play next track
# button center: toggle between play and pause
# button down: toggle between random and sequential play
#
# button top: enter or leave zone control mode (select a zone to control with the buttons)
# in zone control mode:
#     button left: switch to zone before the actual control zone
#     button right: switch to zone after the actual control zone (in list of available zones)
#     button down: leave zone control mode without switching to new selected zone (no saving of control_id)
#     button enter: leave zone control mode and switch to new selected zone (save control_id)
#     button top: leave zone control mode and switch to new selected zone (save control_id)

if display_cover is False:
    GPIO.setmode (GPIO.BCM)
    GPIO.setup (controlswitch_gpio_top, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup (controlswitch_gpio_down, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup (controlswitch_gpio_left, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup (controlswitch_gpio_center, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup (controlswitch_gpio_right, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    GPIO.add_event_detect(controlswitch_gpio_top, GPIO.FALLING, callback=pressed_up, bouncetime=controlswitch_bouncetime)
    GPIO.add_event_detect(controlswitch_gpio_down, GPIO.FALLING, callback=pressed_down, bouncetime=controlswitch_bouncetime)
    GPIO.add_event_detect(controlswitch_gpio_left, GPIO.FALLING, callback=pressed_left, bouncetime=controlswitch_bouncetime)
    GPIO.add_event_detect(controlswitch_gpio_center, GPIO.FALLING, callback=pressed_enter, bouncetime=controlswitch_bouncetime)
    GPIO.add_event_detect(controlswitch_gpio_right, GPIO.FALLING, callback=pressed_right, bouncetime=controlswitch_bouncetime)

# --- MAIN ---
if display_cover is False:
    device = init_matrix()

while True:
    if is_url_active(internet_connection_url,internet_connection_timeout) is True:
        # Do somthing
        if log is True: flexprint("The internet connection is active")
        break
    else:
        if log is True: flexprint("The internet connection is down")
        pass

parser = argparse.ArgumentParser()
parser.add_argument("-z", "--zone", help="zone selection")
parser.add_argument("-a", "--all", default=False, action='store_true',
                    help="display all zones regardless of state")

appKey = 'coverplayer' if display_cover is True else 'roonmatrix'
appinfo = {
  "extension_id": appKey + '_' + hostName,
  "display_name": appKey + ' [' + hostName + ']',
  "display_version": scriptVersion,
  "publisher": "Stephan Wilhelm",
  "email": "support@wilhelm-devblog.de",
  "website": "https://github.com/eventcatcher/roonmatrix"
}

if roon_show == True:
    if core_ip == '' or core_port == '':
        roon_discover()
    if roonapi is None:
        get_roon_api()

if weather_show == True:
    get_weather(weather_api,location)

if force_webserver_update is True:
    check_webserver_for_playouts()

set_default_zone()
clear_display('initialization done')
initialization_done = True
if log is True:
    flexprint('main initialization done')
    flexprint('')

try:
    with ThreadPoolExecutor(max_workers=4) as executor:
        job = executor.submit(start_restserver)

        while True:
            if reboot is True:
                job = executor.submit(do_reboot)
            if do_set_zone_control is True:
                # quit zone control mode after timeout
                if (datetime.now() - zone_control_last_update_time).total_seconds() > zone_control_timeout:
                    if log is True: flexprint('zone control timeout')
                    clear_display('zone control timeout')
                    do_set_zone_control = False
                    refresh_output_data()
                    if log is True: flexprint('zone control timeout end')

            if clock_in_progress == False and fetch_output_in_progress == False and (fetch_output_time is None or datetime.now() > fetch_output_time):
                # build output string at fetch_output_time
                fetch_output_in_progress = True
                job = executor.submit(build_output)
                remove_completed_threads()
                jobcount += 1
                jobs[job] = jobcount

            if clock_in_progress == False and fetch_output_in_progress is True and fetch_output_done is True and output_in_progress == False and prepared_displaystr != '':
                # output string to display
                fetch_output_done = False
                output_in_progress = True
                playcount += 1
                displaystr = prepared_displaystr
                vert_strlines = prepared_vert_strlines
                prepared_displaystr = ''
                prepared_vert_strlines = []
                delaySec = led_scroll_delay/1000
                if vertical_output == True:
                    fetch_output_time = get_next_fetch_output_time(vert_strlines, font=proportional(CP437_FONT), scroll_delay=delaySec)
                else:
                    fetch_output_time = get_next_fetch_output_time(displaystr, font=proportional(CP437_FONT), scroll_delay=delaySec)
                if log is True: flexprint(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ' => playout round ' + str(playcount) + ', estimated output fetch time: ' + fetch_output_time.strftime("%H:%M:%S"))
                fetch_output_in_progress = False
                remove_completed_threads()
                job = executor.submit(output)
                jobcount += 1
                jobs[job] = jobcount

            if clock_in_progress is False and fetch_output_in_progress is True and fetch_output_done is True and output_in_progress == False and prepared_displaystr == '' and len(prepared_vert_strlines) == 0:
                # if nothing to play and output string is empty (music_required is True), set fetch_output_time 15sec into the future to check again for output contents
                fetch_output_done = False
                displaystr = ''
                vert_strlines = []
                fetch_output_time = datetime.now() + timedelta(0,15)
                if log is True: flexprint(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ' => nothing to play, estimated output fetch time: ' + fetch_output_time.strftime("%H:%M:%S"))
                fetch_output_in_progress = False

            above_maxtime = last_idle_time is not None and ((datetime.now() - last_idle_time).total_seconds() / 60.0) > clock_max_idle_time
            if music_required is True and clock_without_idle_time is False and above_maxtime is True and displaystr == '' and prepared_displaystr == '' and len(prepared_vert_strlines) == 0 and fetch_output_in_progress == True and fetch_output_done is True:
                fetch_output_in_progress = False
            fill_idle_playout_with_clock = music_required is True and (clock_without_idle_time is True or above_maxtime is True) and prepared_displaystr == '' and len(prepared_vert_strlines) == 0 and fetch_output_in_progress == False and output_in_progress is False and audioinfo_available is False
            if clock_in_progress == True or (clock_show == True and do_set_zone_control is False and check_audioinfo == False and (fill_idle_playout_with_clock is True or above_maxtime is True)):
                # show clock
                clock_in_progress = True
                if (music_required is False or fetch_output_in_progress == False) and output_in_progress == False:
                    if log is True: flexprint('clock mode start')
                    check_audioinfo = True
                    prepared_displaystr = ''
                    prepared_vert_strlines = []
                    remove_completed_threads()
                    set_fetch_time_before_clock_ends()
                    job = executor.submit(show_clock)
                    jobcount += 1
                    jobs[job] = jobcount
                    sleepcount = 0
                    while check_audioinfo is True and audioinfo_available is False and do_set_zone_control is False:
                        if fetch_output_in_progress == False and (fetch_output_time is None or datetime.now() > fetch_output_time):
                            fetch_output_in_progress = True
                            job = executor.submit(build_output)
                            jobcount += 1
                            jobs[job] = jobcount
                        if sleepcount % audioinfo_timer == 0:
                            job = executor.submit(is_audioinfo_available)
                            jobcount += 1
                            jobs[job] = jobcount
                        time.sleep(1)
                        sleepcount += 1
                        tick()
                    clock_in_progress = False
                    remove_completed_threads()
                    if log is True: flexprint('clock mode end')
            time.sleep(1)
            tick()
except Exception as e:
    if errorlog is True: 
        flexprint('[red]==> MAIN ERROR: [/red]', str(e))
        flexprint(traceback.format_exc())

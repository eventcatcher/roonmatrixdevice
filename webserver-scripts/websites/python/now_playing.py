#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__  = 'Stephan Wilhelm @2024, based on script from Marcos Vinicius Rodrigues / https://mvrpl.com.br'
__doc__     = '''
This Script get track information of music now playing in Apple Music or Spotify App, 
works on macos with python 3.8, and writes the result into response output

access to webserver: http://www.roonmatrix.test/now_playing.php (local network via vhost hostname), 
or: http://IP-ADDRESS/roonmatrix/now_playing.php (local network via ip address)
or: http://NETWORKNAME.local/roonmatrix/now_playing.php (local network via bonjour network)
'''

import applescript # pip install of this package: https://pypi.python.org/packages/source/p/py-applescript/py-applescript-1.0.0.tar.gz
import json
import os
from os.path import expanduser
import hashlib

userHomePath = expanduser("~") # /Users/USERNAME
phpScriptPath = os.getcwd().replace(userHomePath,'') # /Users/USERNAME/websites/roonmatrix
userHomeDirSubfolderPathToCoversPHP = phpScriptPath.replace(userHomePath,'') + '/covers/'
userHomeDirSubfolderPathToCoversAppleScript = userHomeDirSubfolderPathToCoversPHP[1:-1].replace('/',':')

tell_iTunes = applescript.AppleScript('''
on is_running(appName)
    tell application "System Events" to (name of processes) contains appName
end is_running

on Playing()
    set resultArray to {}
    set iTunesRunning to is_running("Music")
    set SpotifyRunning to is_running("Spotify")

    if iTunesRunning then
        tell application "Music"
            try
                set songArtist to the artist of the current track
                set songAlbum to the album of the current track
                set songTitle to the name of the current track

                set hasCover to true
                try 
                    tell artwork 1 of current track
                        set srcBytes to raw data
                        if format is «class PNG » then
                            set ext to ".png"
                        else
                            set ext to ".jpg"
                        end if
                    end tell
                on error errMsg
                    set hasCover to false
                end try

                set home_path to (path to home folder)
                set subfolder to "''' + userHomeDirSubfolderPathToCoversAppleScript + '''"
                set fileName to ":coverAppleMusic" & ext
                set filePathWithName to ((home_path & subfolder as text) & fileName)

                set pos_double to the player position
                set total_double to the duration of the current track
                set pos to round pos_double rounding down
                set total to round total_double rounding down

                set outFile to open for access file filePathWithName with write permission
                set eof outFile to 0
                write srcBytes to outFile
                close access outFile                
                
                if hasCover then
                    set result to "Apple Music%-%" & player state & "%-%" & songArtist & "%-%" & songAlbum & "%-%" & songTitle & "%-%" & shuffle enabled & "%-%" & song repeat & "%-%" & pos & "%-%" & total & "%-%" & fileName
                else
                    set result to "Apple Music%-%" & player state & "%-%" & songAlbum & "%-%" & songArtist & "%-%" & songTitle & "%-%" & shuffle enabled & "%-%" & song repeat & "%-%" & pos & "%-%" & total
                end if
            on error m number n
            end try
            copy result to the end of the resultArray
        end tell
    else
        copy "Apple Music%-%" & "status::not running" to the end of the resultArray
    end if

    if SpotifyRunning then
        tell application "Spotify"
            tell current track
                set songArtist to the artist
                set songAlbum to the album
                set songTitle to the name
                set hasCover to true
                try 
                    set coverUrl to artwork url
                on error errMsg
                    set hasCover to false
                end try
            end tell

            set currentPosition to player position
            set pos to round currentPosition rounding down
            set total to round ((duration of current track) / 1000) rounding down
            
            if hasCover then
                set result to "Spotify%-%" & player state & "%-%" & songArtist & "%-%" & songAlbum & "%-%" & songTitle & "%-%" & shuffling & "%-%" & repeating & "%-%" & pos & "%-%" & total & "%-%" & coverUrl
            else
                set result to "Spotify%-%" & player state & "%-%" & songArtist & "%-%" & songAlbum & "%-%" & songTitle & "%-%" & shuffling & "%-%" & repeating & "%-%" & pos & "%-%" & total
            end if
                
            copy result to the end of the resultArray
        end tell
    else
        copy "Spotify%-%" & "status::not running" to the end of the resultArray
    end if

    return resultArray

end Playing
''')

userHomeDir = os.path.expanduser("~")
DIR = userHomeDir + userHomeDirSubfolderPathToCoversPHP
maxCoverFiles = 50
coverfiles = [f for f in os.listdir(DIR) if f.startswith('coverAppleMusic_')]
coverfiles.sort(key=lambda x: os.stat(os.path.join(DIR, x)).st_mtime, reverse=True)
if (len(coverfiles) > maxCoverFiles):
    for filename in coverfiles[maxCoverFiles:]:
        os.remove(os.path.join(DIR, filename))	# remove covers but not a number of newest ones (maxCoverFiles)

return_str = ''
output_list = []
output = tell_iTunes.call('Playing')

for line in output:
    output = line.split('%-%')
    zone_name = output[0]
    status = output[1].encode('utf8')
    cover = ''
    if status.decode().startswith('status::'):
        roonstr = '"zone": "{}", "status": "{}"'
        tup = (zone_name,status.decode()[8:])
    else:   
        artist = output[2].encode('utf8')
        album = output[3].encode('utf8')
        track = output[4].encode('utf8')
        shuffle = output[5].encode('utf8')
        repeat = output[6].encode('utf8')
        position = output[7].encode('utf8')
        total = output[8].encode('utf8')
        if len(output) > 9:
            if zone_name.startswith('Spotify'):
                if output[9].startswith('http') is False:
                    cover = ''
                else:
                    cover = output[9].encode('utf8')
            else:
                filename = output[9].replace(':','')
                if os.path.exists(DIR + filename):
                    fnparts = filename.rsplit('.',1)
                    stringToHash = artist.decode() + '-' + album.decode() + '-' + track.decode()
                    hash = hashlib.md5(stringToHash.encode('utf8'))
                    newFilename = fnparts[0] + '_' + hash.hexdigest() + '.' + fnparts[1]
                    if os.path.exists(DIR + newFilename) is False:
                        os.rename(DIR + filename, DIR + newFilename)
                    cover = ('covers/' + newFilename).encode('utf8')

        if cover!='':
            roonstr = '"zone": "{}", "status": "{}", "artist": "{}", "album": "{}", "track": "{}", "shuffle": "{}", "repeat": "{}", "position": "{}", "total": "{}", "cover": "{}"'
            tup = (zone_name,status.decode(),artist.decode(),album.decode(),track.decode(),shuffle.decode(),repeat.decode(),position.decode(),total.decode(),cover.decode())
        else:
            roonstr = '"zone": "{}", "status": "{}", "artist": "{}", "album": "{}", "track": "{}", "shuffle": "{}", "repeat": "{}", "position": "{}", "total": "{}"'
            tup = (zone_name,status.decode(),artist.decode(),album.decode(),track.decode(),shuffle.decode(),repeat.decode(),position.decode(),total.decode())
        
    output_list.append('{' + roonstr.format(*tup) + '}')
return_str = ','.join(output_list)
print('[' + return_str + ']')

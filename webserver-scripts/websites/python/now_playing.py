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

                set outFile to open for access file filePathWithName with write permission
                set eof outFile to 0
                write srcBytes to outFile
                close access outFile                
                
                if hasCover then
                    set result to "Apple Music%-%" & songArtist & "%-%" & songAlbum & "%-%" & songTitle & "%-%" & fileName
                else
                    set result to "Apple Music%-%" & songArtist & "%-%" & songAlbum & "%-%" & songTitle
                end if
            on error m number n
            end try
            if player state is playing then
                copy result to the end of the resultArray
            else
                copy "Apple Music%-%" & "status::idle" to the end of the resultArray
            end if
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
            
            if hasCover then
                set result to "Spotify%-%" & songArtist & "%-%" & songAlbum & "%-%" & songTitle & "%-%" & coverUrl
            else
                set result to "Spotify%-%" & songArtist & "%-%" & songAlbum & "%-%" & songTitle
            end if
                
            if player state is playing then
                copy result to the end of the resultArray
            else
                copy "Spotify%-%" & "status::idle" to the end of the resultArray
            end if
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
    cover = ''
    artist = output[1].encode('utf8')
    if artist.decode().startswith('status::'):
        roonstr = '"zone": "{}", "status": "{}"'
        tup = (zone_name,artist.decode()[8:])
    else:   
        album = output[2].encode('utf8')
        track = output[3].encode('utf8')
        if len(output)>4:
            if zone_name.startswith('Spotify'):
                if output[4].startswith('http') is False:
                    cover = ''
                else:
                    cover = output[4].encode('utf8')
            else:
                filename = output[4].replace(':','')
                if os.path.exists(DIR + filename):
                    fnparts = filename.rsplit('.',1)
                    stringToHash = artist.decode() + '-' + album.decode() + '-' + track.decode()
                    hash = hashlib.md5(stringToHash.encode('utf8'))
                    newFilename = fnparts[0] + '_' + hash.hexdigest() + '.' + fnparts[1]
                    if os.path.exists(DIR + newFilename) is False:
                        os.rename(DIR + filename, DIR + newFilename)
                    cover = newFilename.encode('utf8')

        if cover!='':
            roonstr = '"zone": "{}", "artist": "{}", "album": "{}", "track": "{}", "cover": "{}"'
            tup = (zone_name,artist.decode(),album.decode(),track.decode(),cover.decode())
        else:
            roonstr = '"zone": "{}", "artist": "{}", "album": "{}", "track": "{}"'
            tup = (zone_name,artist.decode(),album.decode(),track.decode())
        
    output_list.append('{' + roonstr.format(*tup) + '}')
return_str = ','.join(output_list)
print('[' + return_str + ']')

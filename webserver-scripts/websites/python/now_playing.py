#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ 	= 'Stephan Wilhelm @2024, based on script from Marcos Vinicius Rodrigues / https://mvrpl.com.br'
__doc__		= '''
This Script get track information of music now playing in Apple Music or Spotify App, 
works on macos with python 3.8, and writes the result into php file
write file to: /Users/USERNAME/websites/spielwiese/now_playing.txt

access on webserver: http://www.roonmatrix.test/now_playing.php (local), 
or: http://IP-ADDRESS/roonmatrix/now_playing.php (network)
or: http://NETWORKNAME.local/roonmatrix/now_playing.php (bonjour network)
'''
# pip install pyobjc
import applescript # pip install https://pypi.python.org/packages/source/p/py-applescript/py-applescript-1.0.0.tar.gz
import json

#filepath = '/Users/swilhelm/websites/spielwiese/now_playing.txt'

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
				set songTitle to the name of the current track
				set songArtist to the artist of the current track
				set songAlbum to the album of the current track
				set result to "Apple Music%-%" & songArtist & "%-%" & songTitle & "%-%" & songAlbum
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
			set songTitle to the name of the current track
			set songArtist to the artist of the current track
			set songAlbum to the album of the current track
			set result to "Spotify%-%" & songArtist & "%-%" & songTitle & "%-%" & songAlbum
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

return_str = ''
output_list = []
output = tell_iTunes.call('Playing')

for line in output:
	output = line.split('%-%')
	zone_name = output[0]
	artist = output[1].encode('utf8')
	if artist.decode().startswith('status::'):
	    roonstr = '"zone": "{}", "status": "{}"'
	    tup = (zone_name,artist.decode()[8:])
	else:	
	    track = output[2].encode('utf8')
	    album = output[3].encode('utf8')
	    roonstr = '"zone": "{}", "artist": "{}", "album": "{}", "track": "{}"'
	    tup = (zone_name,artist.decode(),album.decode(),track.decode())
	output_list.append('{' + roonstr.format(*tup) + '}')
return_str = ','.join(output_list)
print('[' + return_str + ']')

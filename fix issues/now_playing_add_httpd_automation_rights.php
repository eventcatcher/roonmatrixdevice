<?php 

exec('osascript -e \'tell application "System Events" to (name of processes) contains "Spotify"\'', $output, $retval); 

echo "System Events done\n";

exec('osascript -e \'
tell application "Music"
	try
		set songTitle to the name of the current track
		set songArtist to the artist of the current track
		set songAlbum to the album of the current track
		set result to "Apple Music%-%" & songArtist & "%-%" & songTitle & "%-%" & songAlbum
	on error m number n
	end try
	if player state is playing then
		return result
	else
		return "Apple Music%-%" & "None" & "%-%" & "None" & "%-%" & "None"
	end if
end tell\'', $output, $retval); 

echo "Apple Music done\n";

exec('osascript -e \'
tell application "Spotify"
	set songTitle to the name of the current track
	set songArtist to the artist of the current track
	set songAlbum to the album of the current track
	set result to "Spotify%-%" & songArtist & "%-%" & songTitle & "%-%" & songAlbum
	if player state is playing then
		return result
	else
		return "Spotify%-%" & "None" & "%-%" & "None" & "%-%" & "None"
	end if
end tell\'', $output, $retval); 

echo "Spotify done\n";

?>

<?php 

// php script to get zone, artist, album, title and cover url (if cover exist) from Apple Music and Spotify, running on macos
//
// Requirements to run this php script (calls python script and applescript):
// 1. You need a installed python 3.x on your macos computer.
// 2. installed python versionmanager: pyenv >= v3.8.
// 3. Export env variables, and replace USERNAME (very important here is PYENV_ROOT and PIPENV_PYTHON, which is used in this script to find python):
// 		export PYENV_ROOT=/Users/USERNAME/.pyenv
// 		export PIPENV_PYTHON=/Users/USERNAME/.pyenv/shims/python
// 		export PYENV_SHELL=bash
// 		export PYENV_VIRTUALENV_INIT=1
// 4. open Apache httpd.conf, located in folder /opt/homebrew/etc/httpd, and add PYENV_ROOT and PIPENV_PYTHON env variables too (and replace USERNAME):
// 		SetEnv PYENV_ROOT "/Users/USERNAME/.pyenv"
// 		SetEnv PIPENV_PYTHON "/Users/USERNAME/.pyenv/shims/python"
// 5. installed python AppleScript library: py-applescript: https://github.com/rdhyee/py-applescript (or from my github account).
// 6. a own local webserver on mac, and website folder located in ~/websites/roonmatrix. Copy this php script into this folder.
// 7. python script now_playing.py, Copy the python script to python folder, located in ~/websites/python.
// 8. environment variable named USER with the name of the macos user the webserver is running on.
// 9. a subfolder for covers, located in: ~/websites/roonmatrix/covers

try {
	$source = isset($_POST['source']) ? $_POST['source'] : ''; 
	$code = isset($_POST['code']) ? $_POST['code'] : ''; 
	$search = isset($_POST['search']) ? $_POST['search'] : ''; 
	$detail = isset($_POST['detail']) ? $_POST['detail'] : ''; 
	$detail2 = isset($_POST['detail2']) ? $_POST['detail2'] : '';

    $playcontrols = ['previous','next','stop','play','shuffle','noshuffle','repeat','norepeat'];

$replaceText = <<<EOD
                    on replaceText(find, replace, theText)
                        set {TID, text item delimiters} to {text item delimiters, find}
                        set textItems to text items of theText
                        set text item delimiters to replace
                        set newText to textItems as text
                        set text item delimiters to TID
                        return newText
                    end replaceText
                EOD;

	if ($source=='Spotify' || $source=='Apple Music') {
		$script = '';
		if ($source == 'Apple Music') {
			$source = 'Music';
		}
		
		switch ($code) {
			case 'previous':
				$script = <<<EOD
                tell application "$source" to previous track
                EOD;    
				break;
			case 'next':
				$script = <<<EOD
                tell application "$source" to next track
                EOD;    
				break;
			case 'stop':
				$script = <<<EOD
                tell application "$source" to pause
                EOD;    
				break;
			case 'play':
				$script = <<<EOD
                tell application "$source" to play
                EOD;    
				break;
			case 'shuffle':
				if ($source == "Music") {
					$script = <<<EOD
                    tell application "$source" to set shuffle enabled to true
                    EOD;    
				} else {
					$script = <<<EOD
                    tell application "$source"
                        if shuffling is false then
                            set shuffling to true
                        end if
                    end tell
                    EOD;    
				}
				break;
			case 'noshuffle':
				if ($source == "Music") {
					$script = <<<EOD
                    tell application "$source" to set shuffle enabled to false
                    EOD;
				} else {
					$script = <<<EOD
                    tell application "$source"
                        if shuffling is true then
                            set shuffling to false
                        end if
                    end tell
                    EOD;    
				}
				break;
			case 'repeat':
				if ($source == "Music") {
					$script = <<<EOD
                    tell application "$source" to set song repeat to all
                    EOD;
				} else {
					$script = <<<EOD
                    tell application "$source"
                        if repeating is false then
                            set repeating to true
                        end if
                    end tell
                    EOD;    
				}
				break;
			case 'norepeat':
				if ($source == "Music") {
					$script = <<<EOD
                    tell application "$source" to set song repeat to off
                    EOD;
				} else {
					$script = <<<EOD
                    tell application "$source"
                        if repeating is true then
                            set repeating to false
                        end if
                    end tell
                    EOD;    
				}
				break;
			case 'artists':
				if ($source == "Music") {
					$script = <<<EOD
                    tell application "$source"
                        set myList to get artist of every track of library playlist 1
                    end tell
                    set list_ref to a reference to myList
                    set r to remove_duplicates(list_ref)
                    return r

                    on remove_duplicates(the_list)
                        set searchTerm to "$search"
                        set return_list to {}
                        repeat with artistName in the_list
                            if artistName is not missing value then
                                if artistName starts with searchTerm then
                                    set artistName to my replaceText("\"", "[dq]", artistName)
                                    set artistStr to "\"" & artistName & "\""
                                    if return_list does not contain artistStr then set end of return_list to (contents of artistStr)
                                end if
                            end if
                        end repeat
                        return return_list
                    end remove_duplicates
                    $replaceText
                    EOD;
				}
				break;
			case 'playlists':
				if ($source == "Music") {
					$script = <<<EOD
                    tell application "$source"
                    	set searchTerm to "$search"
                    	set foundPlaylists to {}

                        set allPlaylists to every playlist
                        repeat with aPlaylist in allPlaylists
                            set playlistName to name of aPlaylist
                            set playlistNameEscaped to my replaceText("\"", "[dq]", playlistName)
                            if playlistName is not missing value then
                                if searchTerm = "" or playlistName starts with searchTerm then
                    				set playlistStr to "\"" & playlistNameEscaped & "\""
                    				if playlistStr is not in foundPlaylists then
                    					set end of foundPlaylists to playlistStr
                    				end if
                    			end if
                    		end if
                    	end repeat

                    	return foundPlaylists as list
                    end tell
                    $replaceText
                    EOD;
				}
				break;
			case 'albums':
				if ($source == "Music") {
					$script = <<<EOD
                    tell application "$source"
                        set targetArtist to "$search"
                        set albumList to {}
                        set trackList to every track of library playlist 1 whose artist is targetArtist

                        repeat with aTrack in trackList
                            set albumName to album of aTrack
                            set albumName to my replaceText("\"", "[dq]", albumName)
                            set albumStr to "\"" & albumName & "\""
                            if albumStr is not in albumList then
                                set end of albumList to albumStr
                            end if
                        end repeat

                        return albumList as list
                    end tell
                    $replaceText
                    EOD;    
				}
				break;
			case 'albumtracks':
				if ($source == "Music") {
					$script = <<<EOD
                    tell application "$source"
                        set targetArtist to "$search"
                        set targetAlbum to "$detail"
                        set trackList to {}
                        set albumSongs to every track of library playlist 1 whose artist is targetArtist and album is targetAlbum

                        repeat with aSong in albumSongs
                            set trackName to name of aSong
                            set trackName to my replaceText("\"", "[dq]", trackName)
                            set trackNumber to (track number of aSong)
                            set trackStr to "\"" & trackNumber & "|" & trackName & "\""
                            if trackStr is not in trackList then
                                set end of trackList to trackStr
                            end if
                        end repeat

                        return trackList
                    end tell
                    $replaceText
                    EOD;    
			    }
			    break;
			case 'playlist-tracks':
				if ($source == "Music") {
					$script = <<<EOD
                    tell application "$source"
                        set targetPlaylist to "$search"
                        set trackList to {}
                        set playlistSongs to every track of playlist targetPlaylist

                        repeat with aSong in playlistSongs
                            set trackName to name of aSong
                            set trackName to my replaceText("\"", "[dq]", trackName)
                            set artistName to artist of aSong
                            set artistName to my replaceText("\"", "[dq]", artistName)
                            set trackStr to "\"" & trackName & "|" & artistName & "\""
                            if trackStr is not in trackList then
                                set end of trackList to trackStr
                            end if
                        end repeat

                        return trackList
                    end tell
                    $replaceText
                    EOD;    
			    }
			    break;
			case 'tracks':
				if ($source == "Music") {
					$script = <<<EOD
                    tell application "$source"
                        set searchTerm to "$search"
                        set return_list to {}
                        set results to name of (every track of playlist 1 whose name contains searchTerm) as list
                        repeat with trackName in results
                            set trackName to my replaceText("\"", "[dq]", trackName)
                            set trackStr to "\"" & trackName & "\""
                            if return_list does not contain trackStr then set end of return_list to (contents of trackStr)
                        end repeat
                        return return_list
                    end tell
                    $replaceText
                    EOD;    
				}
				break;
			case 'tracks-with-artist':
				if ($source == "Music") {
					$script = <<<EOD
                    tell application "$source"
                        set searchTerm to "$search"
                        set return_list to {}
                        repeat with obj in (every track of playlist 1 whose name contains searchTerm)
                            set trackName to name of obj
                            set trackName to my replaceText("\"", "[dq]", trackName)
                            set trackArtist to artist of obj
                            set trackArtist to my replaceText("\"", "[dq]", trackArtist)
                            set trackStr to "\"" & trackName & "|" & trackArtist & "\""
                            if return_list does not contain trackStr then set end of return_list to (contents of trackStr)
                        end repeat
                        return return_list
                    end tell
                    $replaceText
                    EOD;    
				}
				break;
			case 'genres':
				if ($source == "Music") {
					$script = <<<EOD
                    tell application "$source"
                        set searchTerm to "$search"
                        if searchTerm = "" then
                            set allGenres to genre of every track of library playlist 1
                        else
                            set allGenres to genre of every track of library playlist 1 whose genre starts with searchTerm
                        end if
                        set uniqueGenres to {}
                        repeat with i in allGenres
                            set mygenre to (i as string)
                            set genreStr to "\"" & mygenre & "\""
                            if mygenre is not "" and mygenre is not " " and genreStr is not in uniqueGenres then
                                set end of uniqueGenres to genreStr
                            end if
                        end repeat

                        set {old_delims, AppleScript's text item delimiters} to {AppleScript's text item delimiters, linefeed}
                        set sorted_list to paragraphs of (do shell script "sort -t . -k 1,1 <<< " & quoted form of (uniqueGenres as string))
                        set AppleScript's text item delimiters to old_delims

                        return sorted_list as list
                    end tell
                    EOD;    
				}
				break;
			case 'artists-in-genre':
				if ($source == "Music") {
					$script = <<<EOD
                    tell application "$source"
                        set searchTerm to "$search"
                        set foundArtists to {}

                        set allTracks to every track of library playlist 1 whose genre starts with searchTerm
                        repeat with aTrack in allTracks
                            set artistName to artist of aTrack
                            if artistName is not missing value then
                                set artistStr to "\"" & artistName & "\""
                                if artistStr is not in foundArtists then
                                    set end of foundArtists to artistStr
                                end if
                            end if
                        end repeat

                        return foundArtists as list
                    end tell
                    EOD;    
				}
				break;
			case 'playtrack':
				if ($source == "Music") {
				    if ($detail == '' && $detail2 == '') {
                        $script = <<<EOD
                        tell application "$source"
                            set myTrack to "$search"
                            play (first track of library playlist 1 whose name is myTrack)
                        end tell
                        EOD;
				    } else if ($detail != '' && $detail2 == '') {
                        $script = <<<EOD
                        tell application "$source"
                            set myTrack to "$search"
                            set targetArtist to "$detail"
                            play (first track of library playlist 1 whose name is myTrack and artist is targetArtist)					    
                        end tell
                        EOD;
				    } else {
                        $script = <<<EOD
                        tell application "$source"
                            set targetArtist to "$search"
                            set targetAlbum to "$detail"
                            set albumTrack to "$detail2"

                            set playlistName to "Coverplayer"
                            set song repeat to off
                            set shuffle enabled to false

                            if (exists user playlist playlistName) then
                                delete every track of user playlist playlistName
                            else
                                make new user playlist with properties {name:playlistName}
                            end if

                            set thePlaylist to user playlist playlistName
                            set albumTracks to (every track of library playlist 1 whose artist is targetArtist and album is targetAlbum)
                            set found to false

                            repeat with t in albumTracks
                                if name of t is albumTrack then
                                    set found to true
                                end if
                                if found is true then
                                    duplicate t to thePlaylist
                                end if
                            end repeat

                            play thePlaylist
                        end tell
                        EOD;
				    }
			    }
			    if ($source == "Spotify") {
                    $script = <<<EOD
                    tell application "$source"
                        set playCommand to "$search"
                        play track playCommand
                    end tell
                    EOD;
			    }
			    break;
			case 'play-playlist-track':
				if ($source == "Music") {
				    if ($detail == '' && $detail2 == '') {
                        $script = <<<EOD
                        tell application "$source"
                            set thePlaylist to user playlist "$search"
                            play thePlaylist
                        end tell
                        EOD;
				    } else if ($detail != '' && $detail2 == '') {
                        $script = <<<EOD
                        tell application "$source"
                            set sourcePlaylist to "$search"
                            set playlistTrack to "$detail"

                            set playlistName to "Coverplayer"
                            set song repeat to off
                            set shuffle enabled to false

                            if (exists user playlist playlistName) then
                                delete every track of user playlist playlistName
                            else
                                make new user playlist with properties {name:playlistName}
                            end if

                            set thePlaylist to user playlist playlistName
                            set playlistTracks to (every track of user playlist sourcePlaylist)
                            set found to false

                            repeat with t in playlistTracks
                                if name of t is playlistTrack then
                                    set found to true
                                end if
                                if found is true then
                                    duplicate t to thePlaylist
                                end if
                            end repeat

                            play thePlaylist
                        end tell
                        EOD;
				    }
			    }
			    if ($source == "Spotify") {
                    $script = <<<EOD
                    tell application "$source"
                        set playCommand to "$search"
                        play track playCommand
                    end tell
                    EOD;
			    }
			    break;
		}

		if ($script!='') {
		    $cmd = 'osascript -e ' . escapeshellarg($script);
			$json_str = shell_exec($cmd);

            if ($code=='artists' || $code=='albums' || $code=='albumtracks' || $code=='tracks' || $code=='tracks-with-artist' || $code=='playlists' || $code=='playlist-tracks' || $code=='play-playlist-track' || $code=='genres' || $code=='artists-in-genre') {
		        if ($json_str != null) {
			        $output = "[".$json_str."]";
		        } else {
        	        $output = 'script error';
		        }
		
		        header('Content-Type: application/json; charset=utf-8');
		        echo $output;
		    }
            if ($code=='playtrack') {
		        header('Content-Type: application/json; charset=utf-8');
		        echo $cmd;
            }
		}
	}

	if (($source!='Spotify' && $source!='Apple Music') || in_array($code,$playcontrols) ) {
		$pyenvFolderName = '.pyenv';
		$pyenvPythonPath = '/shims/python';
		$pythonScriptName = 'now_playing.py';

		$envUser = getenv('USER');
		$envHomePath = getenv('HOME');
		$envPythonPath = getenv('PIPENV_PYTHON');
		$envPyenvRoot = getenv('PYENV_ROOT');
	    
	    // create subfolder covers to save all covers which are taken from local Apple Music library (folder for max 50 of the newest covers, the rest will be automatically removed)
	    if (!is_dir('covers')) {
        	if (!mkdir('covers', 0777, true)) {
            	echo "Error creating the covers subdirectory!";
            	return;
           	}
        }
	
		$username = '';
		if ($envUser !== false && strlen($envUser) > 0) {
			$username = $envUser;
		} else if ($envHomePath !== false && strlen($envHomePath) > 0) {
			$homePathParts = explode("/", $envHomePath);
			$username = end($homePathParts);	// fallback: get username from HOME path
		}
		
		$pythonPath = '';
		if ($envPythonPath !== false && strlen($envPythonPath) > 0) {
			$pythonPath = $envPythonPath;	// get path to python from env property PIPENV_PYTHON (environment variables, e.g. /Users/USERNAME/.pyenv/shims/python)
		} else if ($envPyenvRoot !== false && strlen($envPyenvRoot) > 0) {
			$pythonPath = $envPyenvRoot.$pyenvPythonPath;	// as fallback: get path to python from env property PYENV_ROOT (environment variables, e.g. /Users/USERNAME/.pyenv/shims/python)
		} else {
			if ($envHomePath !== false && strlen($envHomePath) > 0) {
				$pythonPath = $envHomePath.'/'.$pyenvFolderName.$pyenvPythonPath;	// as fallback: replace USERNAME with your macos username
			} else if ($username != '') {
				$pythonPath = '/Users/'.$username.'/'.$pyenvFolderName.$pyenvPythonPath;	// as fallback: replace USERNAME with your macos username
			}
		}
		
		if ($username == '' || $pythonPath =='') {
			echo "Error: username and/or pythonPath not found.";
			return;
		}
				
		$docRoot = '';
		if (isset($_SERVER['DOCUMENT_ROOT']) && strlen($_SERVER['DOCUMENT_ROOT']) > 0) {
			$docRoot = $_SERVER['DOCUMENT_ROOT'];
		} else if (isset($_SERVER['PWD']) && strlen($_SERVER['PWD']) > 0) {
			$docRoot = $_SERVER['PWD'];		// if started with php cmd, get document root from PWD
		}
		if ($docRoot != '' && strlen($docRoot) > 0 && strpos($docRoot, '/') !== false) {
			if (isset($_SERVER['PHP_SELF']) && strlen($_SERVER['PHP_SELF']) > 0 && strpos($_SERVER['PHP_SELF'], '/') !== false) {
				$subDirParts = explode('/', $_SERVER['PHP_SELF']);
				array_pop($subDirParts);
				$subDir = implode('/', $subDirParts);
				if (substr($_SERVER['PHP_SELF'],0,1) !== '/') {
					$docRoot.='/';
				}
				$docRoot.=$subDir;
			}	
			$docRootParts = explode('/', $docRoot);
			array_pop($docRootParts);
			array_push($docRootParts, 'python'); // replace roonmatrix website script folder with python script folder which is in a same parent folder
			$pythonScriptPath = implode('/', $docRootParts).'/';
		} else {
			$pythonScriptPath = '/Users/'.$username.'/websites/python/';
		}

		$json_str = shell_exec($pythonPath.' '.$pythonScriptPath.$pythonScriptName);	// call python script and get returned payload
		if ($json_str != null) {
			// in json string array with objects, escape all doublequotes inside object property values strings
			$len = strlen($json_str);
			$output = '';
			for ($i = 0; $i < $len; $i++) {
				$char = $json_str[$i];
		
				$match1 = $i<($len-3) && substr($json_str,$i,4)=='": "';
				$match2 = $i<($len-1) && substr($json_str,$i,2)=='{"';
				$match3 = $i<($len-3) && substr($json_str,$i,4)=='", "';
				$match4 = $i<($len-1) && substr($json_str,$i,2)=='"}';

				if ($match1 || $match3) {
					$output .= substr($json_str,$i,4);
					$i+=3;
				} else if ($match2 || $match4) {
					$output .= substr($json_str,$i,2);
					$i+=1;
				} else if ($char=='"') {
					$output .= '\"';	// escape DOUBLE QUOTE
				} else {
					$output .= $char;
				}
			}
		} else {
        	$output = 'script error';
		}
		
		header('Content-Type: application/json; charset=utf-8');
		echo $output;	
	}
} catch (Exception $e) {
	echo "Exception: " . $e->getMessage();
    return;
}

?>
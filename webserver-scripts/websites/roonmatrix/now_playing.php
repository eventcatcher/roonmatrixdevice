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

	if ($source=='Spotify' || $source=='Apple Music') {
		$cmd = '';
		if ($source == 'Apple Music') {
			$source = 'Music';
		}
		
		switch ($code) {
			case 'previous':
				$cmd = 'osascript -e \'tell application "'.$source.'" to previous track\';';
				break;
			case 'next':
				$cmd = 'osascript -e \'tell application "'.$source.'" to next track\';';
				break;
			case 'stop':
				$cmd = 'osascript -e \'tell application "'.$source.'" to pause\';';
				break;
			case 'play':
				$cmd = 'osascript -e \'tell application "'.$source.'" to play\';';
				break;
			case 'shuffle':
				if ($source == "Music") {
					$cmd = 'osascript -e \'tell application "'.$source.'" to set shuffle enabled to true\';';
				} else {
					$cmd = 'osascript -e \'tell application "'.$source.'"
						if shuffling is false then
							set shuffling to true
							if repeating is false then
								set repeating to true
							end if
						end if
					end tell\';';
				}
				break;
			case 'noshuffle':
				if ($source == "Music") {
					$cmd = 'osascript -e \'tell application "'.$source.'" to set shuffle enabled to false\';';
				} else {
					$cmd = 'osascript -e \'tell application "'.$source.'"
						if shuffling is true then
							set shuffling to false
							if repeating is true then
								set repeating to false
							end if
						end if
					end tell\';';
				}
				break;
			case 'repeat':
				if ($source == "Music") {
					$cmd = 'osascript -e \'tell application "'.$source.'" to set song repeat to all\';';
				} else {
					$cmd = 'osascript -e \'tell application "'.$source.'"
						if repeating is false then
							set repeating to true
						end if
					end tell\';';
				}
				break;
			case 'norepeat':
				if ($source == "Music") {
					$cmd = 'osascript -e \'tell application "'.$source.'" to set song repeat to off\';';
				} else {
					$cmd = 'osascript -e \'tell application "'.$source.'"
						if repeating is true then
							set repeating to false
						end if
					end tell\';';
				}
				break;
			case 'artists':
				if ($source == "Music") {
					$cmd = 'osascript -e \'tell application "'.$source.'"
	                    set myList to get artist of every track of library playlist 1
                    end tell
                    set list_ref to a reference to myList
                    set r to remove_duplicates(list_ref)
                    return r

                    on remove_duplicates(the_list)
	                    set searchTerm to "'.$search.'"
	                    set return_list to {}
	                    repeat with artistName in the_list
		                    if artistName is not missing value then
			                    if artistName starts with searchTerm then
				                    set artistStr to "\"" & artistName & "\""
				                    if return_list does not contain artistStr then set end of return_list to (contents of artistStr)
			                    end if
		                    end if
	                    end repeat
	                    return return_list
                    end remove_duplicates\';';
				}
				break;
			case 'albums':
				if ($source == "Music") {
					$cmd = 'osascript -e \'tell application "'.$source.'"
	                    set targetArtist to "'.$search.'"
	                    set albumList to {}
	                    set trackList to every track of library playlist 1 whose artist is targetArtist
	
	                    repeat with aTrack in trackList
	                    	set albumName to album of aTrack
	                    	set albumStr to "\"" & albumName & "\""
	                    	if albumStr is not in albumList then
			                    set end of albumList to albumStr
		                    end if
	                    end repeat
	
                        return albumList as list
					end tell\';';
				}
				break;
			case 'albumtracks':
				if ($source == "Music") {
					$cmd = 'osascript -e \'tell application "'.$source.'"
	                    set targetArtist to "'.$search.'"
	                    set targetAlbum to "'.$detail.'"
	                    set trackList to {}
	                    set albumSongs to every track of library playlist 1 whose artist is targetArtist and album is targetAlbum
	
	                    repeat with aSong in albumSongs
	                    	set trackName to name of aSong
	                        set trackNumber to (track number of aSong)
	                        set trackStr to "\"" & trackNumber & "|" & trackName & "\""
	                    	if trackStr is not in trackList then
	                    	    set end of trackList to trackStr
	                    	end if
	                    end repeat
	
	                    return trackList
					end tell\';';
			    }
			    break;
			case 'tracks':
				if ($source == "Music") {
					$cmd = 'osascript -e \'tell application "'.$source.'"
					    set searchTerm to "'.$search.'"
	                    set return_list to {}
	                    set results to name of (every track of playlist 1 whose name contains searchTerm) as list
	                    repeat with trackName in results
		                    set trackStr to "\"" & trackName & "\""
		                    if return_list does not contain trackStr then set end of return_list to (contents of trackStr)
	                    end repeat
	                    return return_list
                    end tell\';';
				}
				break;
			case 'playtrack':
				if ($source == "Music") {
				    if ($detail == '' && $detail2 == '') {
					    $cmd = 'osascript -e \'tell application "'.$source.'"
	                        set myTrack to "'.$search.'"
	                        play (first track of library playlist 1 whose name is myTrack)
					    end tell\';';
				    } else {
					    $cmd = 'osascript -e \'tell application "'.$source.'"
	                        set targetArtist to "'.$search.'"
	                        set targetAlbum to "'.$detail.'"
	                        set albumTrack to "'.$detail2.'"

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
					    end tell\';';
				    }
			    }
			    if ($source == "Spotify") {
					$cmd = 'osascript -e \'tell application "'.$source.'"
	                    set playCommand to "'.$search.'"
	                    play track playCommand
					end tell\';';
			    }
			    break;
		}

		if ($cmd!='') {
			$json_str = shell_exec($cmd);

            if ($code=='artists' || $code=='albums' || $code=='albumtracks' || $code=='tracks') {
		        if ($json_str != null) {
			        $output = "[".$json_str."]";
		        } else {
        	        $output = 'script error';
		        }
		
		        header('Content-Type: application/json; charset=utf-8');
		        echo $output;
		    }
		}
	} else {
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
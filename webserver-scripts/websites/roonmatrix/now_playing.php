<?php 

// Requirements to run this php script (calls python script and applescript):
// 1. You need a installed python 3.x on your macos computer.
// 2. installed python versionmanager: pyenv >= v3.8.
// 3. Export env variables (very important here is PIPENV_PYTHON, which is used in this script to find python):
// 		export PYENV_ROOT=/Users/USERNAME/.pyenv
// 		export PIPENV_PYTHON=/Users/USERNAME/.pyenv/shims/python
// 		export PYENV_SHELL=bash
// 		export PYENV_VIRTUALENV_INIT=1
// 4. installed python AppleScript library: py-applescript: https://github.com/rdhyee/py-applescript (or from my github account).
// 5. a own local webserver on mac, and website folder located in ~/websites/roonmatrix. Copy this php script into this folder.
// 6. python script now_playing.py, Copy the python script to python folder, located in ~/websites/python.
// 7. environment variable named USER with the name of the macos user the webserver is running on.

$source = isset($_POST['source']) ? $_POST['source'] : ''; 
$code = isset($_POST['code']) ? $_POST['code'] : ''; 

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
	}

	if ($cmd!='') {
		shell_exec($cmd);
	}
} else {
	$pythonPath = getenv('PIPENV_PYTHON');	// get path to python from env property PIPENV_PYTHON (environment variables, e.g. /Users/USERNAME/.pyenv/shims/python)
	if ($pythonPath === false) {
		$pythonPath = getenv('PYENV_ROOT');	// as fallback: get path to python from env property PYENV_ROOT (environment variables, e.g. /Users/USERNAME/.pyenv/shims/python)
		if ($pythonPath) {
			$pythonPath = $pythonPath.'/shims/python';
		}
	}
	if ($pythonPath === false) {
		$pythonPath = '/Users/USERNAME/.pyenv/shims/python';	// as fallback: replace USERNAME with your macos username
	}
	$username = getenv('USER');
	
	$json_str = shell_exec($pythonPath." /Users/".$username."/websites/python/now_playing.py");

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
	
	header('Content-Type: application/json; charset=utf-8');
	echo $output;	
}

?>
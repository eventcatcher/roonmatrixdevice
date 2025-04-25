<?php 

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
	$json_str = shell_exec("/Users/USERNAME/.pyenv/shims/python /Users/USERNAME/websites/python/now_playing.py");

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
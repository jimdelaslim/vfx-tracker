from models import db, Shot, timecode_to_frames, frames_to_timecode
import opentimelineio as otio

import re

def parse_vfx_elements(clip_name):
    """
    Parse VFX code, plate type, element number, and version from clip name
    
    Flexible format: PROJECT_SCENE_SHOT_[plateType][plateNum]_v[version]
    Examples:
        WILD_038_0010_bg01_v1
        WILD_038_0010_src01_v002
        WILD_038_0010_bgr001_v1
        101_BOR_070_002_bg01_v1
    
    Plate type: any 2-4 letter combo (bg, fg, pl, rf, fx, src, ref, bgr, etc.)
    Plate number: any digit count (01, 001, 0001, etc.)
    Version: any digit count (v1, v01, v001, etc.)
    """
    # Flexible pattern: anything_[2-4 letters][digits]_v[digits]
    pattern = r'^(.+?)_([a-zA-Z]{2,4})(\d+)_v(\d+)$'
    match = re.match(pattern, clip_name, re.IGNORECASE)
    
    if match:
        return {
            'vfx_code': match.group(1),
            'plate_type': match.group(2).lower(),
            'vfx_element': match.group(3),
            'version': int(match.group(4))
        }
    
    # Fallback: treat entire name as VFX code
    return {
        'vfx_code': clip_name,
        'plate_type': None,
        'vfx_element': None,
        'version': 1
    }


def init_db(app):
    """Initialize the database"""
    db.init_app(app)
    with app.app_context():
        db.create_all()
        print("Database initialized!")


def parse_m2_lines(edl_text):
    """Parse M2 motion effect lines from raw EDL text"""
    m2_data = {}
    lines = edl_text.split('\n')
    current_event = None
    
    for i, line in enumerate(lines):
        # Track which event we're on
        if line and line[0].isdigit() and len(line.split()) >= 8:
            try:
                event_num = int(line.split()[0])
                current_event = event_num
            except:
                pass
        
        # Look for M2 lines
        if line.startswith('M2') and current_event:
            parts = line.split()
            if len(parts) >= 3:
                try:
                    source_fps = float(parts[2])
                    m2_data[current_event] = source_fps
                except:
                    pass
    
    return m2_data

def import_edl(filepath, fps=24.0):
    """Import an EDL file and return a list of shot dictionaries"""
    # First, read raw EDL text to parse M2 lines
    with open(filepath, 'r') as f:
        edl_text = f.read()
    
    m2_data = parse_m2_lines(edl_text)
    
    timeline = otio.adapters.read_from_file(filepath, adapter_name="cmx_3600")
    
    shots = []
    event_num = 1
    
    for track in timeline.tracks:
        for item in track:
            if isinstance(item, otio.schema.Clip):
                # Parse VFX elements from clip name
                parsed = parse_vfx_elements(item.name)
                
                shot_data = {
                    'clip_name': item.name,
                    'vfx_code': parsed['vfx_code'],
                    'plate_type': parsed['plate_type'],
                    'vfx_element': parsed['vfx_element'],
                    'version': parsed['version'],
                    'event_number': event_num,
                    'fps': fps,
                }
                
                if item.source_range:
                    shot_data['source_in'] = item.source_range.start_time.to_timecode()
                    shot_data['source_out'] = item.source_range.end_time_exclusive().to_timecode()
                    shot_data['duration_frames'] = int(item.source_range.duration.value)
                
                # Extract reel/tape name from metadata and auto-populate cam_roll
                if item.metadata:
                    reel = item.metadata.get('cmx_3600', {}).get('reel', '')
                    shot_data['reel'] = reel
                    shot_data['cam_roll'] = reel  # Auto-populate cam_roll with tape name
                
                # Detect M2 but don't auto-set crank - store for warning
                if event_num in m2_data:
                    source_fps = m2_data[event_num]
                    timeline_fps = 24.0
                    detected_crank = (source_fps / timeline_fps) * 100
                    shot_data['detected_respeed'] = detected_crank  # For warning only
                    # Don't auto-set crank_speed - leave at default 100%
                    
                    # IMPORTANT: Adjust duration_frames to be source frames, not timeline frames
                    # Timeline has 57 frames, but those are 114 source frames at 200% speed
                    # duration_frames should be source frames needed (for calculations)
                    if 'duration_frames' in shot_data:
                        timeline_frames = shot_data['duration_frames']
                        source_frames = int(timeline_frames * (detected_crank / 100.0))
                        shot_data['duration_frames'] = source_frames
                        
                        # Also recalculate source_out timecode to reflect actual source frames needed
                        if 'source_in' in shot_data:
                            source_in_frames = timecode_to_frames(shot_data['source_in'], fps)
                            correct_source_out_frames = source_in_frames + source_frames
                            shot_data['source_out'] = frames_to_timecode(correct_source_out_frames, fps)
                
                shots.append(shot_data)
                event_num += 1
    
    return shots

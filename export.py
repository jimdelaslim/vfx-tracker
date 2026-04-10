from models import Shot, timecode_to_frames, frames_to_timecode

def generate_pull_edl(shots, title="VFX_PULL_EDL"):
    """
    Generate a CMX3600 EDL for pulling source footage with handles
    """
    edl_lines = []
    
    # EDL Header
    edl_lines.append(f"TITLE: {title}")
    edl_lines.append("FCM: NON-DROP FRAME")
    edl_lines.append("")
    
    for idx, shot in enumerate(shots, 1):
        # Format: EVENT  REEL  TRACK  EDIT_TYPE  SOURCE_IN  SOURCE_OUT  RECORD_IN  RECORD_OUT
        
        # Reel name (use cam roll if available, otherwise clip name)
        reel = shot.cam_roll or shot.reel or shot.clip_name[:8].upper()
        
        # Get scan timecodes (with handles)
        scan_in = shot.tc_scan_in()
        scan_out = shot.tc_scan_out()
        
        # Record timecodes - sequential on timeline starting at 01:00:00:00
        # Calculate duration with handles
        scan_in_frames = timecode_to_frames(scan_in, shot.fps)
        scan_out_frames = timecode_to_frames(scan_out, shot.fps)
        duration = scan_out_frames - scan_in_frames
        
        # Record in starts at previous shot's record out (or 01:00:00:00 for first shot)
        if idx == 1:
            record_in = "01:00:00:00"
            record_in_frames = timecode_to_frames(record_in, shot.fps)
        else:
            # Continue from where last shot ended (use tracked value)
            record_in_frames = last_record_out_frames
            record_in = frames_to_timecode(record_in_frames, shot.fps)
        
        record_out_frames = record_in_frames + duration
        record_out = frames_to_timecode(record_out_frames, shot.fps)
        
        # Track this for next iteration
        last_record_out_frames = record_out_frames
        
        # Main event line
        event_line = f"{idx:03d}  {reel:8s} V     C        {scan_in} {scan_out} {record_in} {record_out}"
        edl_lines.append(event_line)
        
        # Add comment with full clip name (as imported)
        edl_lines.append(f"* FROM CLIP NAME: {shot.clip_name}")
        
        # Timecodes already include handles - no need for additional comments
        
        # Add vendor info if present
        if shot.vendor:
            edl_lines.append(f"* VENDOR: {shot.vendor}")
        
        edl_lines.append("")
    
    return "\n".join(edl_lines)


def generate_vfx_report(shots):
    """
    Generate a text report of all VFX shots with frame ranges and timecodes
    """
    report_lines = []
    report_lines.append("=" * 100)
    report_lines.append("VFX SHOT REPORT")
    report_lines.append("=" * 100)
    report_lines.append("")
    
    for shot in shots:
        frame_range = shot.frame_range_display()
        source_head, source_tail = shot.source_handles()
        
        report_lines.append(f"SHOT: {shot.clip_name}")
        report_lines.append(f"VFX Code: {shot.vfx_code or 'N/A'}")
        report_lines.append(f"Status: {shot.status}")
        report_lines.append(f"Vendor: {shot.vendor or 'N/A'}")
        report_lines.append("")
        
        # Frame range
        report_lines.append(f"FRAME RANGE: {frame_range['head_start']} [{frame_range['head_frames']}] {frame_range['head_end']}    {frame_range['shot_start']} [{frame_range['shot_frames']}] {frame_range['shot_end']}    {frame_range['tail_start']} [{frame_range['tail_frames']}] {frame_range['tail_end']}")
        report_lines.append(f"Starting Frame: {frame_range['shot_start']}")
        report_lines.append("")
        
        # Timecodes
        report_lines.append(f"TC Cut In:  {shot.source_in} to {shot.source_out}")
        report_lines.append(f"TC Scan In: {shot.tc_scan_in()} to {shot.tc_scan_out()}")
        report_lines.append("")
        
        # Frame counts
        report_lines.append(f"Length: {shot.duration_frames} frames (output)")
        if shot.crank_speed != 100.0:
            report_lines.append(f"Source Length: {shot.source_frames_needed()} frames @ {shot.crank_speed}%")
        report_lines.append(f"Total Scan: {shot.total_source_frames()} frames (source for vendor)")
        report_lines.append(f"Handles: {shot.head_handles}/{shot.tail_handles} (output) > {source_head}/{source_tail} (source)")
        
        if shot.crank_speed != 100.0:
            report_lines.append("")
            report_lines.append(f"RETIMED CLIP: {shot.crank_speed}%")
        
        report_lines.append("")
        report_lines.append("-" * 100)
        report_lines.append("")
    
    return "\n".join(report_lines)

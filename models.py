from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import re

db = SQLAlchemy()

def timecode_to_frames(timecode, fps=24.0):
    """Convert timecode (HH:MM:SS:FF) to frame count"""
    if not timecode:
        return 0
    parts = timecode.split(':')
    if len(parts) != 4:
        return 0
    hours, minutes, seconds, frames = map(int, parts)
    total_frames = (hours * 3600 + minutes * 60 + seconds) * fps + frames
    return int(total_frames)

def frames_to_timecode(frames, fps=24.0):
    """Convert frame count to timecode (HH:MM:SS:FF)"""
    frames = int(frames)
    ff = frames % int(fps)
    total_seconds = frames // int(fps)
    ss = total_seconds % 60
    mm = (total_seconds // 60) % 60
    hh = total_seconds // 3600
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


class Project(db.Model):
    __tablename__ = 'projects'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    fps = db.Column(db.Float, default=24.0)  # Project frame rate
    logo_filename = db.Column(db.String(200))  # Filename of uploaded logo
    logo_path = db.Column(db.Text)  # Full path to logo file
    path_aliases = db.Column(db.Text)  # JSON list of base paths for reference images
    cache_enabled = db.Column(db.Boolean, default=True)  # Enable/disable image caching
    default_start_frame = db.Column(db.Integer, default=1001)  # Default starting frame for new plates
    is_active = db.Column(db.Boolean, default=False)  # Only one project can be active at a time
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to shots
    shots = db.relationship('Shot', back_populates='project', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Project {self.name}>'




class VFXCode(db.Model):
    """VFX Code level data - one per VFX code (e.g., WILD_038_0010)"""
    __tablename__ = 'vfx_codes'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Link to project
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    project = db.relationship('Project', backref=db.backref('vfx_codes', lazy=True))
    shots = db.relationship('Shot', backref='vfx_code_obj', cascade='all, delete-orphan', lazy=True)
    
    # VFX Code identifier
    vfx_code = db.Column(db.String(100), nullable=False, index=True)
    
    # Shot-level status and info
    shot_status = db.Column(db.String(50), default='Prep')  # Prep, Ready, Turned Over, Update
    turnover_number = db.Column(db.String(50))
    turnover_date = db.Column(db.Date)
    
    # Vendors (4 fields)
    vendor_1 = db.Column(db.String(200))
    vendor_2 = db.Column(db.String(200))
    vendor_3 = db.Column(db.String(200))
    vendor_4 = db.Column(db.String(200))
    
    # VFX-level notes
    scope_of_work = db.Column(db.Text)
    vfx_editorial_note = db.Column(db.Text)
    internal_notes = db.Column(db.Text)  # Internal notes - NOT exported to PDFs
    reference_image = db.Column(db.String(500))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to shots (plates)
    shots = db.relationship('Shot', back_populates='vfx_code_obj', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<VFXCode {self.vfx_code}>'


class Shot(db.Model):
    __tablename__ = 'shots'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Link to project
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    project = db.relationship('Project', back_populates='shots')
    
    # Link to VFX Code
    vfx_code_id = db.Column(db.Integer, db.ForeignKey('vfx_codes.id'))
    vfx_code_obj = db.relationship('VFXCode', back_populates='shots')
    
    # Plate-specific fields
    plate_number = db.Column(db.Integer, default=0)  # 0 means unassigned
    start_frame = db.Column(db.Integer, default=1001)  # Starting frame for vendor delivery
    plate_status = db.Column(db.String(50), default='Prep')  # Prep, Ready, UPDATE
    plate_rev = db.Column(db.String(100))
    pull_date = db.Column(db.Date)
    element_notes = db.Column(db.Text)
    resize_reposition = db.Column(db.Text)
    retime_notes = db.Column(db.Text)

    
    # EDL Data
    clip_name = db.Column(db.String(200), nullable=False)
    event_number = db.Column(db.Integer)
    source_in = db.Column(db.String(20))
    source_out = db.Column(db.String(20))
    record_in = db.Column(db.String(20))
    record_out = db.Column(db.String(20))
    duration_frames = db.Column(db.Integer)
    fps = db.Column(db.Float, default=24.0)
    
    # VFX Metadata
    vfx_code = db.Column(db.String(100))
    vfx_element = db.Column(db.String(200))
    version = db.Column(db.Integer, default=1)
    turnover_number = db.Column(db.String(50))
    turnover_date = db.Column(db.Date)  # Date when shots were turned over
    
    # Shot Details
    plate_type = db.Column(db.String(50))
    vendor = db.Column(db.String(200))
    status = db.Column(db.String(50), default='Prep')
    
    # Handles & Timing
    head_handles = db.Column(db.Integer, default=0)
    tail_handles = db.Column(db.Integer, default=0)
    crank_speed = db.Column(db.Float, default=100.0)
    detected_respeed = db.Column(db.Float)  # Detected from EDL M2 line (for warning)
    
    # Additional Info
    scope_of_work = db.Column(db.Text)
    notes = db.Column(db.Text)
    reference_image = db.Column(db.String(500))  # Path to reference image
    cam_roll = db.Column(db.String(100))
    reel = db.Column(db.String(100))
    
    # Camera & Lens Metadata
    camera = db.Column(db.String(100))
    lens = db.Column(db.String(100))
    focal_length = db.Column(db.String(50))
    t_stop = db.Column(db.String(50))
    shutter = db.Column(db.String(50))
    iso = db.Column(db.String(50))
    white_balance = db.Column(db.String(50))
    lut = db.Column(db.String(200))
    resolution = db.Column(db.String(50))
    codec = db.Column(db.String(100))
    color_space = db.Column(db.String(100))
    gamma = db.Column(db.String(100))
    file_path = db.Column(db.Text)
    camera_clipname = db.Column(db.String(200))
    
    # Extended Metadata
    shot_frame_rate = db.Column(db.String(50))
    start_tc = db.Column(db.String(50))
    end_tc = db.Column(db.String(50))
    start_frame = db.Column(db.String(50))
    end_frame = db.Column(db.String(50))
    total_frames = db.Column(db.String(50))
    camera_manufacturer = db.Column(db.String(100))
    camera_serial = db.Column(db.String(100))
    shutter_angle = db.Column(db.String(50))
    shutter_speed = db.Column(db.String(50))
    distance = db.Column(db.String(50))
    nd_filter = db.Column(db.String(50))
    camera_tilt = db.Column(db.String(50))
    camera_roll = db.Column(db.String(50))
    
    # Tracking
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    pull_date = db.Column(db.DateTime)
    
    def __repr__(self):
        return f'<Shot {self.clip_name} - {self.vfx_code}>'
    
    def source_frames_needed(self):
        """Calculate source frames needed based on output duration and crank speed"""
        output_frames = self.duration_frames or 0
        return int(output_frames * (self.crank_speed / 100.0))
    
    def source_handles(self):
        """Return source handles directly (input boxes already contain source handles)"""
        head = self.head_handles or 0
        tail = self.tail_handles or 0
        return head, tail
    
    def total_source_frames(self):
        """Total SOURCE frames to scan (including handles)"""
        # This is what vendor actually scans from the source material
        # Example: 114 source frames + 16 head + 16 tail = 146 frames
        return (self.duration_frames or 0) + (self.head_handles or 0) + (self.tail_handles or 0)
    
    def total_frames_with_handles(self):
        """Calculate total OUTPUT frames including handles"""
        base_frames = self.duration_frames or 0
        handles = (self.head_handles or 0) + (self.tail_handles or 0)
        return base_frames + handles
    
    def frame_range_display(self):
        """Generate the frame range display: 1001 [8] 1008  1009 [170] 1178  1179 [8] 1186"""
        # Display OUTPUT handles (divide source handles by crank to get output)
        crank = self.crank_speed or 100.0
        head = int((self.head_handles or 0) / (crank / 100.0))
        tail = int((self.tail_handles or 0) / (crank / 100.0))
        
        # Calculate ACTION frames accounting for respeed
        # timeline_frames = what's in the timeline (57 frames)
        # If crank is 100% (no respeed): need 57 source frames
        # If crank is 200% (double speed): need 114 source frames (twice as many)
        # If crank is 50% (half speed): need 28.5 source frames (half as many)
        timeline_frames = self.duration_frames or 0
        crank = self.crank_speed or 100.0
        
        # duration_frames already contains SOURCE frames (adjusted on import)
        # To show OUTPUT frames (what vendor delivers), divide by crank
        # Example: 114 source frames at 200% crank = 57 output frames
        source_frames = int(timeline_frames / (crank / 100.0))
        
        # Starting frame (default 1001, but can be customized)
        # Handle start_frame - might be int, string int, or timecode
        try:
            start = int(self.start_frame) if self.start_frame else 1001
        except (ValueError, TypeError):
            start = 1001
        
        # Head handle range
        head_start = start
        head_end = start + head - 1
        
        # Shot range
        shot_start = head_end + 1
        shot_end = shot_start + source_frames - 1
        
        # Tail handle range
        tail_start = shot_end + 1
        tail_end = tail_start + tail - 1
        
        return {
            'head_start': head_start,
            'head_frames': head,
            'head_end': head_end,
            'shot_start': shot_start,
            'shot_frames': source_frames,
            'shot_end': shot_end,
            'tail_start': tail_start,
            'tail_frames': tail,
            'tail_end': tail_end,
            'total_end': tail_end
        }
    
    def tc_scan_in(self):
        """Calculate scan in timecode (source in - head handles)"""
        if not self.source_in:
            return None
        source_in_frames = timecode_to_frames(self.source_in, self.fps)
        head, _ = self.source_handles()
        scan_in_frames = source_in_frames - head
        return frames_to_timecode(scan_in_frames, self.fps)
    
    def tc_scan_out(self):
        """Calculate scan out timecode (source out + tail handles)"""
        if not self.source_out:
            return None
        
        # Start from source_out
        source_out_frames = timecode_to_frames(self.source_out, self.fps)
        
        # Add tail handles
        _, tail = self.source_handles()
        
        scan_out_frames = source_out_frames + tail
        
        return frames_to_timecode(scan_out_frames, self.fps)


    def get_scan_timecodes(self):
        """Calculate scan timecodes including handles"""
        if not self.source_in or not self.source_out:
            return None, None
        
        fps = self.fps or 24.0
        head, tail = self.source_handles()
        
        # Parse timecode HH:MM:SS:FF
        def tc_to_frames(tc_str, fps):
            parts = tc_str.split(':')
            if len(parts) != 4:
                return 0
            h, m, s, f = map(int, parts)
            return int((h * 3600 + m * 60 + s) * fps + f)
        
        def frames_to_tc(frames, fps):
            f = int(frames % fps)
            total_seconds = int(frames // fps)
            s = total_seconds % 60
            m = (total_seconds // 60) % 60
            h = total_seconds // 3600
            return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"
        
        # Calculate scan in (subtract head handles)
        in_frames = tc_to_frames(self.source_in, fps)
        scan_in_frames = max(0, in_frames - head)
        scan_in = frames_to_tc(scan_in_frames, fps)
        
        # Calculate scan out (add tail handles)
        out_frames = tc_to_frames(self.source_out, fps)
        scan_out_frames = out_frames + tail
        scan_out = frames_to_tc(scan_out_frames, fps)
        
        return scan_in, scan_out

    def validate_handles(self):
        """Check if requested handles exceed available source material"""
        if not self.source_in or not self.start_tc or not self.end_tc:
            return {'valid': True}  # Can't validate without metadata
        
        # Get actual source material range from metadata
        source_start_frames = timecode_to_frames(self.start_tc, self.fps)
        source_end_frames = timecode_to_frames(self.end_tc, self.fps)
        
        # Get requested scan range
        scan_in = self.tc_scan_in()
        scan_out = self.tc_scan_out()
        
        if not scan_in or not scan_out:
            return {'valid': True}
        
        scan_in_frames = timecode_to_frames(scan_in, self.fps)
        scan_out_frames = timecode_to_frames(scan_out, self.fps)
        
        # Check if scan range exceeds source material
        head_overflow = max(0, source_start_frames - scan_in_frames)
        tail_overflow = max(0, scan_out_frames - source_end_frames)
        
        is_valid = head_overflow == 0 and tail_overflow == 0
        
        return {
            'valid': is_valid,
            'head_overflow': head_overflow,
            'tail_overflow': tail_overflow,
            'source_start': self.start_tc,
            'source_end': self.end_tc,
            'requested_scan_in': scan_in,
            'requested_scan_out': scan_out
        }


class Vendor(db.Model):
    __tablename__ = 'vendors'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    contact_email = db.Column(db.String(200))
    notes = db.Column(db.Text)
    reference_image = db.Column(db.String(500))  # Path to reference image
    
    def __repr__(self):
        return f'<Vendor {self.name}>'

class CameraMetadata(db.Model):
    """Camera metadata library - stores metadata by cam roll/tape name"""
    id = db.Column(db.Integer, primary_key=True)
    cam_roll = db.Column(db.String(100), unique=True, nullable=False, index=True)
    
    # Camera & Lens Metadata
    camera = db.Column(db.String(100))
    lens = db.Column(db.String(100))
    focal_length = db.Column(db.String(50))
    t_stop = db.Column(db.String(50))
    shutter = db.Column(db.String(50))
    iso = db.Column(db.String(50))
    white_balance = db.Column(db.String(50))
    lut = db.Column(db.String(200))
    resolution = db.Column(db.String(50))
    codec = db.Column(db.String(100))
    color_space = db.Column(db.String(100))
    gamma = db.Column(db.String(100))
    file_path = db.Column(db.Text)
    camera_clipname = db.Column(db.String(200))
    
    # Extended Metadata
    shot_frame_rate = db.Column(db.String(50))
    start_tc = db.Column(db.String(50))
    end_tc = db.Column(db.String(50))
    start_frame = db.Column(db.String(50))
    end_frame = db.Column(db.String(50))
    total_frames = db.Column(db.String(50))
    camera_manufacturer = db.Column(db.String(100))
    camera_serial = db.Column(db.String(100))
    shutter_angle = db.Column(db.String(50))
    shutter_speed = db.Column(db.String(50))
    distance = db.Column(db.String(50))
    nd_filter = db.Column(db.String(50))
    camera_tilt = db.Column(db.String(50))
    camera_roll = db.Column(db.String(50))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<CameraMetadata {self.cam_roll}>'



class ShotHistory(db.Model):
    """Stores historical versions of shots"""
    id = db.Column(db.Integer, primary_key=True)
    shot_id = db.Column(db.Integer, db.ForeignKey('shots.id'), nullable=False)
    
    # Snapshot of shot data
    version = db.Column(db.Integer, nullable=False)
    vfx_code = db.Column(db.String(100))
    clip_name = db.Column(db.String(200))
    reel_name = db.Column(db.String(100))
    record_in = db.Column(db.String(20))
    record_out = db.Column(db.String(20))
    source_in = db.Column(db.String(20))
    source_out = db.Column(db.String(20))
    handles = db.Column(db.Integer)
    source_in_with_handles = db.Column(db.String(20))
    source_out_with_handles = db.Column(db.String(20))
    status = db.Column(db.String(50))
    turnover_number = db.Column(db.String(50))
    turnover_date = db.Column(db.Date)  # Date when shots were turned over
    notes = db.Column(db.Text)
    reference_image = db.Column(db.String(500))  # Path to reference image
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    change_description = db.Column(db.String(500))
    
    shot = db.relationship('Shot', backref=db.backref('history', lazy=True, order_by='ShotHistory.version.desc()'))

class MetadataPreset(db.Model):
    """Store metadata column mapping presets"""
    __tablename__ = 'metadata_presets'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    mapping_json = db.Column(db.Text, nullable=False)  # JSON string of column mappings
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    project = db.relationship('Project', backref=db.backref('metadata_presets', lazy=True))


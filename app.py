from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session, jsonify
from models import db, Shot, Vendor, Project, CameraMetadata, ShotHistory, VFXCode
from database import init_db, import_edl
from export import generate_pull_edl, generate_vfx_report
from utils.pdf_playwright import generate_shot_pdf_playwright as generate_shot_pdf, generate_selected_shots_pdf_playwright
import os
import sys
from io import BytesIO
import json
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = '7a592f1f94e4567e3b29b1d18eabafae05fa21186d4a6197c6d7c351c3406b15'
# Database configuration - can be changed via set_database_path()
# Get database path from environment variable or use writable location
if os.environ.get('VFX_DB_PATH'):
    DATABASE_PATH = os.environ.get('VFX_DB_PATH')
else:
    basedir = os.path.abspath(os.path.dirname(__file__))
    
    # Detect if running as packaged app (PyInstaller frozen or Mac .app bundle)
    is_packaged = getattr(sys, 'frozen', False) or '/Contents/Resources' in basedir
    
    if is_packaged:
        # Running as packaged app - use platform-appropriate app data folder
        if sys.platform == 'win32':
            app_data = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'VFX Shot Tracker')
        elif sys.platform == 'darwin':
            app_data = os.path.expanduser('~/Library/Application Support/VFX Shot Tracker')
        else:
            app_data = os.path.expanduser('~/.local/share/VFX Shot Tracker')
        
        os.makedirs(app_data, exist_ok=True)
        DATABASE_PATH = os.path.join(app_data, 'vfx_tracker.db')
        print(f"Using app data folder: {DATABASE_PATH}")
    else:
        # Running in development
        DATABASE_PATH = 'instance/vfx_tracker.db'
        print(f"Using development: {DATABASE_PATH}")

def get_db_uri():
    """Get database URI from current DATABASE_PATH"""
    global DATABASE_PATH
    # Ensure absolute path
    if not os.path.isabs(DATABASE_PATH):
        DATABASE_PATH = os.path.join(os.path.dirname(__file__), DATABASE_PATH)
    return f'sqlite:///{DATABASE_PATH}'

app.config['SQLALCHEMY_DATABASE_URI'] = get_db_uri()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['LOGO_FOLDER'] = 'static/logos'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# Initialize database

def migrate_database_schema():
    """Auto-migrate database to add any missing columns"""
    try:
        # Wait a moment for database to be ready
        import time
        time.sleep(0.5)
        
        with app.app_context():
            # Use SQLAlchemy's raw connection
            connection = db.engine.raw_connection()
            cursor = connection.cursor()
            
            # Check for internal_notes column
            cursor.execute("PRAGMA table_info(vfx_codes)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'internal_notes' not in columns:
                print("AUTO-MIGRATION: Adding internal_notes column...")
                cursor.execute("ALTER TABLE vfx_codes ADD COLUMN internal_notes TEXT DEFAULT ''")
                connection.commit()
                print("AUTO-MIGRATION: internal_notes complete!")
            
            # Check for path_aliases column in projects table
            cursor.execute("PRAGMA table_info(projects)")
            project_columns = [row[1] for row in cursor.fetchall()]
            
            if 'path_aliases' not in project_columns:
                print("AUTO-MIGRATION: Adding path_aliases column...")
                cursor.execute("ALTER TABLE projects ADD COLUMN path_aliases TEXT DEFAULT '[]'")
                connection.commit()
                print("AUTO-MIGRATION: path_aliases complete!")
            
            if 'cache_enabled' not in project_columns:
                print("AUTO-MIGRATION: Adding cache_enabled column...")
                cursor.execute("ALTER TABLE projects ADD COLUMN cache_enabled BOOLEAN DEFAULT 1")
                connection.commit()
                print("AUTO-MIGRATION: cache_enabled complete!")
            if 'default_start_frame' not in project_columns:
                print("AUTO-MIGRATION: Adding default_start_frame column...")
                cursor.execute("ALTER TABLE projects ADD COLUMN default_start_frame INTEGER DEFAULT 1001")
                connection.commit()
                print("AUTO-MIGRATION: default_start_frame complete!")
            # Check for camera_clipname column in shots table
            cursor.execute("PRAGMA table_info(shots)")
            shot_columns = [row[1] for row in cursor.fetchall()]
            
            if 'camera_clipname' not in shot_columns:
                print("AUTO-MIGRATION: Adding camera_clipname to shots...")
                cursor.execute("ALTER TABLE shots ADD COLUMN camera_clipname VARCHAR(200) DEFAULT ''")
                connection.commit()
                print("AUTO-MIGRATION: camera_clipname (shots) complete!")
            
            # Check for camera_clipname column in camera_metadata table
            cursor.execute("PRAGMA table_info(camera_metadata)")
            meta_columns = [row[1] for row in cursor.fetchall()]
            
            if 'camera_clipname' not in meta_columns:
                print("AUTO-MIGRATION: Adding camera_clipname to camera_metadata...")
                cursor.execute("ALTER TABLE camera_metadata ADD COLUMN camera_clipname VARCHAR(200) DEFAULT ''")
                connection.commit()
                print("AUTO-MIGRATION: camera_clipname (camera_metadata) complete!")
            
            if 'cdl_sat' not in shot_columns:
                print("AUTO-MIGRATION: Adding cdl_sat/cdl_sop to shots...")
                cursor.execute("ALTER TABLE shots ADD COLUMN cdl_sat VARCHAR(50) DEFAULT ''")
                cursor.execute("ALTER TABLE shots ADD COLUMN cdl_sop VARCHAR(200) DEFAULT ''")
                connection.commit()
                print("AUTO-MIGRATION: cdl_sat/cdl_sop (shots) complete!")
            
            if 'cdl_sat' not in meta_columns:
                print("AUTO-MIGRATION: Adding cdl_sat/cdl_sop to camera_metadata...")
                cursor.execute("ALTER TABLE camera_metadata ADD COLUMN cdl_sat VARCHAR(50) DEFAULT ''")
                cursor.execute("ALTER TABLE camera_metadata ADD COLUMN cdl_sop VARCHAR(200) DEFAULT ''")
                connection.commit()
                print("AUTO-MIGRATION: cdl_sat/cdl_sop (camera_metadata) complete!")
            
            cursor.close()
            connection.close()
    except Exception as e:
        print(f"Migration warning: {e}")
        # Don't crash the app if migration fails


init_db(app)
try:
    migrate_database_schema()
except:
    pass  # Migration not critical for startup


# Create folders
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['LOGO_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_active_project():
    """Get the currently active project, or create a default one"""
    project = Project.query.filter_by(is_active=True).first()
    
    if not project:
        # Create default project if none exists
        project = Project(name='Default Project', is_active=True)
        db.session.add(project)
        db.session.commit()
    
    return project




# Helper function for shot versioning
def create_shot_history_entry(shot):
    """Create a history entry from current shot state before updating"""
    history = ShotHistory(
        shot_id=shot.id,
        version=shot.version,
        vfx_code=shot.vfx_code,
        clip_name=shot.clip_name,
        reel_name=shot.reel,
        record_in=shot.record_in,
        record_out=shot.record_out,
        source_in=shot.source_in,
        source_out=shot.source_out,
        handles=shot.head_handles,
        source_in_with_handles=shot.source_in,
        source_out_with_handles=shot.source_out,
        status=shot.status,
        turnover_number=shot.turnover_number,
        notes=shot.notes,
        change_description="EDL import update"
    )
    db.session.add(history)
    return history

def update_shot_from_edl(shot, edl_data):
    """Update existing shot with new EDL data and increment version"""
    # Save current state to history
    create_shot_history_entry(shot)
    
    # Update shot with new data
    shot.clip_name = edl_data['clip_name']
    shot.reel = edl_data['reel_name']
    shot.record_in = edl_data['record_in']
    shot.record_out = edl_data['record_out']
    shot.source_in = edl_data['src_in']
    shot.source_out = edl_data['src_out']
    
    # Recalculate handles
    if shot.head_handles:
        shot.source_in_with_handles = calculate_timecode_with_handles(shot.source_in, -shot.handles)
        shot.source_out_with_handles = calculate_timecode_with_handles(shot.source_out, shot.handles)
    
    # Update status and version
    shot.status = 'Updated'
    shot.version += 1
    
    db.session.commit()
    return shot


def auto_number_plates(project_id):
    """Auto-assign plate numbers within each VFX code based on alphabetical order of plate_type + element"""
    from models import VFXCode, Shot
    
    vfx_codes = VFXCode.query.filter_by(project_id=project_id).all()
    
    for vfx_code in vfx_codes:
        # Sort shots by plate_type then vfx_element alphabetically
        sorted_shots = sorted(vfx_code.shots, key=lambda s: (
            (s.plate_type or '').lower(),
            (s.vfx_element or '00')
        ))
        
        # Assign sequential numbers
        for idx, shot in enumerate(sorted_shots, 1):
            if shot.plate_number != idx:
                shot.plate_number = idx
    
    db.session.commit()


def find_metadata_by_cam_roll(cam_roll):
    """Find camera metadata by cam_roll with fuzzy matching.
    Tries exact match first, then tries prefix/partial matching.
    E.g. shot cam_roll 'A030C002' matches metadata cam_roll 'A030C002_260520US'
    """
    if not cam_roll:
        return None
    
    # Try exact match first
    metadata = CameraMetadata.query.filter_by(cam_roll=cam_roll).first()
    if metadata:
        return metadata
    
    # Try: shot cam_roll is a prefix of metadata cam_roll
    # E.g. shot='A030C002', metadata='A030C002_260520US'
    metadata = CameraMetadata.query.filter(
        CameraMetadata.cam_roll.like(f'{cam_roll}%')
    ).first()
    if metadata:
        return metadata
    
    # Try: metadata cam_roll is a prefix of shot cam_roll
    # E.g. metadata='A030C002', shot='A030C002_260520US'
    all_metadata = CameraMetadata.query.all()
    for m in all_metadata:
        if m.cam_roll and (cam_roll.startswith(m.cam_roll) or m.cam_roll.startswith(cam_roll)):
            return m
    
    return None


@app.route('/index_old')
def index_old():
    """Main dashboard"""
    project = get_active_project()
    shots = Shot.query.filter_by(project_id=project.id).order_by(Shot.event_number).all()
    
    # Group shots by VFX code
    from collections import defaultdict
    grouped_shots = defaultdict(list)
    for shot in shots:
        grouped_shots[shot.vfx_code].append(shot)
    
    # Sort each group by plate_type order
    plate_order = {'bg': 1, 'fg': 2, 'pl': 3, 'rf': 4, 'fx': 5}
    for vfx_code in grouped_shots:
        grouped_shots[vfx_code].sort(key=lambda s: (
            plate_order.get(s.plate_type or 'zz', 99),
            s.vfx_element or '99'
        ))
    
    # Get status counts for active project (including Omitted)
    status_counts = {
        'prep': Shot.query.filter_by(project_id=project.id, status='Prep').count(),
        'ready': Shot.query.filter_by(project_id=project.id, status='Ready').count(),
        'turnover': Shot.query.filter_by(project_id=project.id, status='Turned Over').count(),
        'update': Shot.query.filter_by(project_id=project.id, status='Update').count(),
        'omitted': Shot.query.filter_by(project_id=project.id, status='Omitted').count(),
    }
    
    # Get all projects for switcher
    all_projects = Project.query.order_by(Project.created_at.desc()).all()
    
    return render_template('index.html', shots=shots, grouped_shots=grouped_shots, status_counts=status_counts, 
                         project=project, all_projects=all_projects)




@app.route('/help')
def help_page():
    """Help documentation page"""
    project = get_active_project()
    return render_template('help.html', project=project)

@app.route('/project/create', methods=['POST'])
def create_project():
    """Create a new project"""
    name = request.form.get('name')
    
    if not name:
        flash('Project name is required', 'error')
        return redirect(url_for('index'))
    
    # Handle logo upload
    logo_filename = None
    if 'logo' in request.files:
        file = request.files['logo']
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            logo_filename = timestamp + filename
            file.save(os.path.join(app.config['LOGO_FOLDER'], logo_filename))
    
    # Create new project
    project = Project(name=name, logo_filename=logo_filename, is_active=False)
    db.session.add(project)
    db.session.commit()
    
    flash(f'Project "{name}" created successfully!', 'success')
    return redirect(url_for('index'))



@app.route('/project/switch/<int:project_id>')
def switch_project(project_id):
    """Switch to a different project"""
    # Deactivate all projects
    Project.query.update({'is_active': False})
    
    # Activate selected project
    project = Project.query.get_or_404(project_id)
    project.is_active = True
    db.session.commit()
    
    flash(f'Switched to project: {project.name}', 'success')
    return redirect(url_for('index'))


    
    db.session.commit()
    flash('Project updated successfully!', 'success')
    return redirect(url_for('index'))


@app.route('/project/<int:project_id>/delete', methods=['POST'])
def delete_project(project_id):
    """Delete a project and all its shots"""
    project = Project.query.get_or_404(project_id)
    
    # Don't allow deleting the last project
    if Project.query.count() == 1:
        flash('Cannot delete the last project', 'error')
        return redirect(url_for('index'))
    
    # If deleting active project, activate another one
    if project.is_active:
        other_project = Project.query.filter(Project.id != project_id).first()
        if other_project:
            other_project.is_active = True
    
    # Delete logo if exists
    if project.logo_filename:
        logo_path = os.path.join(app.config['LOGO_FOLDER'], project.logo_filename)
        if os.path.exists(logo_path):
            os.remove(logo_path)
    
    db.session.delete(project)
    db.session.commit()
    
    flash(f'Project "{project.name}" deleted', 'success')
    return redirect(url_for('index'))


@app.route('/import', methods=['GET', 'POST'])
def import_edl_route():
    """Import EDL file"""
    project = get_active_project()
    
    if request.method == 'POST':
        if 'edl_file' not in request.files:
            flash('No file selected', 'error')
            return redirect(request.url)
        
        file = request.files['edl_file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(request.url)
        
        if file and file.filename.endswith('.edl'):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)
            
            # Import the EDL
            try:
                # Get FPS from form or use project default
                fps = request.form.get('fps', type=float)
                if fps is None:
                    fps = project.fps if project else 24.0
                
                # Check if user wants to use Avid markers
                use_markers = request.form.get('use_markers') == 'on'

                shots_data = import_edl(filepath, fps=fps, use_markers=use_markers)
                
                # Check for conflicts
                conflicts = []
                missing_codes = []
                
                for shot_data in shots_data:
                    vfx_code_name = shot_data.get('vfx_code')
                    plate_type = shot_data.get('plate_type')
                    vfx_element = shot_data.get('vfx_element')
                    
                    
                    if not vfx_code_name:
                        missing_codes.append({'clip_name': shot_data.get('clip_name')})
                    else:
                        # Find VFXCode entry
                        vfx_code_obj = VFXCode.query.filter_by(
                            vfx_code=vfx_code_name,
                            project_id=project.id
                        ).first()
                        
                        if vfx_code_obj:
                            # Check if this plate already exists under this VFXCode
                            existing = Shot.query.filter_by(
                                vfx_code_id=vfx_code_obj.id,
                                plate_type=plate_type,
                                vfx_element=vfx_element
                            ).first()
                            
                            if existing:
                                pass  # Existing shot found
                            else:
                                pass  # New shot
                        else:
                            existing = None
                        
                        if existing:
                            conflicts.append({
                                'vfx_code': vfx_code_name,
                                'current_version': existing.version,
                                'status': existing.status,
                                'turnover_number': existing.turnover_number,
                                'shot_data': shot_data
                            })
                
                # Always redirect to confirmation (it will auto-process if no conflicts)
                # Store pending import in temp file (session cookies too small for large EDLs)
                import tempfile
                pending_data = {
                    'filepath': filepath,
                    'conflicts': conflicts,
                    'missing_codes': missing_codes,
                    'all_shots': shots_data
                }
                pending_file = os.path.join(tempfile.gettempdir(), 'vfx_tracker_pending_import.json')
                with open(pending_file, 'w') as pf:
                    json.dump(pending_data, pf)
                session['pending_import_file'] = pending_file
                return redirect(url_for('import_confirmation'))

                
            except Exception as e:
                flash(f'Error importing EDL: {str(e)}', 'error')
                return redirect(request.url)
    
    return render_template('import.html', project=project)




@app.route('/import/metadata', methods=['GET', 'POST'])
def import_metadata():
    """Upload CSV and redirect to mapping screen"""
    project = get_active_project()
    
    if request.method == 'POST':
        if 'metadata_file' not in request.files:
            flash('No file selected', 'error')
            return redirect(request.url)
        
        file = request.files['metadata_file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(request.url)
        
        if file and (file.filename.lower().endswith('.csv') or file.filename.lower().endswith('.ale')):
            import csv
            from io import StringIO
            import os
            
            # Save file temporarily with original extension
            import os
            file_ext = os.path.splitext(file.filename)[1]  # Get .csv or .ale
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], f'temp_metadata{file_ext}')
            file.save(filepath)
            
            # Redirect to mapping screen
            return redirect(url_for('metadata_mapping', filepath=filepath))
            
            library_added = 0
            library_updated = 0
            
            for row in csv_reader:
                clip_name = row.get('File Name', '').strip()
                if not clip_name:
                    continue
                
                cam_roll = os.path.splitext(clip_name)[0]
                
                # Check if metadata exists in library
                metadata = CameraMetadata.query.filter_by(cam_roll=cam_roll).first()
                
                if not metadata:
                    metadata = CameraMetadata(cam_roll=cam_roll)
                    library_added += 1
                else:
                    library_updated += 1
                
                # Update all metadata fields
                metadata.camera = row.get('Camera Type', '')
                metadata.lens = row.get('Lens Type', '')
                metadata.focal_length = row.get('Focal Point (mm)', '')
                metadata.t_stop = row.get('Camera Aperture', '')
                metadata.iso = row.get('ISO', '')
                metadata.white_balance = row.get('White Point (Kelvin)', '')
                metadata.lut = row.get('LUT Used', '')
                metadata.resolution = row.get('Resolution', '')
                metadata.codec = row.get('Video Codec', '')
                metadata.color_space = row.get('Color Space Notes', '')
                metadata.gamma = row.get('Gamma Notes', '')
                metadata.file_path = row.get('Clip Directory', '')
                metadata.shot_frame_rate = row.get('Shot Frame Rate', '')
                metadata.start_tc = row.get('Start TC', '')
                metadata.end_tc = row.get('End TC', '')
                metadata.start_frame = row.get('Start Frame', '')
                metadata.end_frame = row.get('End Frame', '')
                metadata.total_frames = row.get('Frames', '')
                metadata.camera_manufacturer = row.get('Camera Manufacturer', '')
                metadata.camera_serial = row.get('Camera Serial #', '')
                metadata.shutter_angle = row.get('Shutter Angle', '')
                metadata.shutter_speed = row.get('Shutter Speed', '')
                
                if metadata.shutter_angle and metadata.shutter_speed:
                    metadata.shutter = f"{metadata.shutter_angle}° / {metadata.shutter_speed}s"
                elif metadata.shutter_angle:
                    metadata.shutter = f"{metadata.shutter_angle}°"
                elif metadata.shutter_speed:
                    metadata.shutter = f"{metadata.shutter_speed}s"
                
                metadata.distance = row.get('Distance', '')
                metadata.nd_filter = row.get('ND Filter', '')
                metadata.camera_tilt = row.get('Camera Tilt Angle', '')
                metadata.camera_roll = row.get('Camera Roll Angle', '')
                
                db.session.add(metadata)
            
            db.session.commit()
            
            # Link to existing shots
            shots_linked = 0
            all_shots = Shot.query.filter_by(project_id=project.id).all()
            
            for shot in all_shots:
                if shot.cam_roll:
                    metadata = find_metadata_by_cam_roll(shot.cam_roll)
                    if metadata:
                        shot.camera = metadata.camera
                        shot.lens = metadata.lens
                        shot.focal_length = metadata.focal_length
                        shot.t_stop = metadata.t_stop
                        shot.iso = metadata.iso
                        shot.white_balance = metadata.white_balance
                        shot.lut = metadata.lut
                        shot.resolution = metadata.resolution
                        shot.codec = metadata.codec
                        shot.color_space = metadata.color_space
                        shot.gamma = metadata.gamma
                        shot.file_path = metadata.file_path
                        shot.shot_frame_rate = metadata.shot_frame_rate
                        shot.start_tc = metadata.start_tc
                        shot.end_tc = metadata.end_tc
                        # Don't overwrite start_frame if already set by user
                        if not shot.start_frame or str(shot.start_frame) in ('0', ''):
                            shot.start_frame = metadata.start_frame
                        shot.end_frame = metadata.end_frame
                        shot.total_frames = metadata.total_frames
                        shot.camera_manufacturer = metadata.camera_manufacturer
                        shot.camera_serial = metadata.camera_serial
                        shot.shutter_angle = metadata.shutter_angle
                        shot.shutter_speed = metadata.shutter_speed
                        shot.shutter = metadata.shutter
                        shot.distance = metadata.distance
                        shot.nd_filter = metadata.nd_filter
                        shot.camera_tilt = metadata.camera_tilt
                        shot.camera_roll = metadata.camera_roll
                        shot.camera_clipname = metadata.camera_clipname

                        shot.cdl_sat = metadata.cdl_sat

                        shot.cdl_sop = metadata.cdl_sop
                        shots_linked += 1
            
            db.session.commit()
            
            flash(f'Added {library_added} new, updated {library_updated} metadata entries to library', 'success')
            if shots_linked > 0:
                flash(f'Linked metadata to {shots_linked} existing shot(s)', 'success')
            
            return redirect(url_for('index'))
    
    return render_template('import_metadata.html', project=project)


@app.route('/import/metadata/mapping')
def metadata_mapping():
    """Show column mapping interface"""
    import csv
    from io import StringIO
    import json
    
    project = get_active_project()
    filepath = request.args.get('filepath')
    
    if not filepath or not os.path.exists(filepath):
        flash('CSV file not found', 'error')
        return redirect(url_for('import_metadata'))
    
    # Read file and get headers + preview
    with open(filepath, 'rb') as f:
        raw_data = f.read()
    
    # Decode with proper encoding handling
    try:
        decoded = raw_data.decode("UTF-8")
    except UnicodeDecodeError:
        try:
            decoded = raw_data.decode("latin-1")
        except:
            decoded = raw_data.decode("cp1252", errors='ignore')
    
    # Check if this is an ALE file
    is_ale = filepath.lower().endswith('.ale')
    
    if is_ale:
        # Parse ALE format
        lines_ale = [line.rstrip() for line in decoded.split('\n')]
        
        # Find Column header
        column_line_idx = None
        for i, line in enumerate(lines_ale):
            if line.strip().upper() == 'COLUMN':
                column_line_idx = i + 1
                break
        
        if column_line_idx is None or column_line_idx >= len(lines_ale):
            flash('Invalid ALE file: Could not find Column header', 'error')
            return redirect(url_for('import_metadata'))
        
        # Get headers (tab-delimited)
        header_line = lines_ale[column_line_idx]
        app.logger.info(f"ALE Column line: {repr(header_line)}")
        split_result = header_line.split('\t')
        app.logger.info(f"Split by tab: {split_result}")
        csv_headers = [h.strip() for h in split_result]
        # Remove only trailing empty headers (from trailing tabs)
        while csv_headers and not csv_headers[-1]:
            csv_headers.pop()
        app.logger.info(f"Found {len(csv_headers)} headers: {csv_headers[:5]}")
        
        if not csv_headers:
            flash('Invalid ALE file: No headers found', 'error')
            return redirect(url_for('import_metadata'))
        
        # Find Data section
        data_line_idx = None
        for i, line in enumerate(lines_ale):
            if line.strip().upper() == 'DATA':
                data_line_idx = i + 1
                break
        
        if data_line_idx is None or data_line_idx >= len(lines_ale):
            flash('Invalid ALE file: Could not find Data section', 'error')
            return redirect(url_for('import_metadata'))
        
        # Get first 3 data rows for preview
        preview_rows = []
        rows_added = 0
        for i in range(data_line_idx, len(lines_ale)):
            line = lines_ale[i].strip()
            if line and rows_added < 3:
                row_data = line.split('\t')
                while len(row_data) < len(csv_headers):
                    row_data.append('')
                preview_rows.append(row_data[:len(csv_headers)])
                rows_added += 1
    else:
        # Parse CSV format
        cleaned = decoded.replace('\x00', '').replace('\r', '\n')
        if cleaned.startswith('\ufeff'):
            cleaned = cleaned[1:]
        if cleaned.startswith('ÿþ'):
            cleaned = cleaned[2:]
        
        stream = StringIO(cleaned, newline=None)
        reader = csv.DictReader(stream)
        csv_headers = [field.replace('ÿþ', '').replace('\ufeff', '').strip() for field in reader.fieldnames]
        
        # Get first 3 rows for preview
        stream.seek(0)
        next(stream)  # Skip header
        preview_rows = []
        for i, row in enumerate(csv.DictReader(stream, fieldnames=csv_headers)):
            if i == 0:  # Skip the duplicate header row
                continue
            if i > 3:
                break
            preview_rows.append([row.get(h, '') for h in csv_headers])
    
    # Get saved presets
    from models import MetadataPreset
    presets = MetadataPreset.query.filter_by(project_id=project.id).all()
    
    # Get last used mapping from session
    last_mapping = session.get('last_metadata_mapping', {})
    
    return render_template('metadata_mapping.html', 
                         csv_headers=csv_headers,
                         preview_rows=preview_rows,
                         filepath=filepath,
                         presets=presets,
                         last_mapping=last_mapping,
                         project=project)


@app.route('/import/metadata/preset/save', methods=['POST'])
def save_metadata_preset():
    """Save a metadata mapping preset (with overwrite support)"""
    from models import MetadataPreset
    
    try:
        project = get_active_project()
        data = request.json
        
        # Check if we're overwriting an existing preset
        overwrite_id = data.get('overwrite_id')
        
        if overwrite_id:
            # Update existing preset
            preset = MetadataPreset.query.get(overwrite_id)
            if preset and preset.project_id == project.id:
                preset.name = data['name']
                preset.mapping_json = json.dumps(data['mappings'])
                app.logger.info(f"Overwriting preset {preset.id}: {preset.name}")
            else:
                return jsonify({'success': False, 'error': 'Preset not found'}), 404
        else:
            # Create new preset
            preset = MetadataPreset(
                name=data['name'],
                mapping_json=json.dumps(data['mappings']),
                project_id=project.id
            )
            db.session.add(preset)
            app.logger.info(f"Creating new preset: {data['name']}")
        
        db.session.commit()
        
        return jsonify({'success': True, 'id': preset.id})
    except Exception as e:
        app.logger.error(f"Error saving preset: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/import/metadata/preset/<int:preset_id>')
def load_metadata_preset(preset_id):
    """Load a metadata mapping preset"""
    import json
    from models import MetadataPreset
    
    preset = MetadataPreset.query.get_or_404(preset_id)
    return jsonify({'mappings': json.loads(preset.mapping_json)})



@app.route('/import/metadata/preset/<int:preset_id>/delete', methods=['POST'])
def delete_metadata_preset(preset_id):
    """Delete a metadata mapping preset"""
    from models import MetadataPreset
    
    try:
        preset = MetadataPreset.query.get_or_404(preset_id)
        db.session.delete(preset)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"Error deleting preset: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/import/metadata/confirm', methods=['POST'])
def confirm_metadata_import():
    """Process metadata import with custom column mapping"""
    import csv
    from io import StringIO
    import os
    
    app.logger.info("="*80)
    app.logger.info("DEBUG: confirm_metadata_import STARTED")
    app.logger.info("="*80)
    
    project = get_active_project()
    filepath = request.form.get('filepath')
    
    if not filepath or not os.path.exists(filepath):
        flash('CSV file not found', 'error')
        return redirect(url_for('import_metadata'))
    
    # Read file
    with open(filepath, 'rb') as f:
        raw_data = f.read()
    
    # Decode with proper encoding handling
    try:
        decoded = raw_data.decode("UTF-8")
    except UnicodeDecodeError:
        try:
            decoded = raw_data.decode("latin-1")
        except:
            decoded = raw_data.decode("cp1252", errors='ignore')
    
    # Check if this is an ALE file
    is_ale = filepath.lower().endswith('.ale')
    
    # Build mapping dictionary from form data
    # Format: column_mapping[db_field] = csv_column
    column_mapping = {}
    
    # Get all form fields that start with "mapping_"
    for form_key in request.form:
        if form_key.startswith('mapping_'):
            db_field = form_key.replace('mapping_', '')
            csv_column = request.form.get(form_key)
            if csv_column:  # Only map if user selected a column (not "Skip")
                column_mapping[db_field] = csv_column
    
    # Save mapping to session for next time
    session['last_metadata_mapping'] = column_mapping
    
    # Parse data based on file type
    if is_ale:
        # Parse ALE format
        lines = [line.rstrip() for line in decoded.split('\n')]
        
        # Find Column line
        column_line_idx = None
        for i, line in enumerate(lines):
            if line.strip().upper() == 'COLUMN':
                column_line_idx = i + 1
                break
        
        if not column_line_idx or column_line_idx >= len(lines):
            flash('Invalid ALE file format', 'error')
            return redirect(url_for('import_metadata'))
        
        csv_headers = [h.strip() for h in lines[column_line_idx].split('\t') if h.strip()]
        
        # Find Data section
        data_line_idx = None
        for i, line in enumerate(lines):
            if line.strip().upper() == 'DATA':
                data_line_idx = i + 1
                break
        
        if not data_line_idx or data_line_idx >= len(lines):
            flash('Invalid ALE file format', 'error')
            return redirect(url_for('import_metadata'))
        
        # Create list of dict rows from ALE data
        csv_reader = []
        for i in range(data_line_idx, len(lines)):
            line = lines[i].strip()
            if line:
                row_data = line.split('\t')
                row_dict = {}
                for j, header in enumerate(csv_headers):
                    row_dict[header] = row_data[j] if j < len(row_data) else ''
                csv_reader.append(row_dict)
    else:
        # Parse CSV format
        cleaned = decoded.replace('\x00', '').replace('\r', '\n')
        if cleaned.startswith('\ufeff'):
            cleaned = cleaned[1:]
        if cleaned.startswith('ÿþ'):
            cleaned = cleaned[2:]
        
        stream = StringIO(cleaned, newline=None)
        reader = csv.DictReader(stream)
        csv_headers = [field.replace('ÿþ', '').replace('\ufeff', '').strip() for field in reader.fieldnames]
        
        # Process CSV with mapping
        stream.seek(0)
        next(stream)  # Skip header
        csv_reader = csv.DictReader(stream, fieldnames=csv_headers)
        next(csv_reader)  # Skip duplicate header
        csv_reader = list(csv_reader)
    
    library_added = 0
    library_updated = 0
    
    from models import CameraMetadata
    
    for row in csv_reader:
        # Get file name from the mapped column
        file_name_col = column_mapping.get('file_name')
        if not file_name_col:
            continue  # Skip if no file name column mapped
        
        clip_name = row.get(file_name_col, '').strip()
        if not clip_name:
            continue
        
        cam_roll = os.path.splitext(clip_name)[0]
        
        # Check if metadata exists
        metadata = CameraMetadata.query.filter_by(cam_roll=cam_roll).first()
        
        if not metadata:
            metadata = CameraMetadata(cam_roll=cam_roll)
            library_added += 1
        else:
            library_updated += 1
        
        # Apply mappings dynamically
        # column_mapping format: {db_field: csv_column}
        for db_field, csv_column in column_mapping.items():
            value = row.get(csv_column, '')
            setattr(metadata, db_field, value)
        
        # Special handling for shutter (combine angle + speed)
        if hasattr(metadata, 'shutter_angle') and hasattr(metadata, 'shutter_speed'):
            if metadata.shutter_angle and metadata.shutter_speed:
                metadata.shutter = f"{metadata.shutter_angle}° / {metadata.shutter_speed}s"
            elif metadata.shutter_angle:
                metadata.shutter = f"{metadata.shutter_angle}°"
            elif metadata.shutter_speed:
                metadata.shutter = f"{metadata.shutter_speed}s"
        
        db.session.add(metadata)
    
    db.session.commit()
    
    # Link to existing shots
    shots_linked = 0
    all_shots = Shot.query.filter_by(project_id=project.id).all()
    
    app.logger.info(f"DEBUG: Attempting to link metadata to {len(all_shots)} shots")
    
    for shot in all_shots:
        if shot.cam_roll:
            app.logger.info(f"DEBUG: Shot {shot.clip_name} has cam_roll: {shot.cam_roll}")
            metadata = find_metadata_by_cam_roll(shot.cam_roll)
            if metadata:
                app.logger.info(f"  -> Found metadata! Camera: {metadata.camera}, Lens: {metadata.lens}")
                # Copy all metadata fields to shot (hardcoded to ensure all fields are copied)
                shot.camera = metadata.camera
                shot.lens = metadata.lens
                shot.focal_length = metadata.focal_length
                shot.t_stop = metadata.t_stop
                shot.iso = metadata.iso
                shot.white_balance = metadata.white_balance
                shot.lut = metadata.lut
                shot.resolution = metadata.resolution
                shot.codec = metadata.codec
                shot.color_space = metadata.color_space
                shot.gamma = metadata.gamma
                shot.file_path = metadata.file_path
                shot.shot_frame_rate = metadata.shot_frame_rate
                shot.start_tc = metadata.start_tc
                shot.end_tc = metadata.end_tc
                # Don't overwrite start_frame if already set by user
                if not shot.start_frame or str(shot.start_frame) in ('0', ''):
                    shot.start_frame = metadata.start_frame
                shot.end_frame = metadata.end_frame
                shot.total_frames = metadata.total_frames
                shot.camera_manufacturer = metadata.camera_manufacturer
                shot.camera_serial = metadata.camera_serial
                shot.shutter_angle = metadata.shutter_angle
                shot.shutter_speed = metadata.shutter_speed
                shot.shutter = metadata.shutter
                shot.distance = metadata.distance
                shot.nd_filter = metadata.nd_filter
                shot.camera_tilt = metadata.camera_tilt
                shot.camera_roll = metadata.camera_roll
                shot.camera_clipname = metadata.camera_clipname

                shot.cdl_sat = metadata.cdl_sat

                shot.cdl_sop = metadata.cdl_sop
                
                shots_linked += 1
    
    db.session.commit()
    
    # Clean up temp file
    os.remove(filepath)
    
    flash(f'Added {library_added} new, updated {library_updated} metadata entries', 'success')
    if shots_linked > 0:
        flash(f'Linked metadata to {shots_linked} existing shot(s)', 'success')
    
    return redirect(url_for('index'))


@app.route('/shot/<int:shot_id>')
def shot_detail(shot_id):
    """View/edit individual shot"""
    shot = Shot.query.get_or_404(shot_id)
    vendors = Vendor.query.all()
    return render_template('shot_detail.html', shot=shot, vendors=vendors)


@app.route('/shot/<int:shot_id>/update', methods=['POST'])
def update_shot(shot_id):
    """Update shot details"""
    print(f"UPDATE ROUTE CALLED - Shot ID: {shot_id}")
    print(f"Form data: {dict(request.form)}")
    
    shot = Shot.query.get_or_404(shot_id)
    
    # Don't update vfx_code - it's derived from clip name and shouldn't change
    # shot.vfx_code = request.form.get('vfx_code')  # REMOVED
    # shot.vfx_element = request.form.get('vfx_element')  # Don't overwrite - derived from clip name
    shot.version = int(request.form.get('version', 1))
    shot.turnover_number = request.form.get('turnover_number')
    # shot.plate_type = request.form.get('plate_type')  # Don't overwrite - derived from clip name
    shot.vendor = request.form.get('vendor')
    shot.status = request.form.get('status')
    shot.head_handles = int(request.form.get('head_handles', 0))
    shot.tail_handles = int(request.form.get('tail_handles', 0))
    shot.crank_speed = float(request.form.get('crank_speed', 100.0))
    shot.scope_of_work = request.form.get('scope_of_work')
    shot.notes = request.form.get('notes')
    # shot.cam_roll = request.form.get('cam_roll')  # Don't overwrite - set from reel
    
    # Combine shutter for display
    if shot.shutter_angle and shot.shutter_speed:
        shot.shutter = f"{shot.shutter_angle}° / {shot.shutter_speed}s"
    elif shot.shutter_angle:
        shot.shutter = f"{shot.shutter_angle}°"
    elif shot.shutter_speed:
        shot.shutter = f"{shot.shutter_speed}s"
    else:
        shot.shutter = ''
    
    db.session.commit()
    flash('Shot updated successfully!', 'success')
    
    # Redirect back to where we came from
    if request.referrer and 'shot' in request.referrer:
        return redirect(url_for('shot_detail', shot_id=shot_id))
    else:
        return redirect(url_for('index'))




@app.route('/shot/<int:shot_id>/update/field', methods=['POST'])
def update_shot_field(shot_id):
    """Update a single field for a shot (for auto-save) - now handles JSON"""
    from flask import jsonify
    
    shot = Shot.query.get_or_404(shot_id)
    
    # Handle both form data and JSON
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form
    
    # Get the field name and value
    for field_name, value in data.items():
        if hasattr(shot, field_name):
            # Convert types as needed
            if field_name in ['head_handles', 'tail_handles', 'version', 'plate_number', 'start_frame']:
                value = int(value) if value else (1001 if field_name == 'start_frame' else 0)
            elif field_name == 'crank_speed':
                value = float(value) if value else 100.0
            elif field_name == 'pull_date':
                from datetime import datetime
                if value:
                    value = datetime.strptime(value, '%Y-%m-%d').date()
                else:
                    value = None
            
            setattr(shot, field_name, value)
    
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/vfx/<int:vfx_id>/timecode_data')
def get_vfx_timecode_data(vfx_id):
    """Return computed timecode data for all shots in a VFX code group"""
    vfx_code_obj = VFXCode.query.get_or_404(vfx_id)
    shots_data = []
    for shot in vfx_code_obj.shots:
        crank = shot.crank_speed or 100.0
        output_head = round((shot.head_handles or 0) / (crank / 100.0))
        output_tail = round((shot.tail_handles or 0) / (crank / 100.0))
        fr = shot.frame_range_display()
        shots_data.append({
            'id': shot.id,
            'tc_scan_in': shot.tc_scan_in() or 'N/A',
            'tc_scan_out': shot.tc_scan_out() or 'N/A',
            'total_scan': shot.total_source_frames(),
            'head_handles': shot.head_handles or 0,
            'tail_handles': shot.tail_handles or 0,
            'crank_speed': crank,
            'output_head': output_head,
            'output_tail': output_tail,
            'frame_range': {
                'head_start': fr['head_start'],
                'head_frames': fr['head_frames'],
                'head_end': fr['head_end'],
                'shot_start': fr['shot_start'],
                'shot_frames': fr['shot_frames'],
                'shot_end': fr['shot_end'],
                'tail_start': fr['tail_start'],
                'tail_frames': fr['tail_frames'],
                'tail_end': fr['tail_end'],
                'total_end': fr['total_end'],
            },
            'duration_frames': shot.duration_frames or 0,
            'detected_respeed': shot.detected_respeed or 0,
            'source_in': shot.source_in or '',
            'source_out': shot.source_out or '',
        })
    
    return jsonify({
        'success': True,
        'shots': shots_data,
    })


@app.route('/shots/delete', methods=['POST'])
def delete_shots():
    """Delete selected shots"""
    shot_ids = request.form.get('shot_ids', '')
    
    if not shot_ids:
        flash('No shots selected', 'error')
        return redirect(url_for('index'))
    
    shot_id_list = [int(id.strip()) for id in shot_ids.split(',') if id.strip()]
    
    # Delete shots
    Shot.query.filter(Shot.id.in_(shot_id_list)).delete(synchronize_session=False)
    db.session.commit()
    
    flash(f'{len(shot_id_list)} shot(s) deleted successfully', 'success')
    return redirect(url_for('index'))

@app.route('/delete-selected', methods=['POST'])
def delete_selected():
    """Delete selected VFX codes and/or individual shots"""
    vfx_ids = request.form.get('vfx_ids', '')
    shot_ids = request.form.get('shot_ids', '')
    
    
    deleted_count = 0
    
    # Delete entire VFX codes (and all their shots via cascade)
    if vfx_ids:
        vfx_id_list = [int(id.strip()) for id in vfx_ids.split(',') if id.strip()]
        # First delete all shots associated with these VFX codes
        Shot.query.filter(Shot.vfx_code_id.in_(vfx_id_list)).delete(synchronize_session=False)
        # Then delete the VFX codes
        VFXCode.query.filter(VFXCode.id.in_(vfx_id_list)).delete(synchronize_session=False)
        deleted_count += len(vfx_id_list)
    
    # Delete individual shots
    if shot_ids:
        shot_id_list = [int(id.strip()) for id in shot_ids.split(',') if id.strip()]
        Shot.query.filter(Shot.id.in_(shot_id_list)).delete(synchronize_session=False)
        deleted_count += len(shot_id_list)
    
    db.session.commit()
    
    flash(f'Deleted {deleted_count} item(s) successfully', 'success')
    return redirect(url_for('index'))


@app.route('/shot/<int:shot_id>/pdf')
def export_shot_pdf(shot_id):
    """Export shot sheet as PDF"""
    shot = Shot.query.get_or_404(shot_id)
    
    pdf_bytes = generate_shot_pdf(shot)
    pdf_buffer = BytesIO(pdf_bytes)
    
    # Use VFX code in filename if available
    filename = f"{shot.vfx_code or shot.clip_name}_shot_sheet.pdf"
    
    # Return PDF directly for JSON requests, file download for form requests
    if request.is_json:
        pdf_buffer.seek(0)
        return pdf_buffer.read(), 200, {'Content-Type': 'application/pdf'}
    else:
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )




@app.route('/export/vfx_group/<vfx_code>/pdf')
def export_vfx_group_pdf(vfx_code):
    """Export all plates for a VFX code as one PDF"""
    project = get_active_project()
    shots = Shot.query.filter_by(project_id=project.id, vfx_code=vfx_code).order_by(Shot.plate_type, Shot.vfx_element).all()
    
    if not shots:
        flash('No shots found for this VFX code', 'error')
        return redirect(url_for('index'))
    
    # Generate PDF with all plates
    pdf_bytes = generate_selected_shots_pdf_playwright(shots, project, vfx_code)
    pdf_buffer = BytesIO(pdf_bytes)
    
    filename = f"{vfx_code}_all_plates.pdf"
    
    # Return PDF directly for JSON requests, file download for form requests
    if request.is_json:
        pdf_buffer.seek(0)
        return pdf_buffer.read(), 200, {'Content-Type': 'application/pdf'}
    else:
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )

@app.route('/export/vfx_group/<vfx_code>/csv')
def export_vfx_group_csv(vfx_code):
    """Export all plates for a VFX code as CSV"""
    project = get_active_project()
    shots = Shot.query.filter_by(project_id=project.id, vfx_code=vfx_code).order_by(Shot.plate_type, Shot.vfx_element).all()
    
    if not shots:
        flash('No shots found for this VFX code', 'error')
        return redirect(url_for('index'))
    
    # Generate CSV
    import csv
    from io import StringIO
    
    output = StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        'VFX Code', 'Plate Type', 'Element', 'Version', 'Clip Name',
        'Source In', 'Source Out', 'TC Scan In', 'TC Scan Out',
        'Head Handles', 'Tail Handles', 'Crank Speed',
        'FPS',
        'Vendor', 'Status', 'Turnover #', 'Notes'
    ])
    
    # Data rows
    for shot in shots:
        writer.writerow([
            shot.vfx_code,
            shot.plate_type or '',
            shot.vfx_element or '',
            shot.version,
            shot.clip_name,
            shot.source_in or '',
            shot.source_out or '',
            shot.tc_scan_in() or '',
            shot.tc_scan_out() or '',
            shot.head_handles or 0,
            shot.tail_handles or 0,
            shot.crank_speed or 100,
            shot.shot_frame_rate or shot.fps or '',
            shot.vendor or '',
            shot.status,
            shot.turnover_number or '',
            shot.notes or ''
        ])
    
    # Convert to bytes for download
    csv_data = output.getvalue()
    output.close()
    
    return send_file(
        BytesIO(csv_data.encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f"{vfx_code}_vfx_data.csv"
    )




@app.route('/export/vfx_group/<vfx_code>/metadata_csv')
def export_vfx_group_metadata_csv(vfx_code):
    """Export metadata for all plates in a VFX code as CSV"""
    project = get_active_project()
    shots = Shot.query.filter_by(project_id=project.id, vfx_code=vfx_code).order_by(Shot.plate_type, Shot.vfx_element).all()
    
    if not shots:
        flash('No shots found for this VFX code', 'error')
        return redirect(url_for('index'))
    
    # Generate metadata CSV
    import csv
    from io import StringIO
    
    output = StringIO()
    writer = csv.writer(output)
    
    # Metadata header
    writer.writerow([
        'VFX Code', 'Plate Type', 'Clip Name', 'Camera Type', 'Camera Manufacturer', 
        'Camera Serial', 'Lens Type', 'Focal Length', 'Aperture', 'Distance', 'ISO',
        'Shutter Angle', 'Shutter Speed', 'White Balance', 'ND Filter', 
        'Camera Tilt', 'Camera Roll', 'LUT', 'Resolution', 'Codec', 
        'Color Space', 'Gamma', 'Frame Rate', 'Start TC', 'End TC',
        'Start Frame', 'End Frame', 'Total Frames'
    ])
    
    # Metadata rows
    for shot in shots:
        writer.writerow([
            shot.vfx_code,
            shot.plate_type or '',
            shot.clip_name,
            shot.camera or '',
            shot.camera_manufacturer or '',
            shot.camera_serial or '',
            shot.lens or '',
            shot.focal_length or '',
            shot.t_stop or '',
            shot.distance or '',
            shot.iso or '',
            shot.shutter_angle or '',
            shot.shutter_speed or '',
            shot.white_balance or '',
            shot.nd_filter or '',
            shot.camera_tilt or '',
            shot.camera_roll or '',
            shot.lut or '',
            shot.resolution or '',
            shot.codec or '',
            shot.color_space or '',
            shot.gamma or '',
            shot.shot_frame_rate or '',
            shot.start_tc or '',
            shot.end_tc or '',
            shot.start_frame or '',
            shot.end_frame or '',
            shot.total_frames or ''
        ])
    
    # Convert to bytes for download
    csv_data = output.getvalue()
    output.close()
    
    return send_file(
        BytesIO(csv_data.encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f"{vfx_code}_metadata.csv"
    )

@app.route('/shot/<int:shot_id>/upload_reference', methods=['POST'])
def upload_reference_image(shot_id):
    """Upload reference image for a shot"""
    shot = Shot.query.get_or_404(shot_id)
    
    if 'reference_image' not in request.files:
        flash('No file provided', 'error')
        return redirect(url_for('index'))
    
    file = request.files['reference_image']
    
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('index'))
    
    if file:
        # Create uploads directory if it doesn't exist
        import os
        # Save to database folder, not app folder
        upload_dir = get_reference_images_folder()
        
        # Save with shot ID in filename
        from werkzeug.utils import secure_filename
        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        new_filename = f"shot_{shot_id}_ref.{ext}"
        filepath = os.path.join(upload_dir, new_filename)
        
        file.save(filepath)
        
        # Store relative path in database
        shot.reference_image = f"reference_images/{new_filename}"
        db.session.commit()
        
        flash('Reference image uploaded!', 'success')
    
    return redirect(url_for('index'))

@app.route('/shot/<int:shot_id>/delete_reference', methods=['POST'])
def delete_reference_image(shot_id):
    """Delete reference image for a shot"""
    shot = Shot.query.get_or_404(shot_id)
    
    if shot.reference_image:
        # Delete file
        import os
        filepath = os.path.join('static', shot.reference_image)
        if os.path.exists(filepath):
            os.remove(filepath)
        
        shot.reference_image = None
        db.session.commit()
        flash('Reference image deleted', 'success')
    
    return redirect(url_for('index'))

@app.route('/export/edl', methods=['GET', 'POST'])
def export_edl():
    """Export all shots as EDL - only exports shots with vfx_code (filters orphaned shots)"""
    project = get_active_project()
    shots = Shot.query.filter_by(project_id=project.id).filter(Shot.vfx_code_id != None).order_by(Shot.event_number).all()
    
    if not shots:
        flash('No shots to export', 'error')
        return redirect(url_for('index'))
    
    edl_content = generate_pull_edl(shots, title=f"{project.name.upper().replace(' ', '_')}_PULL")
    
    edl_file = BytesIO()
    edl_file.write(edl_content.encode('utf-8'))
    edl_file.seek(0)
    
    # Use first VFX code or project name for filename
    first_vfx_code = next((s.vfx_code for s in shots if s.vfx_code), None)
    filename = f'{first_vfx_code or project.name.lower().replace(" ", "_")}_pull_list.edl'
    
    # Return plain text for JSON requests (Electron), file download for form requests
    if request.is_json:
        return edl_content, 200, {'Content-Type': 'text/plain'}
    else:
        return send_file(
            edl_file,
            mimetype='text/plain',
            as_attachment=True,
            download_name=filename
        )


@app.route('/export/edl/selected', methods=['POST'])
def export_edl_selected():
    """Export selected shots as EDL - filters to latest version of each plate"""
    import sys
    sys.stdout.flush()
    sys.stderr.write(f"\n\n=== EDL FUNCTION CALLED ===\n")
    sys.stderr.write(f"is_json: {request.is_json}\n")
    sys.stderr.write(f"data: {request.data}\n")
    sys.stderr.flush()
    
    # Handle both form data (old) and JSON (new from Electron)
    if request.is_json:
        data = request.json
        shot_ids = data.get('shot_ids', '')
        vfx_code_ids = data.get('vfx_code_ids', '')  # NEW: Accept VFX code IDs
        print(f"\n=== EDL EXPORT DEBUG ===")
        print(f"Received shot_ids: {shot_ids}")
        print(f"Received vfx_code_ids: {vfx_code_ids}")
        print(f"========================\n")
    else:
        shot_ids = request.form.get('shot_ids', '')
        vfx_code_ids = request.form.get('vfx_code_ids', '')
    
    all_shots = []
    
    # Get shots from VFX code IDs (if provided)
    if vfx_code_ids:
        vfx_id_list = [int(id.strip()) for id in vfx_code_ids.split(',') if id.strip()]
        print(f"Getting shots from {len(vfx_id_list)} VFX codes: {vfx_id_list}")
        for vfx_id in vfx_id_list:
            vfx_code = VFXCode.query.get(vfx_id)
            if vfx_code:
                print(f"  VFX {vfx_code.vfx_code}: {len(vfx_code.shots)} shots")
                all_shots.extend(vfx_code.shots)
    
    # Get individual shots (if provided)
    if shot_ids:
        shot_id_list = [int(id.strip()) for id in shot_ids.split(',') if id.strip()]
        individual_shots = Shot.query.filter(Shot.id.in_(shot_id_list)).all()
        # Add shots that aren't already in the list
        for shot in individual_shots:
            if shot not in all_shots:
                all_shots.append(shot)
    
    if not all_shots:
        flash('No shots selected', 'error')
        return redirect(url_for('index'))
    
    print(f"Total shots collected: {len(all_shots)}")
    for shot in all_shots:
        print(f"  - ID {shot.id}: {shot.clip_name} (v{shot.version})")
    
    # Filter to latest version of each plate type within each VFX code
    latest_shots = {}
    for shot in all_shots:
        # Use vfx_code_id (foreign key) instead of vfx_code (string which might be None)
        key = (shot.vfx_code_id, shot.plate_type, shot.vfx_element)
        sys.stderr.write(f"Shot {shot.id}: vfx_code_id={shot.vfx_code_id}, key={key}, version={shot.version}\n")
        if key not in latest_shots or shot.version > latest_shots[key].version:
            latest_shots[key] = shot
            sys.stderr.write(f"  -> KEEPING this shot\n")
        else:
            sys.stderr.write(f"  -> SKIPPING (already have v{latest_shots[key].version})\n")
    
    shots = sorted(latest_shots.values(), key=lambda s: s.event_number)
    print(f"After filtering to latest versions: {len(shots)} shots")
    
    if not shots:
        flash('No valid shots selected', 'error')
        return redirect(url_for('index'))
    
    # DEBUG: Check vfx_code values
    for s in shots:
        vfx_obj = s.vfx_code_obj if hasattr(s, 'vfx_code_obj') else None
        print(f"  Shot {s.id}: clip_name={s.clip_name}")
        print(f"    vfx_code (string): {s.vfx_code}")
        print(f"    vfx_code_id: {s.vfx_code_id}")
        print(f"    vfx_code_obj: {vfx_obj}")
        if vfx_obj:
            print(f"    vfx_code_obj.vfx_code: {vfx_obj.vfx_code}")
    
    # Smart filename based on selection
    if len(shots) == 1:
        # Single shot: use clip name
        filename = f'{shots[0].clip_name}.edl'
        title = shots[0].clip_name.upper()
    else:
        # Multiple shots: check if all from same VFX code
        vfx_codes = set()
        for s in shots:
            # Use vfx_code_obj.vfx_code if available, otherwise vfx_code string
            if hasattr(s, 'vfx_code_obj') and s.vfx_code_obj:
                vfx_codes.add(s.vfx_code_obj.vfx_code)
                print(f"  Adding vfx_code from obj: {s.vfx_code_obj.vfx_code}")
            elif s.vfx_code:
                vfx_codes.add(s.vfx_code)
                print(f"  Adding vfx_code from string: {s.vfx_code}")
        
        
        if len(vfx_codes) == 1:
            # All from same VFX code
            vfx_code = list(vfx_codes)[0]
            filename = f'{vfx_code}_pull_list.edl'
            title = f'{vfx_code}_PULL'
        else:
            # Multiple VFX codes
            filename = 'selected_shots_pull_list.edl'
            title = 'SELECTED_SHOTS_PULL'
    
    edl_content = generate_pull_edl(shots, title=title)
    
    edl_file = BytesIO()
    edl_file.write(edl_content.encode('utf-8'))
    edl_file.seek(0)
    
    # Return plain text for JSON requests (Electron), file download for form requests
    if request.is_json:
        return edl_content, 200, {'Content-Type': 'text/plain'}
    else:
        return send_file(
            edl_file,
            mimetype='text/plain',
            as_attachment=True,
            download_name=filename
        )




def generate_pull_ale(shots, fps=24):
    """Generate an Avid ALE file for pulling VFX plates.
    Format:
        Heading
        FIELD_DELIM\tTABS
        VIDEO_FORMAT\t1080
        AUDIO_FORMAT\t48khz
        FPS\t{fps}
        
        Column
        Name\tStart\tEnd\tDuration
        
        Data
        {vfx_code}\t{tc_scan_in}\t{tc_scan_out}\t{duration}
    """
    from models import frames_to_timecode
    
    lines = []
    lines.append("Heading")
    lines.append("FIELD_DELIM\tTABS")
    lines.append("VIDEO_FORMAT\t1080")
    lines.append("AUDIO_FORMAT\t48khz")
    lines.append(f"FPS\t{int(fps)}")
    lines.append("")
    lines.append("Column")
    lines.append("Name\tStart\tEnd\tDuration\tTape")
    lines.append("")
    lines.append("Data")
    
    for shot in shots:
        # Get VFX code name (INV_TST_020_SRC01_V001 style)
        if hasattr(shot, 'vfx_code_obj') and shot.vfx_code_obj:
            base_code = shot.vfx_code_obj.vfx_code
        else:
            base_code = shot.vfx_code or shot.clip_name
        
        # Use clip_name directly if available - it already has proper format (INV_TST_010_SRC01_V001)
        name = shot.clip_name or base_code
        
        # TC Scan In / Out (with handles applied) - these are methods
        try:
            tc_in = shot.tc_scan_in() if callable(shot.tc_scan_in) else shot.tc_scan_in
        except:
            tc_in = shot.tc_cut_in or ""
        try:
            tc_out = shot.tc_scan_out() if callable(shot.tc_scan_out) else shot.tc_scan_out
        except:
            tc_out = shot.tc_cut_out or ""
        
        # Duration = total scan frames as timecode
        head = shot.head_handles or 0
        tail = shot.tail_handles or 0
        duration_frames = (shot.duration_frames or 0) + head + tail
        try:
            duration_tc = frames_to_timecode(duration_frames, fps)
        except:
            duration_tc = "00:00:00:00"
        
        meta = find_metadata_by_cam_roll(shot.cam_roll) if shot.cam_roll else None
        tape = meta.cam_roll if meta else (shot.reel or shot.cam_roll or "")
        lines.append(f"{name}\t{tc_in}\t{tc_out}\t{duration_tc}\t{tape}")
    
    return "\n".join(lines) + "\n"


@app.route('/export/ale/selected', methods=['POST'])
def export_ale_selected():
    """Export selected shots as Avid ALE - for dragging onto masterclips in Avid"""
    import sys
    
    # Handle both form and JSON
    if request.is_json:
        data = request.json
        shot_ids = data.get('shot_ids', '')
        vfx_code_ids = data.get('vfx_code_ids', '')
    else:
        shot_ids = request.form.get('shot_ids', '')
        vfx_code_ids = request.form.get('vfx_code_ids', '')
    
    all_shots = []
    
    # Get shots from VFX code IDs
    if vfx_code_ids:
        vfx_id_list = [int(id.strip()) for id in vfx_code_ids.split(',') if id.strip()]
        for vfx_id in vfx_id_list:
            vfx_code = VFXCode.query.get(vfx_id)
            if vfx_code:
                all_shots.extend(vfx_code.shots)
    
    # Get individual shots
    if shot_ids:
        shot_id_list = [int(id.strip()) for id in shot_ids.split(',') if id.strip()]
        individual_shots = Shot.query.filter(Shot.id.in_(shot_id_list)).all()
        for shot in individual_shots:
            if shot not in all_shots:
                all_shots.append(shot)
    
    if not all_shots:
        flash('No shots selected', 'error')
        return redirect(url_for('index'))
    
    # Filter to latest version of each plate type within each VFX code
    latest_shots = {}
    for shot in all_shots:
        key = (shot.vfx_code_id, shot.plate_type, shot.vfx_element)
        if key not in latest_shots or shot.version > latest_shots[key].version:
            latest_shots[key] = shot
    
    shots = sorted(latest_shots.values(), key=lambda s: s.event_number)
    
    if not shots:
        flash('No valid shots selected', 'error')
        return redirect(url_for('index'))
    
    # Get project FPS
    project = get_active_project()
    fps = project.fps if project else 24
    
    # Smart filename
    if len(shots) == 1:
        filename = f'{shots[0].clip_name}.ale'
    else:
        vfx_codes = set()
        for s in shots:
            if hasattr(s, 'vfx_code_obj') and s.vfx_code_obj:
                vfx_codes.add(s.vfx_code_obj.vfx_code)
            elif s.vfx_code:
                vfx_codes.add(s.vfx_code)
        
        if len(vfx_codes) == 1:
            filename = f'{list(vfx_codes)[0]}_pull_list.ale'
        else:
            filename = 'selected_shots_pull_list.ale'
    
    ale_content = generate_pull_ale(shots, fps=fps)
    
    ale_file = BytesIO()
    ale_file.write(ale_content.encode('utf-8'))
    ale_file.seek(0)
    
    if request.is_json:
        return ale_content, 200, {'Content-Type': 'text/plain'}
    else:
        return send_file(
            ale_file,
            mimetype='text/plain',
            as_attachment=True,
            download_name=filename
        )


@app.route('/export/vfx_csv/selected', methods=['POST'])
def export_vfx_csv_selected():
    """Export selected VFX codes and/or individual shots to CSV with shot details"""
    from flask import make_response
    import csv
    from io import StringIO
    
    # Handle both form and JSON
    if request.is_json:
        data = request.json
        vfx_code_ids = data.get('vfx_code_ids', '')
        shot_ids = data.get('shot_ids', '')
        export_mode = data.get('export_mode', 'single')
    else:
        vfx_code_ids = request.form.get('vfx_code_ids', '')
        shot_ids = request.form.get('shot_ids', '')
        export_mode = 'single'
    
    # Get shots from VFX codes
    shots = []
    if vfx_code_ids:
        vfx_ids = [int(id) for id in vfx_code_ids.split(',')]
        vfx_codes = VFXCode.query.filter(VFXCode.id.in_(vfx_ids)).all()
        for vfx_code in vfx_codes:
            shots.extend(vfx_code.shots)
    
    # Get individual shots
    if shot_ids:
        shot_id_list = [int(id) for id in shot_ids.split(',')]
        individual_shots = Shot.query.filter(Shot.id.in_(shot_id_list)).all()
        # Add shots that aren't already in the list
        for shot in individual_shots:
            if shot not in shots:
                shots.append(shot)
    
    if not shots:
        flash('No shots selected', 'error')
        return redirect(url_for('index'))
    
    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'VFX Code', 'Clip Name', 'Plate Type', 'Plate #', 'Version', 
        'Status', 'Turnover #', 'Turnover Date',
        'Vendor 1', 'Vendor 2', 'Vendor 3', 'Vendor 4',
        'Frame Range', 'Starting Frame', 'Head Handles', 'Tail Handles',
        'Crank Speed', 'FPS', 'TC Cut In', 'TC Cut Out', 'TC Scan In', 'TC Scan Out',
        'Length (frames)', 'Total Scan (frames)',
        'Scope of Work', 'VFX Editorial Note'
    ])
    
    # Write data for each shot
    for shot in shots:
        vfx_code = shot.vfx_code_obj  # Get the VFXCode object
        frame_range = shot.frame_range_display()
        frame_range_str = f"{frame_range['head_start']}-{frame_range['total_end']}"
        
        writer.writerow([
            vfx_code.vfx_code if vfx_code else shot.vfx_code,
            shot.clip_name,
            shot.plate_type or '',
            shot.plate_number or '',
            f"v{shot.version}" if shot.version else '',
            vfx_code.shot_status if vfx_code else '',
            vfx_code.turnover_number if vfx_code else '',
            vfx_code.turnover_date.strftime('%Y-%m-%d') if vfx_code and vfx_code.turnover_date else '',
            vfx_code.vendor_1 if vfx_code else '',
            vfx_code.vendor_2 if vfx_code else '',
            vfx_code.vendor_3 if vfx_code else '',
            vfx_code.vendor_4 if vfx_code else '',
            frame_range_str,
            shot.start_frame or 1001,
            shot.head_handles or 0,
            shot.tail_handles or 0,
            f"{shot.crank_speed}%" if shot.crank_speed else '100%',
            shot.shot_frame_rate or shot.fps or '',
            shot.source_in or '',
            shot.source_out or '',
            shot.tc_scan_in() or '',
            shot.tc_scan_out() or '',
            shot.duration_frames or 0,
            shot.total_source_frames() or 0,
            vfx_code.scope_of_work if vfx_code else '',
            vfx_code.vfx_editorial_note if vfx_code else ''
        ])
    
    # Create response
    output.seek(0)
    csv_content = output.getvalue()
    
    # Handle split mode - create separate CSV for each VFX code
    if export_mode == 'split' and request.is_json:
        # Group shots by VFX code
        shots_by_vfx = {}
        for shot in shots:
            vfx_key = shot.vfx_code_obj.vfx_code if shot.vfx_code_obj else shot.vfx_code or 'unknown'
            if vfx_key not in shots_by_vfx:
                shots_by_vfx[vfx_key] = []
            shots_by_vfx[vfx_key].append(shot)
        
        # Generate separate CSV for each VFX code
        csvs = {}
        for vfx_code, vfx_shots in shots_by_vfx.items():
            vfx_output = StringIO()
            vfx_writer = csv.writer(vfx_output)
            
            # Write header
            vfx_writer.writerow([
                'VFX Code', 'Clip Name', 'Plate Type', 'Plate #', 'Version', 
                'Status', 'Turnover #', 'Turnover Date',
                'Vendor 1', 'Vendor 2', 'Vendor 3', 'Vendor 4',
                'Frame Range', 'Starting Frame', 'Head Handles', 'Tail Handles',
                'Crank Speed', 'TC Cut In', 'TC Cut Out', 'TC Scan In', 'TC Scan Out',
                'Length (frames)', 'Total Scan (frames)',
                'Scope of Work', 'VFX Editorial Note'
            ])
            
            # Write data
            for shot in vfx_shots:
                vfx_code_obj = shot.vfx_code_obj
                frame_range = shot.frame_range_display()
                frame_range_str = f"{frame_range['head_start']}-{frame_range['total_end']}"
                
                vfx_writer.writerow([
                    vfx_code_obj.vfx_code if vfx_code_obj else shot.vfx_code,
                    shot.clip_name,
                    shot.plate_type or '',
                    shot.plate_number or '',
                    f"v{shot.version}" if shot.version else '',
                    vfx_code_obj.shot_status if vfx_code_obj else '',
                    vfx_code_obj.turnover_number if vfx_code_obj else '',
                    vfx_code_obj.turnover_date.strftime('%Y-%m-%d') if vfx_code_obj and vfx_code_obj.turnover_date else '',
                    vfx_code_obj.vendor_1 if vfx_code_obj else '',
                    vfx_code_obj.vendor_2 if vfx_code_obj else '',
                    vfx_code_obj.vendor_3 if vfx_code_obj else '',
                    vfx_code_obj.vendor_4 if vfx_code_obj else '',
                    frame_range_str,
                    shot.start_frame or 1001,
                    shot.head_handles or 0,
                    shot.tail_handles or 0,
                    f"{shot.crank_speed}%" if shot.crank_speed else '100%',
                    shot.source_in or '',
                    shot.source_out or '',
                    shot.tc_scan_in() or '',
                    shot.tc_scan_out() or '',
                    shot.duration_frames or 0,
                    shot.total_source_frames() or 0,
                    vfx_code_obj.scope_of_work if vfx_code_obj else '',
                    vfx_code_obj.vfx_editorial_note if vfx_code_obj else ''
                ])
            
            vfx_output.seek(0)
            csvs[f'{vfx_code}_vfx_data.csv'] = vfx_output.getvalue()
        
        return jsonify({'csvs': csvs})
    
    # Return plain CSV for JSON requests (Electron), attachment for form requests
    if request.is_json:
        return csv_content, 200, {'Content-Type': 'text/csv'}
    else:
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        
        # Generate filename
        if len(shots) == 1:
            filename = f"{shots[0].clip_name}_vfx_data.csv"
        else:
            # Check if all shots are from same VFX code
            vfx_codes = set()
            for shot in shots:
                if shot.vfx_code_obj:
                    vfx_codes.add(shot.vfx_code_obj.vfx_code)
                elif shot.vfx_code:
                    vfx_codes.add(shot.vfx_code)
            
            if len(vfx_codes) == 1:
                # All from same VFX code
                filename = f"{list(vfx_codes)[0]}_vfx_data.csv"
            else:
                # Multiple VFX codes
                filename = f"vfx_data_{len(shots)}_shots.csv"
        
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response


@app.route('/export/pdf/selected', methods=['POST'])
def export_pdf_selected():
    """Export selected shots as PDF"""
    # Handle both form data and JSON
    if request.is_json:
        data = request.json
        shot_ids = data.get('shot_ids', '')
        vfx_code_ids = data.get('vfx_code_ids', '')
        export_mode = data.get('export_mode', 'single')  # 'single', 'combined', or 'split'
    else:
        shot_ids = request.form.get('shot_ids', '')
        vfx_code_ids = request.form.get('vfx_code_ids', '')
        export_mode = request.form.get('export_mode', 'single')
    
    all_shots = []
    
    # Get shots from VFX code IDs (if provided)
    if vfx_code_ids:
        vfx_id_list = [int(id.strip()) for id in vfx_code_ids.split(',') if id.strip()]
        for vfx_id in vfx_id_list:
            vfx_code = VFXCode.query.get(vfx_id)
            if vfx_code:
                all_shots.extend(vfx_code.shots)
    
    # Get individual shots (if provided)
    if shot_ids:
        shot_id_list = [int(id.strip()) for id in shot_ids.split(',') if id.strip()]
        individual_shots = Shot.query.filter(Shot.id.in_(shot_id_list)).all()
        for shot in individual_shots:
            if shot not in all_shots:
                all_shots.append(shot)
    
    if not all_shots:
        flash('No shots selected', 'error')
        return redirect(url_for('index'))
    
    # Filter to latest version of each plate type within each VFX code
    latest_shots = {}
    for shot in all_shots:
        # Use vfx_code_id (foreign key) instead of vfx_code (string which might be None)
        key = (shot.vfx_code_id, shot.plate_type, shot.vfx_element)
        sys.stderr.write(f"Shot {shot.id}: vfx_code_id={shot.vfx_code_id}, key={key}, version={shot.version}\n")
        if key not in latest_shots or shot.version > latest_shots[key].version:
            latest_shots[key] = shot
            sys.stderr.write(f"  -> KEEPING this shot\n")
        else:
            sys.stderr.write(f"  -> SKIPPING (already have v{latest_shots[key].version})\n")
    
    shots = sorted(latest_shots.values(), key=lambda s: (s.vfx_code_obj.vfx_code if s.vfx_code_obj else s.vfx_code or '', s.plate_type or '', s.vfx_element or ''))
    
    if not shots:
        flash('No valid shots selected', 'error')
        return redirect(url_for('index'))
    
    # Smart filename based on selection
    if len(shots) == 1:
        filename = f'{shots[0].clip_name}.pdf'
        title = shots[0].clip_name
    else:
        vfx_codes = set()
        for s in shots:
            if hasattr(s, 'vfx_code_obj') and s.vfx_code_obj:
                vfx_codes.add(s.vfx_code_obj.vfx_code)
            elif s.vfx_code:
                vfx_codes.add(s.vfx_code)
        
        if len(vfx_codes) == 1:
            vfx_code = list(vfx_codes)[0]
            filename = f'{vfx_code}_all_plates.pdf'
            title = vfx_code
        else:
            filename = 'selected_shots.pdf'
            title = 'Selected Shots'
    
    # Generate PDF(s) based on export mode
    project = get_active_project()
    
    if export_mode == 'split' and len(vfx_codes) > 1:
        # SPLIT MODE: Create separate PDF for each VFX code
        import base64
        
        # Group shots by VFX code
        shots_by_vfx = {}
        for shot in shots:
            vfx_key = shot.vfx_code_obj.vfx_code if shot.vfx_code_obj else shot.vfx_code or 'unknown'
            if vfx_key not in shots_by_vfx:
                shots_by_vfx[vfx_key] = []
            shots_by_vfx[vfx_key].append(shot)
        
        # Generate PDF for each VFX code and encode as base64
        pdfs = {}
        for vfx_code, vfx_shots in shots_by_vfx.items():
            pdf_bytes = generate_selected_shots_pdf_playwright(vfx_shots, project, vfx_code)
            pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
            pdfs[f'{vfx_code}_plates.pdf'] = pdf_base64
        
        # Return JSON with all PDFs
        return jsonify({'pdfs': pdfs})
    else:
        # SINGLE/COMBINED MODE: One PDF with all shots
        pdf_bytes = generate_selected_shots_pdf_playwright(shots, project, title)
        pdf_buffer = BytesIO(pdf_bytes)
        
        # Return PDF directly for JSON requests, file download for form requests
        if request.is_json:
            pdf_buffer.seek(0)
            return pdf_buffer.read(), 200, {'Content-Type': 'application/pdf'}
        else:
            return send_file(
                pdf_buffer,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=filename
            )


@app.route('/export/edl/status/<status>')
def export_edl_by_status(status):
    """Export shots by status as EDL"""
    project = get_active_project()
    shots = Shot.query.filter_by(project_id=project.id, status=status).order_by(Shot.event_number).all()
    
    if not shots:
        flash(f'No shots with status "{status}" to export', 'error')
        return redirect(url_for('index'))
    
    edl_content = generate_pull_edl(shots, title=f"VFX_{status.upper().replace(' ', '_')}")
    
    edl_file = BytesIO()
    edl_file.write(edl_content.encode('utf-8'))
    edl_file.seek(0)
    
    # Use first VFX code for filename
    first_vfx_code = next((s.vfx_code for s in shots if s.vfx_code), None)
    filename = f'{first_vfx_code or status.lower().replace(" ", "_")}_{status.lower().replace(" ", "_")}.edl'
    
    # Return plain text for JSON requests (Electron), file download for form requests
    if request.is_json:
        return edl_content, 200, {'Content-Type': 'text/plain'}
    else:
        return send_file(
            edl_file,
            mimetype='text/plain',
            as_attachment=True,
            download_name=filename
        )


@app.route('/export/report')
def export_report():
    """Export VFX shot report as text file"""
    project = get_active_project()
    shots = Shot.query.filter_by(project_id=project.id).order_by(Shot.event_number).all()
    
    if not shots:
        flash('No shots to export', 'error')
        return redirect(url_for('index'))
    
    report_content = generate_vfx_report(shots)
    
    report_file = BytesIO()
    report_file.write(report_content.encode('utf-8'))
    report_file.seek(0)
    
    # Use first VFX code for filename
    first_vfx_code = next((s.vfx_code for s in shots if s.vfx_code), None)
    filename = f'{first_vfx_code or project.name.lower().replace(" ", "_")}_report.txt'
    
    return send_file(
        report_file,
        mimetype='text/plain',
        as_attachment=True,
        download_name=filename
    )




@app.route('/shot/<int:shot_id>/metadata')
def shot_metadata(shot_id):
    """View/edit shot metadata"""
    shot = Shot.query.get_or_404(shot_id)
    return render_template('metadata.html', shot=shot)


@app.route('/shot/<int:shot_id>/metadata/update', methods=['POST'])
def update_metadata(shot_id):
    """Update shot metadata"""
    shot = Shot.query.get_or_404(shot_id)
    
    # Update all metadata fields
    shot.camera = request.form.get('camera')
    shot.camera_manufacturer = request.form.get('camera_manufacturer')
    shot.camera_serial = request.form.get('camera_serial')
    shot.lens = request.form.get('lens')
    shot.focal_length = request.form.get('focal_length')
    shot.t_stop = request.form.get('t_stop')
    shot.distance = request.form.get('distance')
    shot.iso = request.form.get('iso')
    shot.shutter_angle = request.form.get('shutter_angle')
    shot.shutter_speed = request.form.get('shutter_speed')
    shot.white_balance = request.form.get('white_balance')
    shot.nd_filter = request.form.get('nd_filter')
    shot.camera_tilt = request.form.get('camera_tilt')
    shot.camera_roll = request.form.get('camera_roll')
    shot.lut = request.form.get('lut')
    shot.resolution = request.form.get('resolution')
    shot.codec = request.form.get('codec')
    shot.color_space = request.form.get('color_space')
    shot.gamma = request.form.get('gamma')
    shot.shot_frame_rate = request.form.get('shot_frame_rate')
    shot.start_tc = request.form.get('start_tc')
    shot.end_tc = request.form.get('end_tc')
    shot.start_frame = request.form.get('start_frame')
    shot.end_frame = request.form.get('end_frame')
    shot.total_frames = request.form.get('total_frames')
    shot.camera_clipname = request.form.get('camera_clipname')
    shot.cdl_sat = request.form.get('cdl_sat')
    shot.cdl_sop = request.form.get('cdl_sop')
    
    # Combine shutter for display
    if shot.shutter_angle and shot.shutter_speed:
        shot.shutter = f"{shot.shutter_angle}° / {shot.shutter_speed}s"
    elif shot.shutter_angle:
        shot.shutter = f"{shot.shutter_angle}°"
    elif shot.shutter_speed:
        shot.shutter = f"{shot.shutter_speed}s"
    else:
        shot.shutter = ''
    
    db.session.commit()
    flash('Metadata updated successfully!', 'success')
    return redirect(url_for('shot_metadata', shot_id=shot_id))




@app.route('/metadata/overview')
def metadata_overview():
    """View all shots metadata"""
    project = get_active_project()
    shots = Shot.query.filter_by(project_id=project.id).order_by(Shot.event_number).all()
    return render_template('metadata_overview.html', shots=shots, project=project)




@app.route('/metadata/delete-selected', methods=['POST'])
def delete_metadata_selected():
    """Delete metadata from selected shots (keeps the shots, just clears metadata fields)"""
    shot_ids = request.form.get('shot_ids', '')
    
    if not shot_ids:
        return jsonify({'success': False, 'error': 'No shots selected'}), 400
    
    shot_id_list = [int(id.strip()) for id in shot_ids.split(',') if id.strip()]
    
    # Clear metadata fields from shots
    for shot_id in shot_id_list:
        shot = Shot.query.get(shot_id)
        if shot:
            shot.camera = None
            shot.lens = None
            shot.focal_length = None
            shot.t_stop = None
            shot.iso = None
            shot.white_balance = None
            shot.lut = None
            shot.resolution = None
            shot.codec = None
            shot.color_space = None
            shot.gamma = None
            shot.file_path = None
            shot.shot_frame_rate = None
            shot.start_tc = None
            shot.end_tc = None
            shot.start_frame = None
            shot.end_frame = None
            shot.total_frames = None
            shot.camera_manufacturer = None
            shot.camera_serial = None
            shot.shutter_angle = None
            shot.shutter_speed = None
            shot.shutter = None
            shot.distance = None
            shot.nd_filter = None
            shot.camera_tilt = None
            shot.camera_roll = None
    
    db.session.commit()
    
    flash(f'Deleted metadata from {len(shot_id_list)} shot(s)', 'success')
    return jsonify({'success': True})


@app.route('/export/metadata/csv/selected', methods=['POST'])
def export_metadata_csv_selected():
    """Export selected shots metadata as CSV"""
    # Handle both form data and JSON
    if request.is_json:
        data = request.json
        shot_ids = data.get('shot_ids', '')
        vfx_code_ids = data.get('vfx_code_ids', '')
        export_mode = data.get('export_mode', 'single')
    else:
        shot_ids = request.form.get('shot_ids', '')
        vfx_code_ids = request.form.get('vfx_code_ids', '')
        export_mode = 'single'
    
    all_shots = []
    
    # Get shots from VFX code IDs (if provided)
    if vfx_code_ids:
        vfx_id_list = [int(id.strip()) for id in vfx_code_ids.split(',') if id.strip()]
        for vfx_id in vfx_id_list:
            vfx_code = VFXCode.query.get(vfx_id)
            if vfx_code:
                all_shots.extend(vfx_code.shots)
    
    # Get individual shots (if provided)
    if shot_ids:
        shot_id_list = [int(id.strip()) for id in shot_ids.split(',') if id.strip()]
        individual_shots = Shot.query.filter(Shot.id.in_(shot_id_list)).all()
        for shot in individual_shots:
            if shot not in all_shots:
                all_shots.append(shot)
    
    if not all_shots:
        flash('No shots selected', 'error')
        return redirect(url_for('metadata_overview'))
    
    shots = sorted(all_shots, key=lambda s: s.event_number)
    
    if not shots:
        flash('No valid shots selected', 'error')
        return redirect(url_for('metadata_overview'))
    
    # Create CSV
    import csv
    from io import StringIO
    
    output = StringIO()
    writer = csv.writer(output)
    
    # Write headers
    headers = [
        'Clip Name', 'VFX Code', 'Cam Roll', 'Camera Type', 'Camera Manufacturer', 
        'Camera Serial #', 'Lens Type', 'Focal Point (mm)', 'Camera Aperture', 
        'Distance', 'ISO', 'Shutter Angle', 'Shutter Speed', 'White Point (Kelvin)', 
        'ND Filter', 'Camera Tilt Angle', 'Camera Roll Angle', 'LUT Used', 
        'Resolution', 'Video Codec', 'Color Space Notes', 'Gamma Notes', 
        'Shot Frame Rate', 'Start TC', 'End TC', 'Start Frame', 'End Frame', 'Frames'
    ]
    writer.writerow(headers)
    
    # Write shot data
    for shot in shots:
        writer.writerow([
            shot.clip_name,
            shot.vfx_code or '',
            shot.cam_roll or '',
            shot.camera or '',
            shot.camera_manufacturer or '',
            shot.camera_serial or '',
            shot.lens or '',
            shot.focal_length or '',
            shot.t_stop or '',
            shot.distance or '',
            shot.iso or '',
            shot.shutter_angle or '',
            shot.shutter_speed or '',
            shot.white_balance or '',
            shot.nd_filter or '',
            shot.camera_tilt or '',
            shot.camera_roll or '',
            shot.lut or '',
            shot.resolution or '',
            shot.codec or '',
            shot.color_space or '',
            shot.gamma or '',
            shot.shot_frame_rate or '',
            shot.start_tc or '',
            shot.end_tc or '',
            shot.start_frame or '',
            shot.end_frame or '',
            shot.total_frames or ''
        ])
    
    # Create response
    csv_data = output.getvalue()
    csv_file = BytesIO()
    csv_file.write(csv_data.encode('utf-8'))
    csv_file.seek(0)
    
    # Create filename based on selection
    if len(shots) == 1:
        shot = shots[0]
        clip_base = shot.clip_name.replace('.mov', '').replace('.mxf', '').replace('.mp4', '')
        filename = f'{clip_base}_metadata.csv'
    else:
        # Extract VFX codes from clip names if vfx_code field is None
        vfx_codes = []
        for s in shots:
            if s.vfx_code and s.vfx_code != 'None':
                vfx_codes.append(s.vfx_code)
            else:
                # Extract from clip name: WILD_038_0010_bg01_v2 -> WILD_038_0010
                parts = s.clip_name.split('_')
                if len(parts) >= 3:
                    vfx_code = '_'.join(parts[:3])  # Take first 3 parts
                    vfx_codes.append(vfx_code)
        
        if vfx_codes:
            unique_vfx_codes = list(set(vfx_codes))
            if len(unique_vfx_codes) == 1:
                filename = f'{unique_vfx_codes[0]}_metadata.csv'
            else:
                from collections import Counter
                most_common_vfx = Counter(vfx_codes).most_common(1)[0][0]
                filename = f'{most_common_vfx}_and_others_metadata.csv'
        else:
            filename = f'selected_shots_metadata.csv'
    
    # Handle split mode - create separate CSV for each VFX code
    if export_mode == 'split' and request.is_json:
        # Group shots by VFX code
        shots_by_vfx = {}
        for shot in shots:
            vfx_key = shot.vfx_code_obj.vfx_code if shot.vfx_code_obj else shot.vfx_code or 'unknown'
            if vfx_key not in shots_by_vfx:
                shots_by_vfx[vfx_key] = []
            shots_by_vfx[vfx_key].append(shot)
        
        # Generate separate CSV for each VFX code
        csvs = {}
        for vfx_code, vfx_shots in shots_by_vfx.items():
            vfx_output = StringIO()
            vfx_writer = csv.writer(vfx_output)
            
            # Write headers
            vfx_writer.writerow(headers)
            
            # Write data
            for shot in vfx_shots:
                vfx_writer.writerow([
                    shot.clip_name,
                    shot.vfx_code or '',
                    shot.cam_roll or '',
                    shot.camera or '',
                    shot.camera_manufacturer or '',
                    shot.camera_serial or '',
                    shot.lens or '',
                    shot.focal_length or '',
                    shot.t_stop or '',
                    shot.distance or '',
                    shot.iso or '',
                    shot.shutter_angle or '',
                    shot.shutter_speed or '',
                    shot.white_balance or '',
                    shot.nd_filter or '',
                    shot.camera_tilt or '',
                    shot.camera_roll or '',
                    shot.lut or '',
                    shot.resolution or '',
                    shot.codec or '',
                    shot.color_space or '',
                    shot.gamma or '',
                    shot.shot_frame_rate or '',
                    shot.start_tc or '',
                    shot.end_tc or '',
                    shot.start_frame or '',
                    shot.end_frame or '',
                    shot.total_frames or ''
                ])
            
            csvs[f'{vfx_code}_metadata.csv'] = vfx_output.getvalue()
        
        return jsonify({'csvs': csvs})
    
    # Return CSV directly for JSON requests, file download for form requests
    if request.is_json:
        csv_file.seek(0)
        return csv_file.read(), 200, {'Content-Type': 'text/csv'}
    else:
        return send_file(
            csv_file,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )


@app.route('/export/metadata/pdf/selected', methods=['POST'])
def export_metadata_pdf_selected():
    """Export selected shots metadata as PDF"""
    # Handle both form data and JSON
    if request.is_json:
        data = request.json
        shot_ids = data.get('shot_ids', '')
        vfx_code_ids = data.get('vfx_code_ids', '')
        export_mode = data.get('export_mode', 'single')
    else:
        shot_ids = request.form.get('shot_ids', '')
        vfx_code_ids = request.form.get('vfx_code_ids', '')
        export_mode = request.form.get('export_mode', 'single')
    
    all_shots = []
    
    # Get shots from VFX code IDs (if provided)
    if vfx_code_ids:
        vfx_id_list = [int(id.strip()) for id in vfx_code_ids.split(',') if id.strip()]
        for vfx_id in vfx_id_list:
            vfx_code = VFXCode.query.get(vfx_id)
            if vfx_code:
                all_shots.extend(vfx_code.shots)
    
    # Get individual shots (if provided)
    if shot_ids:
        shot_id_list = [int(id.strip()) for id in shot_ids.split(',') if id.strip()]
        individual_shots = Shot.query.filter(Shot.id.in_(shot_id_list)).all()
        for shot in individual_shots:
            if shot not in all_shots:
                all_shots.append(shot)
    
    if not all_shots:
        flash('No shots selected', 'error')
        return redirect(url_for('index'))
    
    shots = sorted(all_shots, key=lambda s: s.event_number)
    
    if not shots:
        flash('No valid shots selected', 'error')
        return redirect(url_for('index'))
    
    # Collect VFX codes for split mode
    vfx_codes = set()
    for s in shots:
        if hasattr(s, 'vfx_code_obj') and s.vfx_code_obj:
            vfx_codes.add(s.vfx_code_obj.vfx_code)
        elif s.vfx_code:
            vfx_codes.add(s.vfx_code)
    
    # Generate metadata PDF using existing function
    from pdf_export import generate_metadata_pdf
    
    if export_mode == 'split' and len(vfx_codes) > 1:
        # SPLIT MODE: Create separate metadata PDF for each VFX code
        import base64
        
        shots_by_vfx = {}
        for shot in shots:
            vfx_key = shot.vfx_code_obj.vfx_code if shot.vfx_code_obj else shot.vfx_code or 'unknown'
            if vfx_key not in shots_by_vfx:
                shots_by_vfx[vfx_key] = []
            shots_by_vfx[vfx_key].append(shot)
        
        pdfs = {}
        for vfx_code, vfx_shots in shots_by_vfx.items():
            pdf_buffer = generate_metadata_pdf(vfx_shots)
            pdf_buffer.seek(0)
            pdf_base64 = base64.b64encode(pdf_buffer.read()).decode('utf-8')
            pdfs[f'{vfx_code}_metadata.pdf'] = pdf_base64
        
        return jsonify({'pdfs': pdfs})
    
    # SINGLE/COMBINED MODE: One metadata PDF
    
    # Create filename based on selection (same logic as CSV)
    if len(shots) == 1:
        shot = shots[0]
        clip_base = shot.clip_name.replace('.mov', '').replace('.mxf', '').replace('.mp4', '')
        filename = f'{clip_base}_metadata.pdf'
    else:
        # Extract VFX codes from clip names if vfx_code field is None
        vfx_codes = []
        for s in shots:
            if s.vfx_code and s.vfx_code != 'None':
                vfx_codes.append(s.vfx_code)
            else:
                # Extract from clip name: WILD_038_0010_bg01_v2 -> WILD_038_0010
                parts = s.clip_name.split('_')
                if len(parts) >= 3:
                    vfx_code = '_'.join(parts[:3])  # Take first 3 parts
                    vfx_codes.append(vfx_code)
        
        if vfx_codes:
            unique_vfx_codes = list(set(vfx_codes))
            if len(unique_vfx_codes) == 1:
                filename = f'{unique_vfx_codes[0]}_metadata.pdf'
            else:
                from collections import Counter
                most_common_vfx = Counter(vfx_codes).most_common(1)[0][0]
                filename = f'{most_common_vfx}_and_others_metadata.pdf'
        else:
            filename = f'selected_shots_metadata.pdf'
    
    pdf_buffer = generate_metadata_pdf(shots)
    
    # Return PDF directly for JSON requests, file download for form requests
    if request.is_json:
        pdf_buffer.seek(0)
        return pdf_buffer.read(), 200, {'Content-Type': 'application/pdf'}
    else:
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )



@app.route('/history/<int:shot_id>')
def shot_history(shot_id):
    """View version history for a shot"""
    # Get shot first, then get project from shot
    shot = Shot.query.get_or_404(shot_id)
    project = shot.project
    history = ShotHistory.query.filter_by(shot_id=shot_id).order_by(ShotHistory.version.desc()).all()
    
    return render_template('shot_history.html', shot=shot, history=history, project=project)



@app.route('/check_vfx_code', methods=['POST'])
def check_vfx_code():
    """Check if a VFX code already exists"""
    project_id = session.get('project_id')
    if not project_id:
        return jsonify({'error': 'No project selected'}), 400
    
    data = request.get_json()
    vfx_code = data.get('vfx_code', '').strip()
    
    if not vfx_code:
        return jsonify({'exists': False})
    
    existing_shot = Shot.query.filter_by(
        vfx_code=vfx_code,
        project_id=project_id
    ).first()
    
    if existing_shot:
        return jsonify({
            'exists': True,
            'shot_id': existing_shot.id,
            'current_version': existing_shot.version,
            'status': existing_shot.status,
            'turnover_number': existing_shot.turnover_number
        })
    
    return jsonify({'exists': False})

@app.route('/update_shot_from_import', methods=['POST'])
def update_shot_from_import():
    """Update an existing shot from EDL import"""
    project_id = session.get('project_id')
    if not project_id:
        return jsonify({'error': 'No project selected'}), 400
    
    data = request.get_json()
    shot_id = data.get('shot_id')
    edl_data = data.get('edl_data')
    
    shot = Shot.query.filter_by(id=shot_id, project_id=project_id).first()
    if not shot:
        return jsonify({'error': 'Shot not found'}), 404
    
    # Update the shot
    update_shot_from_edl(shot, edl_data)
    
    return jsonify({
        'success': True,
        'new_version': shot.version,
        'status': shot.status
    })



@app.route('/import_confirmation', methods=['GET', 'POST'])
def import_confirmation():
    project = get_active_project()
    # Load pending import from temp file
    pending_file = session.get('pending_import_file')
    pending = None
    if pending_file and os.path.exists(pending_file):
        try:
            with open(pending_file, 'r') as pf:
                pending = json.load(pf)
        except Exception as e:
            print(f"Error loading pending import: {e}")
    
    if not pending:
        flash('No pending import', 'error')
        return redirect(url_for('import_edl_route'))
    
    # If no conflicts, auto-process (missing codes will be skipped)
    if not pending.get('conflicts'):
        all_shots = pending['all_shots']
        for shot_data in all_shots:
            vfx_code_name = shot_data.pop('vfx_code', None)
            
            if not vfx_code_name:
                continue
            
            # Find or create VFXCode
            vfx_code_obj = VFXCode.query.filter_by(
                vfx_code=vfx_code_name,
                project_id=project.id
            ).first()
            
            if not vfx_code_obj:
                vfx_code_obj = VFXCode(
                    vfx_code=vfx_code_name,
                    project_id=project.id,
                    shot_status='Prep'
                )
                db.session.add(vfx_code_obj)
                db.session.flush()
            
            # Add vfx_code_id and project_id to shot_data
            shot_data['vfx_code_id'] = vfx_code_obj.id
            shot_data['project_id'] = project.id
            shot_data['plate_status'] = 'Prep'
            shot_data['plate_number'] = 0
            # Set default start frame from project settings
            if 'start_frame' not in shot_data or not shot_data.get('start_frame'):
                shot_data['start_frame'] = project.default_start_frame or 1001
            
            shot = Shot(**shot_data)
            db.session.add(shot)
            
            if shot.cam_roll:
                metadata = find_metadata_by_cam_roll(shot.cam_roll)
                if metadata:
                    shot.camera = metadata.camera
                    shot.lens = metadata.lens
                    shot.focal_length = metadata.focal_length
                    shot.t_stop = metadata.t_stop
                    shot.iso = metadata.iso
                    shot.white_balance = metadata.white_balance
                    shot.lut = metadata.lut
                    shot.resolution = metadata.resolution
                    shot.codec = metadata.codec
                    shot.color_space = metadata.color_space
                    shot.gamma = metadata.gamma
                    shot.file_path = metadata.file_path
                    shot.shot_frame_rate = metadata.shot_frame_rate
                    shot.start_tc = metadata.start_tc
                    shot.end_tc = metadata.end_tc
                    # Don't overwrite start_frame if already set by user
                    if not shot.start_frame or str(shot.start_frame) in ('0', ''):
                        shot.start_frame = metadata.start_frame
                    shot.end_frame = metadata.end_frame
                    shot.total_frames = metadata.total_frames
                    shot.camera_manufacturer = metadata.camera_manufacturer
                    shot.camera_serial = metadata.camera_serial
                    shot.shutter_angle = metadata.shutter_angle
                    shot.shutter_speed = metadata.shutter_speed
                    shot.shutter = metadata.shutter
                    shot.distance = metadata.distance
                    shot.nd_filter = metadata.nd_filter
                    shot.camera_tilt = metadata.camera_tilt
                    shot.camera_roll = metadata.camera_roll
                    shot.camera_clipname = metadata.camera_clipname

                    shot.cdl_sat = metadata.cdl_sat

                    shot.cdl_sop = metadata.cdl_sop
        
        db.session.commit()
        # Auto-number plates within each VFX code
        auto_number_plates(project.id)
        # Clean up pending import temp file
        pending_file = session.pop('pending_import_file', None)
        if pending_file and os.path.exists(pending_file):
            try:
                os.remove(pending_file)
            except:
                pass
        flash('EDL imported successfully!', 'success')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        conflicts = pending['conflicts']
        all_shots = pending['all_shots']
        
        
        for i, conflict in enumerate(conflicts):
            action = request.form.get(f'action_{i}')
            if action == 'update':
                shot_data = conflict['shot_data']
                
                # Find the VFXCode first
                vfx_code_obj = VFXCode.query.filter_by(
                    vfx_code=conflict['vfx_code'],
                    project_id=project.id
                ).first()
                
                existing = None
                if vfx_code_obj:
                    existing = Shot.query.filter_by(
                        vfx_code_id=vfx_code_obj.id,
                        plate_type=conflict['shot_data'].get('plate_type'),
                        vfx_element=conflict['shot_data'].get('vfx_element')
                    ).first()
                
                
                if existing:
                    create_shot_history_entry(existing)
                    
                    # Smart handle recalculation
                    from models import timecode_to_frames, frames_to_timecode
                    
                    
                    # Check if tape name (reel/cam_roll) changed - indicates different take
                    old_tape = existing.cam_roll or existing.reel
                    new_tape = shot_data.get('cam_roll') or shot_data.get('reel')
                    
                    if old_tape and new_tape and old_tape != new_tape:
                        # Tape changed - treat as new turnover
                        
                        existing.source_in = shot_data.get('source_in')
                        existing.source_out = shot_data.get('source_out')
                        existing.record_in = shot_data.get('record_in')
                        existing.record_out = shot_data.get('record_out')
                        existing.cam_roll = shot_data.get('cam_roll')
                        existing.reel = shot_data.get('reel')
                        
                        # Recalculate duration
                        if existing.source_in and existing.source_out:
                            fps = existing.fps or 24.0
                            in_frames = timecode_to_frames(existing.source_in, fps)
                            out_frames = timecode_to_frames(existing.source_out, fps)
                            existing.duration_frames = out_frames - in_frames + 1
                        else:
                            existing.duration_frames = shot_data.get('duration_frames')
                        
                        # Reset to defaults
                        existing.head_handles = 0
                        existing.tail_handles = 0
                        existing.start_frame = 1001
                        
                        existing.element_notes = (existing.element_notes or '') + f"\n[Auto v{existing.version + 1}]: [PLATE CHANGE] Plate changed ({old_tape} -> {new_tape}). FULL TURNOVER REQUIRED."
                        
                        # Skip the rest of smart handle logic
                        existing.clip_name = shot_data.get('clip_name', existing.clip_name)
                        existing.plate_status = 'UPDATE'
                        existing.version += 1
                        if existing.vfx_code_obj:
                            existing.vfx_code_obj.shot_status = 'Update'
                        
                        # Continue to next iteration (skip rest of update logic for this shot)
                        continue
                    
                    old_scan_in_tc = existing.tc_scan_in()
                    old_scan_out_tc = existing.tc_scan_out()
                    new_cut_in_tc = shot_data.get('source_in')
                    new_cut_out_tc = shot_data.get('source_out')
                    
                    
                    if old_scan_in_tc and old_scan_out_tc and new_cut_in_tc and new_cut_out_tc:
                        fps = existing.fps or 24.0
                        
                        old_scan_in_frames = timecode_to_frames(old_scan_in_tc, fps)
                        old_scan_out_frames = timecode_to_frames(old_scan_out_tc, fps)
                        new_cut_in_frames = timecode_to_frames(new_cut_in_tc, fps)
                        new_cut_out_frames = timecode_to_frames(new_cut_out_tc, fps)
                        
                        
                        # Check if new cut fits within old scan range
                        if new_cut_in_frames >= old_scan_in_frames and new_cut_out_frames <= old_scan_out_frames:
                            # Recalculate handles based on distance from scan boundaries
                            # Scan range stays the same, but cut position within it changes
                            new_head_handles = new_cut_in_frames - old_scan_in_frames
                            new_tail_handles = old_scan_out_frames - new_cut_out_frames
                            
                            # Start frame stays the same - scan range hasn't changed
                            new_start_frame = int(existing.start_frame or 1001)
                            
                            existing.head_handles = new_head_handles
                            existing.tail_handles = new_tail_handles
                            existing.start_frame = new_start_frame
                            existing.element_notes = (existing.element_notes or '') + f"\n[Auto v{existing.version + 1}]: Cut within handles. New handles: {new_head_handles}/{new_tail_handles}. No new turnover needed."
                            
                        else:
                            # New cut exceeds old scan range - needs new turnover
                            # Reset everything as if fresh import, but keep plate_number and comments
                            existing.source_in = shot_data.get('source_in')
                            existing.source_out = shot_data.get('source_out')
                            existing.record_in = shot_data.get('record_in')
                            existing.record_out = shot_data.get('record_out')
                            
                            # Recalculate duration from timecodes
                            if existing.source_in and existing.source_out:
                                in_frames = timecode_to_frames(existing.source_in, fps)
                                out_frames = timecode_to_frames(existing.source_out, fps)
                                existing.duration_frames = out_frames - in_frames + 1
                            else:
                                existing.duration_frames = shot_data.get('duration_frames')
                            
                            # Reset handles to 0 (no handles for new turnover until set)
                            existing.head_handles = 0
                            existing.tail_handles = 0
                            
                            # Reset start frame to default
                            existing.start_frame = 1001
                            
                            # Add warning to notes
                            existing.element_notes = (existing.element_notes or '') + f"\n[Auto v{existing.version + 1}]: [WARNING] Cut EXCEEDS previous scan range. NEW TURNOVER REQUIRED. Reset to 0/0 handles."
                            
                    
                    existing.clip_name = shot_data.get('clip_name', existing.clip_name)
                    existing.clip_name = shot_data.get('clip_name', existing.clip_name)
                    existing.reel = shot_data.get('reel', existing.reel)
                    existing.record_in = shot_data.get('record_in', existing.record_in)
                    existing.record_out = shot_data.get('record_out', existing.record_out)
                    existing.source_in = shot_data.get('source_in', existing.source_in)
                    existing.source_out = shot_data.get('source_out', existing.source_out)
                    
                    # Handles calculation removed  # TODO: Implement timecode calculation
                    
                    existing.plate_status = 'UPDATE'
                    existing.version += 1
                    
                    # Update VFXCode status to 'Update'
                    if existing.vfx_code_obj:
                        existing.vfx_code_obj.shot_status = 'Update'
                    
                    if shot_data.get('cam_roll'):
                        existing.cam_roll = shot_data['cam_roll']
                        metadata = find_metadata_by_cam_roll(existing.cam_roll)
                        if metadata:
                            existing.camera = metadata.camera
                            existing.lens = metadata.lens
                            existing.focal_length = metadata.focal_length
        
        for shot_data in all_shots:
            vfx_code = shot_data.get('vfx_code')
            if not vfx_code:
                continue
            is_conflict = any(c['vfx_code'] == vfx_code for c in conflicts)
            if is_conflict:
                continue
            
            vfx_code_name = shot_data.pop('vfx_code', None)
            
            if not vfx_code_name:
                continue
            
            # Find or create VFXCode
            vfx_code_obj = VFXCode.query.filter_by(
                vfx_code=vfx_code_name,
                project_id=project.id
            ).first()
            
            if not vfx_code_obj:
                vfx_code_obj = VFXCode(
                    vfx_code=vfx_code_name,
                    project_id=project.id,
                    shot_status='Prep'
                )
                db.session.add(vfx_code_obj)
                db.session.flush()
            
            shot_data['vfx_code_id'] = vfx_code_obj.id
            shot_data['project_id'] = project.id
            shot_data['plate_status'] = 'Prep'
            shot_data['plate_number'] = 0
            # Set default start frame from project settings
            if 'start_frame' not in shot_data or not shot_data.get('start_frame'):
                shot_data['start_frame'] = project.default_start_frame or 1001
            
            shot = Shot(**shot_data)
            db.session.add(shot)
            
            if shot.cam_roll:
                metadata = find_metadata_by_cam_roll(shot.cam_roll)
                if metadata:
                    shot.camera = metadata.camera
                    shot.lens = metadata.lens
                    shot.focal_length = metadata.focal_length
                    shot.t_stop = metadata.t_stop
                    shot.iso = metadata.iso
                    shot.white_balance = metadata.white_balance
                    shot.lut = metadata.lut
                    shot.resolution = metadata.resolution
                    shot.codec = metadata.codec
                    shot.color_space = metadata.color_space
                    shot.gamma = metadata.gamma
                    shot.file_path = metadata.file_path
                    shot.shot_frame_rate = metadata.shot_frame_rate
                    shot.start_tc = metadata.start_tc
                    shot.end_tc = metadata.end_tc
                    # Don't overwrite start_frame if already set by user
                    if not shot.start_frame or str(shot.start_frame) in ('0', ''):
                        shot.start_frame = metadata.start_frame
                    shot.end_frame = metadata.end_frame
                    shot.total_frames = metadata.total_frames
                    shot.camera_manufacturer = metadata.camera_manufacturer
                    shot.camera_serial = metadata.camera_serial
                    shot.shutter_angle = metadata.shutter_angle
                    shot.shutter_speed = metadata.shutter_speed
                    shot.shutter = metadata.shutter
                    shot.distance = metadata.distance
                    shot.nd_filter = metadata.nd_filter
                    shot.camera_tilt = metadata.camera_tilt
                    shot.camera_roll = metadata.camera_roll
                    shot.camera_clipname = metadata.camera_clipname

                    shot.cdl_sat = metadata.cdl_sat

                    shot.cdl_sop = metadata.cdl_sop
        
        db.session.commit()
        # Auto-number plates within each VFX code
        auto_number_plates(project.id)
        # Clean up pending import temp file
        pending_file = session.pop('pending_import_file', None)
        if pending_file and os.path.exists(pending_file):
            try:
                os.remove(pending_file)
            except:
                pass
        flash('EDL imported successfully!', 'success')
        return redirect(url_for('index'))
    
    return render_template('import_confirmation.html', 
                         conflicts=pending['conflicts'],
                         missing_codes=pending.get('missing_codes', []),
                         project=project)



@app.route('/metadata/<int:metadata_id>/delete', methods=['POST'])
def delete_metadata(metadata_id):
    """Delete a metadata entry"""
    project = get_active_project()
    metadata = CameraMetadata.query.get_or_404(metadata_id)
    
    cam_roll = metadata.cam_roll
    db.session.delete(metadata)
    db.session.commit()
    
    flash(f'Deleted metadata for {cam_roll}', 'success')
    return redirect(url_for('metadata'))


@app.route('/update_turnover_date', methods=['POST'])
def update_turnover_date():
    """Update turnover date for all shots in a VFX code group"""
    from datetime import datetime
    
    data = request.json
    vfx_code = data.get('vfx_code')
    date_str = data.get('date')
    
    if not vfx_code:
        return jsonify({'success': False, 'error': 'No VFX code provided'})
    
    # Parse date
    turnover_date = None
    if date_str:
        try:
            turnover_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except:
            return jsonify({'success': False, 'error': 'Invalid date format'})
    
    # Update all shots with this VFX code
    shots = Shot.query.filter_by(vfx_code=vfx_code, project_id=session.get('current_project')).all()
    for shot in shots:
        shot.turnover_date = turnover_date
    
    db.session.commit()
    
    return jsonify({'success': True, 'updated': len(shots)})



# ============================================================
# NEW ROUTES FOR VFXCODE REDESIGN
# ============================================================

@app.route('/settings')
def settings():
    """Project settings page"""
    project = get_active_project()
    all_projects = Project.query.all()
    return render_template('settings.html', project=project, all_projects=all_projects)



@app.route('/project/<int:project_id>/path_aliases', methods=['GET'])
def get_path_aliases(project_id):
    """Get list of path aliases for project"""
    import json
    project = Project.query.get_or_404(project_id)
    
    try:
        paths = json.loads(project.path_aliases) if project.path_aliases else []
    except:
        paths = []
    
    return jsonify({'success': True, 'paths': paths})

@app.route('/project/<int:project_id>/path_aliases/add', methods=['POST'])
def add_path_alias(project_id):
    """Add a new path alias"""
    import json
    project = Project.query.get_or_404(project_id)
    data = request.get_json()
    
    new_path = data.get('path', '').strip()
    if not new_path:
        return jsonify({'success': False, 'error': 'Path cannot be empty'})
    
    try:
        paths = json.loads(project.path_aliases) if project.path_aliases else []
    except:
        paths = []
    
    # Don't add duplicates
    if new_path in paths:
        return jsonify({'success': False, 'error': 'Path already exists'})
    
    paths.append(new_path)
    project.path_aliases = json.dumps(paths)
    db.session.commit()
    
    return jsonify({'success': True, 'paths': paths})

@app.route('/project/<int:project_id>/path_aliases/remove', methods=['POST'])
def remove_path_alias(project_id):
    """Remove a path alias by index"""
    import json
    project = Project.query.get_or_404(project_id)
    data = request.get_json()
    
    index = data.get('index')
    if index is None:
        return jsonify({'success': False, 'error': 'Index required'})
    
    try:
        paths = json.loads(project.path_aliases) if project.path_aliases else []
        if 0 <= index < len(paths):
            paths.pop(index)
            project.path_aliases = json.dumps(paths)
            db.session.commit()
            return jsonify({'success': True, 'paths': paths})
        else:
            return jsonify({'success': False, 'error': 'Invalid index'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})




def resolve_image_path(relative_path, project_id):
    """Try to find an image using path aliases. Returns the first valid path or the original."""
    import json
    import os
    
    if not relative_path:
        return None
    
    # If it's already an absolute path that exists, return it
    if os.path.isabs(relative_path) and os.path.exists(relative_path):
        return relative_path
    
    # Get project's path aliases
    project = Project.query.get(project_id)
    if not project or not project.path_aliases:
        return relative_path
    
    try:
        aliases = json.loads(project.path_aliases)
    except:
        return relative_path
    
    # Try each alias
    for base_path in aliases:
        full_path = os.path.join(base_path, relative_path)
        if os.path.exists(full_path):
            return full_path
    
    # If none found, return original
    return relative_path




def get_image_cache_folder():
    """Get the local image cache folder"""
    import platform
    
    if platform.system() == 'Darwin':  # Mac
        cache_dir = os.path.expanduser('~/Library/Application Support/VFX Shot Tracker/image_cache')
    elif platform.system() == 'Windows':
        cache_dir = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'VFX Shot Tracker', 'image_cache')
    else:  # Linux
        cache_dir = os.path.expanduser('~/.local/share/VFX Shot Tracker/image_cache')
    
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir

def get_project_cache_folder(project_id=None):
    """Get cache folder for specific project"""
    cache_dir = get_image_cache_folder()
    
    if project_id:
        project_cache = os.path.join(cache_dir, f'project_{project_id}')
        os.makedirs(project_cache, exist_ok=True)
        return project_cache
    
    return cache_dir

def cache_image(source_path, relative_path, project_id):
    """Copy and compress image from server to local cache"""
    from PIL import Image
    import shutil
    
    if not source_path or not os.path.exists(source_path):
        return None
    
    try:
        project_cache = get_project_cache_folder(project_id)
        
        # Create subdirectories in cache if needed (e.g., reference_images/)
        cached_path = os.path.join(project_cache, relative_path)
        cached_dir = os.path.dirname(cached_path)
        os.makedirs(cached_dir, exist_ok=True)
        
        # Check if we need to update the cache
        should_process = True
        if os.path.exists(cached_path):
            # Compare modification times
            source_mtime = os.path.getmtime(source_path)
            cache_mtime = os.path.getmtime(cached_path)
            should_process = source_mtime > cache_mtime
        
        if should_process:
            try:
                # Open and compress/resize the image
                img = Image.open(source_path)
                
                # Convert RGBA to RGB if needed (for JPEG)
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                
                # Resize if too large (max 300px on longest side)
                max_size = 300
                if max(img.size) > max_size:
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                
                # Save as JPEG with compression
                # Change extension to .jpg for cache
                cached_path_jpg = os.path.splitext(cached_path)[0] + '.jpg'
                img.save(cached_path_jpg, 'JPEG', quality=60, optimize=True)
                
                print(f"CACHE: Compressed {relative_path} to cache")
                return cached_path_jpg
                
            except Exception as img_error:
                # If image processing fails, fall back to simple copy
                print(f"CACHE: Image processing failed, copying original: {img_error}")
                shutil.copy2(source_path, cached_path)
                return cached_path
        else:
            print(f"CACHE: Using cached {relative_path}")
            # Check if compressed version exists
            cached_path_jpg = os.path.splitext(cached_path)[0] + '.jpg'
            if os.path.exists(cached_path_jpg):
                return cached_path_jpg
            return cached_path
        
    except Exception as e:
        print(f"CACHE ERROR: Failed to cache {relative_path}: {e}")
        return None

def get_cached_image_path(relative_path, project_id):
    """Get cached image path, or cache it if not present"""
    # First, check if already in cache
    project_cache = get_project_cache_folder(project_id)
    cached_path = os.path.join(project_cache, relative_path)
    
    if os.path.exists(cached_path):
        print(f"CACHE: Serving from cache: {relative_path}")
        return cached_path
    
    # Not in cache, try to get from server
    source_path = resolve_reference_image_path(relative_path, project_id)
    
    if not source_path or not os.path.exists(source_path):
        print(f"CACHE: Source not found for: {relative_path}")
        return None
    
    # Cache it for next time
    cached_path = cache_image(source_path, relative_path, project_id)
    
    return cached_path if cached_path else source_path


def get_database_folder():
    """Get the folder where the current database is stored"""
    # Use the environment variable which is set when opening a database
    current_db = os.environ.get('VFX_DB_PATH')
    if current_db:
        return os.path.dirname(os.path.abspath(current_db))
    
    # Fallback to DATABASE_PATH
    db_path = DATABASE_PATH if os.path.isabs(DATABASE_PATH) else os.path.join(os.path.dirname(__file__), DATABASE_PATH)
    return os.path.dirname(os.path.abspath(db_path))

def get_reference_images_folder():
    """Get the reference_images folder next to the database"""
    db_folder = get_database_folder()
    ref_folder = os.path.join(db_folder, 'reference_images')
    
    # Create folder if it doesn't exist
    try:
        os.makedirs(ref_folder, exist_ok=True)
    except Exception as e:
        pass  # Folder creation failed, but continue anyway
    
    return ref_folder

def resolve_reference_image_path(relative_path, project_id=None):
    """Resolve a reference image path using database location and path aliases"""
    import json
    
    if not relative_path:
        return None
    
    # If it's already an absolute path that exists, return it
    if os.path.isabs(relative_path) and os.path.exists(relative_path):
        return relative_path
    
    # Try database folder first (primary location)
    db_folder = get_database_folder()
    primary_path = os.path.join(db_folder, relative_path)
    if os.path.exists(primary_path):
        return primary_path
    
    # Try path aliases if project_id provided
    if project_id:
        project = Project.query.get(project_id)
        if project and project.path_aliases:
            try:
                aliases = json.loads(project.path_aliases)
                for base_path in aliases:
                    alias_path = os.path.join(base_path, relative_path)
                    if os.path.exists(alias_path):
                        return alias_path
            except:
                pass
    
    # Return primary path even if it doesn't exist (for new uploads)
    return primary_path



@app.route('/cache/open_location', methods=['POST'])
def open_cache_location():
    """Open the cache folder in file explorer"""
    import subprocess
    import platform
    
    try:
        cache_folder = get_image_cache_folder()
        
        if platform.system() == 'Darwin':  # Mac
            subprocess.run(['open', cache_folder])
        elif platform.system() == 'Windows':
            subprocess.run(['explorer', cache_folder])
        else:  # Linux
            subprocess.run(['xdg-open', cache_folder])
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error opening cache location: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/cache/status')
def cache_status():
    """Get current cache enabled status"""
    project = Project.query.first()
    enabled = project.cache_enabled if project else True
    return jsonify({'enabled': enabled})

@app.route('/cache/toggle', methods=['POST'])
def toggle_cache():
    """Toggle cache enabled/disabled"""
    try:
        data = request.get_json()
        enabled = data.get('enabled', True)
        
        project = Project.query.first()
        if project:
            project.cache_enabled = enabled
            db.session.commit()
            return jsonify({'success': True})
        
        return jsonify({'success': False, 'error': 'No project found'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/cache/clear', methods=['POST'])
def clear_image_cache():
    """Clear all cached images"""
    import shutil
    
    try:
        cache_folder = get_image_cache_folder()
        
        # Remove all contents
        if os.path.exists(cache_folder):
            shutil.rmtree(cache_folder)
            # Recreate empty folder
            os.makedirs(cache_folder, exist_ok=True)
        
        print("Image cache cleared")
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error clearing cache: {e}")
        return jsonify({'success': False, 'error': str(e)})



@app.route('/reference_image/<path:filename>')
def serve_reference_image(filename):
    """Serve reference images from local cache (with automatic caching from server)"""
    from flask import send_file, abort
    
    # Get current project
    project = Project.query.first()
    project_id = project.id if project else None
    
    # Check if caching is enabled
    cache_enabled = project.cache_enabled if project and hasattr(project, 'cache_enabled') else True
    
    if cache_enabled:
        # Use cache
        cached_path = get_cached_image_path(filename, project_id)
        if cached_path and os.path.exists(cached_path):
            return send_file(cached_path)
    else:
        # Serve directly from server (bypass cache)
        source_path = resolve_reference_image_path(filename, project_id)
        if source_path and os.path.exists(source_path):
            return send_file(source_path)
    
    abort(404)



@app.route('/')
def index():
    """New dashboard - grouped by VFXCode with search/sort/filter support"""
    from flask import request
    project = get_active_project()
    
    # Get query parameters
    search_term = request.args.get('search', '').strip()
    sort_by = request.args.get('sort', 'vfx_code')  # Default: alphabetical
    status_filter = request.args.get('status', '')
    
    # Get all VFXCodes for this project with their shots
    vfx_codes = VFXCode.query.filter_by(project_id=project.id).all()
    
    # APPLY SEARCH FILTER
    if search_term:
        search_lower = search_term.lower()
        
        # Try to parse date in DD/MM or DD/MM/YY format for searching
        import re
        date_search_formats = []
        
        # Match DD/MM/YYYY or DD/MM/YY or DD/MM
        date_match = re.match(r'^(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?$', search_term)
        if date_match:
            day = date_match.group(1).zfill(2)
            month = date_match.group(2).zfill(2)
            year = date_match.group(3)
            
            if year:
                # Convert 2-digit year to 4-digit (assume 2000s)
                if len(year) == 2:
                    year = '20' + year
                # Create YYYY-MM-DD format for database comparison
                date_search_formats.append(f'{year}-{month}-{day}')
            else:
                # No year provided - search for any year with this day/month
                # We'll search for the pattern "-MM-DD" in the date string
                date_search_formats.append(f'-{month}-{day}')
        
        vfx_codes = [
            vfx for vfx in vfx_codes 
            if (search_lower in (vfx.vfx_code or '').lower() or
                search_lower in str(vfx.turnover_number or '').lower() or
                search_lower in str(vfx.turnover_date or '').lower() or
                any(date_fmt in str(vfx.turnover_date or '') for date_fmt in date_search_formats) or
                search_lower in (vfx.vendor_1 or '').lower() or
                search_lower in (vfx.vendor_2 or '').lower() or
                search_lower in (vfx.vendor_3 or '').lower() or
                search_lower in (vfx.vendor_4 or '').lower() or
                any(search_lower in (shot.clip_name or '').lower() for shot in vfx.shots))
        ]
        
        # Sort search results: first by turnover number if exists, then by VFX code
        import re
        def sort_key(vfx):
            # Try to extract number from VFX code for natural sorting
            code = vfx.vfx_code or ''
            match = re.search(r'(\d+)', code)
            if match:
                # Return (prefix, number) tuple for proper sorting
                prefix = code[:match.start()]
                number = int(match.group(1))
                return (prefix.lower(), number)
            return (code.lower(), 0)
        
        vfx_codes.sort(key=sort_key)
    
    # APPLY STATUS FILTER
    if status_filter:
        vfx_codes = [vfx for vfx in vfx_codes if vfx.shot_status == status_filter]
    
    # Group shots by VFXCode and sort plates
    plate_order = {'bg': 1, 'fg': 2, 'pl': 3, 'rf': 4, 'fx': 5}
    for vfx_code_obj in vfx_codes:
        # Sort shots (plates) within each VFXCode
        vfx_code_obj.shots.sort(key=lambda s: (
            plate_order.get(s.plate_type or 'zz', 99),
            s.vfx_element or '99',
            s.plate_number or 999
        ))
    
    # APPLY SORT
    
    if sort_by == 'vfx_code':
        # Natural number sorting
        import re
        
        # DEBUG: Show before sort
        before = [v.vfx_code for v in vfx_codes[:10]]
        
        def natural_sort_key(vfx):
            code = vfx.vfx_code or ''
            # Split into text and number parts for proper natural sorting
            # e.g. 'WILD_038_0010' -> ['wild_', 38, '_', 10]
            parts = re.split(r'(\d+)', code)
            result = []
            for part in parts:
                if part.isdigit():
                    result.append((0, int(part)))  # Numbers sort numerically
                else:
                    result.append((1, part.lower()))  # Text sorts alphabetically
            return result
        
        vfx_codes.sort(key=natural_sort_key)
        
        # DEBUG: Show after sort
        after = [v.vfx_code for v in vfx_codes[:10]]
        

    elif sort_by == 'vfx_code_reverse':
        vfx_codes.sort(key=lambda v: v.vfx_code or '', reverse=True)
    elif sort_by == 'turnover_recent':
        # Sort by turnover_number (Recent = highest numbers first)
        # Empty values go last (when reversed, 0 sorts after 1)
        import re
        def turnover_sort_key(vfx):
            to_num = vfx.turnover_number or ''
            if not to_num:
                # Empty values: indicator 0 to push to end when reversed
                return (0, '', 0)
            match = re.search(r'(\d+)', str(to_num))
            if match:
                prefix = str(to_num)[:match.start()]
                number = int(match.group(1))
                return (1, prefix.lower(), number)
            return (1, str(to_num).lower(), 0)
        vfx_codes.sort(key=turnover_sort_key, reverse=True)
    elif sort_by == 'turnover_oldest':
        # Sort by turnover_number (Oldest = lowest numbers first)
        # Empty values go last
        import re
        def turnover_sort_key(vfx):
            to_num = vfx.turnover_number or ''
            if not to_num:
                # Empty values: use very high number to push to end
                return (1, 'zzz', 999999)
            match = re.search(r'(\d+)', str(to_num))
            if match:
                prefix = str(to_num)[:match.start()]
                number = int(match.group(1))
                return (0, prefix.lower(), number)
            return (0, str(to_num).lower(), 0)
        vfx_codes.sort(key=turnover_sort_key)
    elif sort_by == 'date_recent':
        # Empty dates go last (when reversed, 0 sorts after 1)
        vfx_codes.sort(key=lambda v: (1, str(v.turnover_date)) if v.turnover_date else (0, ''), reverse=True)
    elif sort_by == 'date_oldest':
        # Empty dates go last
        vfx_codes.sort(key=lambda v: (0, str(v.turnover_date)) if v.turnover_date else (1, '9999-99-99'))
    else:
        # Default: natural number sorting (TO1, TO2, TO10 instead of TO1, TO10, TO2)
        import re
        def natural_sort_key(vfx):
            code = vfx.vfx_code or ''
            match = re.search(r'(\d+)', code)
            if match:
                prefix = code[:match.start()]
                number = int(match.group(1))
                return (prefix.lower(), number)
            return (code.lower(), 0)
        vfx_codes.sort(key=natural_sort_key)
    
    # Get status counts (for all VFX codes, not filtered)
    status_counts = {
        'prep': VFXCode.query.filter_by(project_id=project.id, shot_status='Prep').count(),
        'ready': VFXCode.query.filter_by(project_id=project.id, shot_status='Ready').count(),
        'turnover': VFXCode.query.filter_by(project_id=project.id, shot_status='Turned Over').count(),
        'update': VFXCode.query.filter_by(project_id=project.id, shot_status='Update').count(),
        'omitted': VFXCode.query.filter_by(project_id=project.id, shot_status='Omitted').count(),
    }
    
    # Get all projects for switcher
    all_projects = Project.query.order_by(Project.created_at.desc()).all()
    
    
    return render_template('index_new.html', 
                         vfx_codes=vfx_codes,
                         status_counts=status_counts,
                         project=project,
                         all_projects=all_projects,
                         search_term=search_term,
                         sort_by=sort_by,
                         status_filter=status_filter)

@app.route('/vfx/<int:vfx_id>/update/status', methods=['POST'])
def update_vfx_status(vfx_id):
    """Update VFXCode shot status"""
    from flask import jsonify
    
    vfx_code = VFXCode.query.get_or_404(vfx_id)
    data = request.get_json()
    
    vfx_code.shot_status = data.get('shot_status', 'Prep')
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/vfx/<int:vfx_id>/update/field', methods=['POST'])
def update_vfx_field(vfx_id):
    """Update a VFXCode field"""
    from flask import jsonify
    
    vfx_code = VFXCode.query.get_or_404(vfx_id)
    data = request.get_json()
    
    for field, value in data.items():
        if hasattr(vfx_code, field):
            # Handle date fields
            if field == 'turnover_date' and value:
                from datetime import datetime
                value = datetime.strptime(value, '%Y-%m-%d').date()
            setattr(vfx_code, field, value)
    
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/shot/<int:shot_id>/data')
def get_shot_data(shot_id):
    """Get shot data as JSON for edit section"""
    from flask import jsonify
    
    shot = Shot.query.get_or_404(shot_id)
    
    return jsonify({
        'id': shot.id,
        'head_handles': shot.head_handles or 0,
        'tail_handles': shot.tail_handles or 0,
        'crank_speed': shot.crank_speed or 100.0,
        'plate_number': shot.plate_number or 0,
        'duration_frames': shot.duration_frames or 0,
        'start_frame': shot.start_frame or 1001,
        'vfx_code': shot.vfx_code or '',
        'plate_type': shot.plate_type or '',
        'vfx_element': shot.vfx_element or '',
        'version': shot.version or 1,
        'clip_name': shot.clip_name or ''
    })


@app.route('/shot/<int:shot_id>/update_clip_name', methods=['POST'])
def update_clip_name(shot_id):
    """Update clip_name and re-parse plate_type, vfx_element, vfx_code from it"""
    from database import parse_vfx_elements
    
    shot = Shot.query.get_or_404(shot_id)
    data = request.get_json()
    new_clip_name = data.get('clip_name', '').strip()
    
    if not new_clip_name:
        return jsonify({'success': False, 'error': 'Empty clip name'})
    
    # Parse the new clip name
    parsed = parse_vfx_elements(new_clip_name)
    
    # Update shot fields
    shot.clip_name = new_clip_name
    shot.vfx_code = parsed['vfx_code']
    shot.plate_type = parsed['plate_type']
    shot.vfx_element = parsed['vfx_element']
    shot.version = parsed['version']
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'clip_name': shot.clip_name,
        'vfx_code': shot.vfx_code,
        'plate_type': shot.plate_type,
        'vfx_element': shot.vfx_element,
        'version': shot.version
    })


# Update the existing shot field update route to handle JSON
@app.route('/shot/<int:shot_id>/update/field', methods=['POST'])
def update_shot_field_json(shot_id):
    """Update a single field for a shot (for auto-save) - now handles JSON"""
    from flask import jsonify
    
    shot = Shot.query.get_or_404(shot_id)
    
    # Handle both form data and JSON
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form
    
    # Get the field name and value
    for field_name, value in data.items():
        if hasattr(shot, field_name):
            # Convert types as needed
            if field_name in ['head_handles', 'tail_handles', 'version', 'plate_number', 'start_frame']:
                value = int(value) if value else (1001 if field_name == 'start_frame' else 0)
            elif field_name == 'crank_speed':
                value = float(value) if value else 100.0
            elif field_name == 'pull_date':
                from datetime import datetime
                if value:
                    value = datetime.strptime(value, '%Y-%m-%d').date()
                else:
                    value = None
            
            setattr(shot, field_name, value)
    
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/shot/<int:shot_id>/validate-handles')
def validate_shot_handles(shot_id):
    """Validate if handles exceed available source material"""
    from flask import jsonify
    
    shot = Shot.query.get_or_404(shot_id)
    validation = shot.validate_handles()
    
    return jsonify(validation)


@app.route('/project/<int:project_id>/update', methods=['POST'])
def update_project_name(project_id):
    from flask import jsonify
    try:
        project = Project.query.get_or_404(project_id)
        data = request.get_json()
        if data is not None and 'name' in data:
            new_name = data['name'] if data['name'] else ''
            # Allow empty string for name (to show only logo)
            project.name = new_name
            # DO NOT remove logo - keep it
            db.session.commit()
            return jsonify({'success': True, 'name': project.name})
        return jsonify({'success': False, 'error': 'No name provided'})
    except Exception as e:
        print(f"ERROR: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/project/<int:project_id>/update_fps', methods=['POST'])
def update_project_fps(project_id):
    """Update project FPS via AJAX"""
    from flask import jsonify
    try:
        project = Project.query.get_or_404(project_id)
        data = request.get_json()
        
        if data and 'fps' in data:
            try:
                new_fps = float(data['fps'])
                if new_fps <= 0 or new_fps > 120:
                    return jsonify({'success': False, 'error': 'FPS must be between 0 and 120'})
                
                old_fps = project.fps
                project.fps = new_fps
                db.session.commit()
                return jsonify({'success': True, 'fps': new_fps})
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': 'Invalid FPS value'})
        
        return jsonify({'success': False})
    except Exception as e:
        print(f"ERROR: {e}")
        return jsonify({'success': False, 'error': str(e)})

    except Exception as e:
        import traceback
        traceback.print_exc()
        flash(f'Error uploading logo: {str(e)}', 'error')
        return redirect(url_for('settings'))

@app.route('/project/<int:project_id>/upload_logo', methods=['POST'])
def upload_project_logo(project_id):
    from flask import jsonify
    import os
    from werkzeug.utils import secure_filename
    
    try:
        project = Project.query.get_or_404(project_id)
        
        if 'logo' not in request.files:
            flash('No file uploaded', 'error')
            return redirect(url_for('settings'))
        
        file = request.files['logo']
        if not file or file.filename == '':
            flash('Please select an image file first', 'error')
            return redirect(url_for('settings'))
        
        
        # Create uploads directory if it doesn't exist
        upload_dir = os.path.join('static', 'uploads')
        os.makedirs(upload_dir, exist_ok=True)
        
        # Save file
        filename = secure_filename(f"project_{project_id}_{file.filename}")
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)
        
        # Update project
        logo_path = f'uploads/{filename}'
        project.logo_path = logo_path
        
        # Force flush and commit
        db.session.flush()
        db.session.commit()
        
        # Verify it was ACTUALLY saved by querying fresh
        db.session.expire(project)
        fresh_project = Project.query.get(project_id)
        
        if not fresh_project.logo_path:
            fresh_project.logo_path = logo_path
            db.session.commit()
            db.session.expire(fresh_project)
            check = Project.query.get(project_id)
        
        flash('Logo uploaded successfully!', 'success')
        return redirect(url_for('settings'))
    except Exception as e:
        import traceback
        traceback.print_exc()
        flash(f'Error uploading logo: {str(e)}', 'error')
        return redirect(url_for('settings'))




@app.route('/project/<int:project_id>/remove_logo', methods=['POST'])
def remove_project_logo(project_id):
    # Remove project logo - don't delete the file, just clear from database
    try:
        project = Project.query.get_or_404(project_id)
        
        # Just clear the logo path from database
        # Do NOT delete the actual file - it might be used elsewhere or user may want to re-use it
        project.logo_path = None
        project.logo_filename = None
        db.session.commit()
        
        flash('Logo removed successfully', 'success')
        return redirect(url_for('settings'))
    except Exception as e:
        flash(f'Error removing logo: {str(e)}', 'error')
        return redirect(url_for('settings'))


@app.route('/vfx/<int:vfx_id>/upload-reference', methods=['POST'])
def upload_vfx_reference(vfx_id):
    """Upload reference image for VFX code"""
    from flask import jsonify
    import os
    from werkzeug.utils import secure_filename
    
    vfx_code = VFXCode.query.get_or_404(vfx_id)
    
    if 'image' not in request.files:
        return jsonify({'success': False, 'error': 'No image'})
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})
    
    if file:
        filename = secure_filename(f"vfx_{vfx_id}_{file.filename}")
        # Save to database folder, not app folder
        upload_dir = get_reference_images_folder()
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)
        
        vfx_code.reference_image = f'reference_images/{filename}'
        db.session.commit()
        
        return jsonify({'success': True})
    
    return jsonify({'success': False})

@app.route('/shot/<int:shot_id>/upload-reference', methods=['POST'])
def upload_shot_reference(shot_id):
    """Upload reference image for shot"""
    from flask import jsonify
    import os
    from werkzeug.utils import secure_filename
    
    shot = Shot.query.get_or_404(shot_id)
    
    if 'image' not in request.files:
        return jsonify({'success': False, 'error': 'No image'})
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})
    
    if file:
        filename = secure_filename(f"shot_{shot_id}_{file.filename}")
        # Save to database folder, not app folder
        upload_dir = get_reference_images_folder()
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)
        
        shot.reference_image = f'reference_images/{filename}'
        db.session.commit()
        
        return jsonify({'success': True})
    
    return jsonify({'success': False})



@app.route('/api/set_database_path', methods=['POST'])
def set_database_path():
    """Change the active database file - does NOT modify current Flask state.
    Flask will be restarted by Electron with the new VFX_DB_PATH env var."""
    data = request.get_json()
    new_path = data.get('path')
    
    if not new_path:
        return jsonify({'error': 'No path provided'}), 400
    
    try:
        import sqlite3
        is_new_database = False
        
        if not os.path.exists(new_path):
            is_new_database = True
            print(f"Will create new database: {new_path}")
        elif os.path.getsize(new_path) == 0:
            is_new_database = True
            print(f"Empty file detected, will create fresh database: {new_path}")
            os.remove(new_path)
        else:
            try:
                test_conn = sqlite3.connect(new_path)
                test_conn.execute("SELECT 1").fetchone()
                test_conn.close()
                print(f"Valid existing database: {new_path}")
            except sqlite3.DatabaseError as e:
                return jsonify({'error': f'Invalid database file: {str(e)}'}), 400
        
        if is_new_database:
            # Create the new database using a SEPARATE connection
            # Do NOT touch the current Flask db instance
            from sqlalchemy import create_engine
            new_uri = f'sqlite:///{new_path}'
            print(f"Creating new database at: {new_path}")
            
            new_engine = create_engine(new_uri)
            db.Model.metadata.create_all(bind=new_engine)
            
            # Create a default project
            from sqlalchemy.orm import Session as SASession
            with SASession(new_engine) as sa_session:
                from models import Project
                project_name = os.path.splitext(os.path.basename(new_path))[0]
                default_project = Project(name=project_name, is_active=True, fps=24.0)
                sa_session.add(default_project)
                sa_session.commit()
                print(f"Created default project: {default_project.name}")
            
            new_engine.dispose()
            
            # Verify
            if os.path.exists(new_path):
                file_size = os.path.getsize(new_path)
                print(f"[OK] New database created: {new_path} ({file_size} bytes)")
        else:
            print(f"Existing database validated: {new_path}")
        
        # Do NOT change DATABASE_PATH or db engine here.
        # Electron will restart Flask with VFX_DB_PATH set to new_path.
        
        return jsonify({
            'success': True,
            'path': new_path,
            'message': f'Database ready: {os.path.basename(new_path)}',
            'restart_required': True
        })
        
    except Exception as e:
        print(f"Error preparing database: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_database_path', methods=['GET'])
def get_database_path():
    """Get current database path"""
    global DATABASE_PATH
    return jsonify({
        'path': DATABASE_PATH,
        'filename': os.path.basename(DATABASE_PATH)
    })



@app.route('/project/<int:project_id>/update_default_start_frame', methods=['POST'])
def update_default_start_frame(project_id):
    """Update project default start frame"""
    from flask import jsonify
    try:
        project = Project.query.get_or_404(project_id)
        data = request.get_json()
        
        if data and 'default_start_frame' in data:
            project.default_start_frame = int(data['default_start_frame'])
            db.session.commit()
            return jsonify({'success': True, 'default_start_frame': project.default_start_frame})
        
        return jsonify({'success': False, 'error': 'No value provided'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# Warm up Playwright Chromium on startup so first PDF export is fast
def _warmup_playwright():
    try:
        from utils.pdf_playwright import _get_browser
        print("[TOOL] Warming up Playwright Chromium...")
        _get_browser()
        print("[OK] Playwright Chromium ready")
    except Exception as e:
        print(f"[WARN] Playwright warmup failed: {e}")

import threading
threading.Thread(target=_warmup_playwright, daemon=True).start()




@app.route('/metadata/library')
def metadata_library():
    """View all camera metadata in the library (including orphaned)"""
    from models import CameraMetadata, Shot
    
    project = get_active_project()
    all_metadata = CameraMetadata.query.order_by(CameraMetadata.cam_roll).all()
    
    # Check which are linked to shots
    metadata_info = []
    for m in all_metadata:
        # Check if any shot references this cam_roll
        linked_shots = Shot.query.filter(
            Shot.project_id == project.id,
            Shot.cam_roll.like(f'%{m.cam_roll}%')
        ).all()
        
        # Also check reverse - metadata cam_roll matches shot cam_roll prefix
        if not linked_shots:
            all_shots = Shot.query.filter_by(project_id=project.id).all()
            for s in all_shots:
                if s.cam_roll and (s.cam_roll.startswith(m.cam_roll) or m.cam_roll.startswith(s.cam_roll)):
                    linked_shots.append(s)
        
        metadata_info.append({
            'metadata': m,
            'linked_count': len(linked_shots),
            'linked_clips': [s.clip_name for s in linked_shots[:3]]
        })
    
    return render_template('metadata_library.html', 
                         metadata_info=metadata_info,
                         project=project)


@app.route('/metadata/library/delete', methods=['POST'])
def delete_metadata_library_items():
    """Delete selected metadata entries from the library"""
    from models import CameraMetadata
    
    metadata_ids = request.form.get('metadata_ids', '')
    if not metadata_ids:
        flash('No metadata selected', 'error')
        return redirect(url_for('metadata_library'))
    
    id_list = [int(id.strip()) for id in metadata_ids.split(',') if id.strip()]
    
    count = CameraMetadata.query.filter(CameraMetadata.id.in_(id_list)).delete(synchronize_session=False)
    db.session.commit()
    
    flash(f'Deleted {count} metadata entries', 'success')
    return redirect(url_for('metadata_library'))


@app.route('/metadata/library/clear_orphaned', methods=['POST'])
def clear_orphaned_metadata():
    """Delete all metadata entries that aren't linked to any shots"""
    from models import CameraMetadata, Shot
    
    project = get_active_project()
    all_metadata = CameraMetadata.query.all()
    all_shots = Shot.query.filter_by(project_id=project.id).all()
    shot_cam_rolls = [s.cam_roll for s in all_shots if s.cam_roll]
    
    deleted = 0
    for m in all_metadata:
        # Check if linked (either direction)
        is_linked = False
        for shot_roll in shot_cam_rolls:
            if shot_roll == m.cam_roll or shot_roll.startswith(m.cam_roll) or m.cam_roll.startswith(shot_roll):
                is_linked = True
                break
        
        if not is_linked:
            db.session.delete(m)
            deleted += 1
    
    db.session.commit()
    flash(f'Cleared {deleted} orphaned metadata entries', 'success')
    return redirect(url_for('metadata_library'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001, use_reloader=False)

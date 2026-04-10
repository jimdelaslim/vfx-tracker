"""Playwright-based PDF generation - renders HTML to PDF for pixel-perfect output"""
import os
import sys
import tempfile
import base64
from playwright.sync_api import sync_playwright
from flask import render_template


def image_to_base64(image_path):
    """Convert image to base64 data URL for embedding in HTML"""
    try:
        with open(image_path, 'rb') as f:
            image_data = f.read()

        # Determine MIME type based on extension
        ext = image_path.lower().split('.')[-1]
        mime_types = {
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'gif': 'image/gif',
            'webp': 'image/webp'
        }
        mime_type = mime_types.get(ext, 'image/png')

        base64_data = base64.b64encode(image_data).decode('utf-8')
        return f'data:{mime_type};base64,{base64_data}'
    except Exception as e:
        print(f"Error converting image to base64: {e}")
        return None

def generate_shot_pdf_playwright(shot):
    """Generate PDF for a single shot using Playwright"""
    shots = [shot]
    vfx_code = shot.vfx_code_obj.vfx_code if hasattr(shot, 'vfx_code_obj') and shot.vfx_code_obj else shot.vfx_code
    return generate_selected_shots_pdf_playwright(shots, shot.project, vfx_code)

def generate_selected_shots_pdf_playwright(shots, project, title=None):
    print(f"[TOOL] PDF Export started: {len(shots)} shots")
    """Generate PDF for selected shots - one page per plate"""

    if not shots:
        return None

    # Group shots by VFX code
    from collections import defaultdict
    vfx_groups = defaultdict(list)
    for shot in shots:
        vfx_key = shot.vfx_code_obj.vfx_code if (hasattr(shot, 'vfx_code_obj') and shot.vfx_code_obj) else (shot.vfx_code or 'Unknown')
        vfx_groups[vfx_key].append(shot)

    # Generate HTML pages (one per plate)
    html_pages = []

    for vfx_code, group_shots in vfx_groups.items():
        vfx_code_obj = group_shots[0].vfx_code_obj if hasattr(group_shots[0], 'vfx_code_obj') else None

        # Get VFX-level data
        vfx_reference_image = None
        if vfx_code_obj and vfx_code_obj.reference_image:
            # Import here to avoid circular imports
            from app import resolve_reference_image_path
            img_path = resolve_reference_image_path(vfx_code_obj.reference_image, vfx_code_obj.project_id)
            if img_path and os.path.exists(img_path):
                vfx_reference_image = image_to_base64(img_path)
                print(f"[TOOL] VFX Reference Image converted to base64: {vfx_reference_image[:50] if vfx_reference_image else None}...")

        to_number = vfx_code_obj.turnover_number if vfx_code_obj else ''
        to_date = vfx_code_obj.turnover_date if vfx_code_obj else ''

        vendors = []
        if vfx_code_obj:
            for v in [vfx_code_obj.vendor_1, vfx_code_obj.vendor_2, vfx_code_obj.vendor_3, vfx_code_obj.vendor_4]:
                if v:
                    vendors.append(v)
        vendors_str = ', '.join(vendors) if vendors else 'N/A'

        scope_of_work = vfx_code_obj.scope_of_work if vfx_code_obj else ''
        vfx_note = vfx_code_obj.vfx_editorial_note if vfx_code_obj else ''

        # Get shot status for color
        shot_status = vfx_code_obj.shot_status if vfx_code_obj else 'Prep'
        status_color = get_status_color(shot_status)

        # Prepare all plates for this VFX code
        plates_data = [prepare_plate_data(shot, project) for shot in group_shots]

        # Render HTML for this VFX code with all its plates
        html = render_template('pdf/plate_export.html',
            vfx_code=vfx_code,
            project_name=project.name,
            vfx_reference_image=vfx_reference_image,
            to_number=to_number,
            to_date=to_date,
            vendors=vendors_str,
            scope_of_work=scope_of_work,
            vfx_note=vfx_note,
            status_color=status_color,
            plates=plates_data  # All plates for this VFX code
        )

        html_pages.append(html)

    # Use Playwright to render HTML to PDF
    pdf_bytes = render_html_to_pdf(html_pages)

    return pdf_bytes


def format_date_only(date_str):
    """Remove time portion from date string"""
    if not date_str:
        return ''
    # Remove everything after the space (the time portion)
    return str(date_str).split(' ')[0]

def prepare_plate_data(shot, project):
    """Prepare plate data for template"""

    # Get plate reference image
    plate_reference_image = None
    if shot.reference_image:
        from app import resolve_reference_image_path
        img_path = resolve_reference_image_path(shot.reference_image, shot.vfx_code_obj.project_id if shot.vfx_code_obj else None)
        if img_path and os.path.exists(img_path):
            plate_reference_image = image_to_base64(img_path)
            print(f"[TOOL] Plate Reference Image converted to base64: {plate_reference_image[:50] if plate_reference_image else None}...")

    # Calculate frame range
    fr = shot.frame_range_display()
    crank_multiplier = (shot.crank_speed or 100.0) / 100.0
    head_handles_output = round((shot.head_handles or 0) / crank_multiplier)
    tail_handles_output = round((shot.tail_handles or 0) / crank_multiplier)

    # Get status color
    status_color = get_status_color(shot.plate_status)

    return {
        'plate_number': shot.plate_number,
        'clip_name': shot.clip_name,
        'plate_type': f"{shot.plate_type}{shot.vfx_element or ''}".upper(),
        'version': shot.version,
        'status': shot.plate_status,
        'status_color': status_color,
        'reference_image': plate_reference_image,

        # Frame range
        'frame_range': fr,
        'total_frames': shot.total_source_frames(),

        # Timecode
        'source_in': shot.source_in,
        'source_out': shot.source_out,
        'duration_frames': shot.duration_frames,
        'tc_scan_in': shot.tc_scan_in(),
        'tc_scan_out': shot.tc_scan_out(),
        'total_source_frames': shot.total_source_frames(),
        'head_handles': shot.head_handles or 0,
        'tail_handles': shot.tail_handles or 0,
        'head_handles_output': head_handles_output,
        'crank_speed': shot.crank_speed or 100,
        'tail_handles_output': tail_handles_output,

        # Camera metadata
        'camera': shot.camera,
        'lens': shot.lens,
        'focal_length': shot.focal_length,
        't_stop': shot.t_stop,
        'iso': shot.iso,
        'resolution': shot.resolution,
        'fps': shot.shot_frame_rate or str(shot.fps or ''),
        'cam_roll': shot.cam_roll or shot.reel,
        'camera_clipname': shot.camera_clipname or '',
        'shutter_angle': shot.shutter_angle or shot.shutter_speed,
        'camera_roll': shot.camera_roll,
        'camera_tilt': shot.camera_tilt,
        'distance': shot.distance,

        # Color metadata
        'lut': shot.lut,
        'color_space': shot.color_space,
        'gamma': shot.gamma,
        'codec': shot.codec,

        # Notes
        'pull_date': format_date_only(shot.pull_date),
        'plate_rev': shot.plate_rev,
        'retime_notes': shot.retime_notes,
        'resize_reposition': shot.resize_reposition,
        'element_notes': shot.element_notes
    }

def get_status_color(status):
    """Get hex color for a status"""
    STATUS_COLORS = {
        'prep': '#e83e8c',
        'ready': '#fd7e14',
        'update': '#ffc107',
        'turned over': '#198754',
        'omitted': '#000000'
    }
    if not status:
        return STATUS_COLORS['prep']
    status_lower = status.lower().replace(' ', '').replace('-', '')
    for key, color in STATUS_COLORS.items():
        if key.replace(' ', '').replace('-', '') == status_lower:
            return color
    return STATUS_COLORS['prep']

def render_html_to_pdf(html_pages):
    print(f"[TOOL] Rendering {len(html_pages)} pages with Playwright")
    """Use Playwright to render HTML pages to PDF"""
    
    try:
        with sync_playwright() as p:
            # Set browser path for bundled Playwright browsers on Windows
            browser_path = None
            
            # Check if running in PyInstaller bundle
            if getattr(sys, 'frozen', False):
                print("[TOOL] Running in packaged mode, looking for bundled browsers...")
                
                # Get base path - different depending on how PyInstaller was run
                if hasattr(sys, '_MEIPASS'):
                    base_path = sys._MEIPASS
                else:
                    base_path = os.path.dirname(sys.executable)
                
                # Check multiple possible locations for Playwright browsers
                possible_paths = [
                    os.path.join(os.path.dirname(sys.executable), 'playwright-browsers'),
                    os.path.join(base_path, 'playwright-browsers'),
                    os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
                ]
                
                for path in possible_paths:
                    if path and os.path.exists(path):
                        browser_path = path
                        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = path
                        print(f"[OK] Using Playwright browsers from: {path}")
                        break
                
                if not browser_path:
                    print(f"[ERROR] Could not find Playwright browsers!")
                    print(f"[ERROR] Checked paths: {possible_paths}")
                    print(f"[ERROR] sys.executable: {sys.executable}")
                    print(f"[ERROR] Current working directory: {os.getcwd()}")
                    raise Exception("Playwright browsers not found in packaged app")
            else:
                print("[TOOL] Running in development mode, using system Playwright browsers")
            
            # Launch browser
            browser = p.chromium.launch()
            context = browser.new_context()
            page = context.new_page()

            # Combine all pages with page breaks
            combined_html = """
            <!DOCTYPE html>
            <html>
            <head><meta charset="UTF-8"></head>
            <body>
            """

            for i, html_content in enumerate(html_pages):
                if i > 0:
                    combined_html += '<div style="page-break-before: always;"></div>'
                combined_html += html_content

            combined_html += """
            </body>
            </html>
            """

            # Set content and generate PDF
            page.set_content(combined_html)

            pdf_bytes = page.pdf(
                format='A4',
                landscape=True,
                margin={
                    'top': '0.5in',
                    'right': '0.5in',
                    'bottom': '0.5in',
                    'left': '0.5in'
                },
                print_background=True
            )

            browser.close()
            print(f"[OK] PDF generated: {len(pdf_bytes)} bytes")
            return pdf_bytes
            
    except Exception as e:
        print(f"[ERROR] Playwright PDF generation failed: {str(e)}")
        import traceback
        traceback.print_exc()
        raise Exception(f"PDF generation failed: {str(e)}")

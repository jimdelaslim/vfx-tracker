"""PDF generation using HTML templates and xhtml2pdf"""
import os
from datetime import datetime
from io import BytesIO
from xhtml2pdf import pisa
from jinja2 import Template

def get_status_color(status):
    """Get color for shot status"""
    status_colors = {
        'prep': '#e83e8c',
        'ready': '#fd7e14',
        'update': '#ffc107',
        'review': '#17a2b8',
        'final': '#28a745',
        'on hold': '#6c757d',
    }
    return status_colors.get(status.lower() if status else 'prep', '#fd7e14')

def generate_selected_shots_pdf(title, shots, project):
    """Generate PDF from HTML template"""
    
    # Group shots by VFX code
    vfx_groups = {}
    for shot in shots:
        vfx_code = shot.vfx_code_obj.vfx_code if hasattr(shot, 'vfx_code_obj') and shot.vfx_code_obj else 'Unknown'
        if vfx_code not in vfx_groups:
            vfx_groups[vfx_code] = {
                'vfx_obj': shot.vfx_code_obj if hasattr(shot, 'vfx_code_obj') else None,
                'shots': []
            }
        vfx_groups[vfx_code]['shots'].append(shot)
    
    # For now, just handle the first VFX group
    vfx_code = list(vfx_groups.keys())[0]
    group = vfx_groups[vfx_code]
    vfx_obj = group['vfx_obj']
    group_shots = group['shots']
    
    # Prepare data for template
    plates = []
    for shot in group_shots:
        # Calculate retime handles
        crank = shot.crank_speed or 100.0
        head_output = int((shot.head_handles or 0) / (crank / 100.0))
        tail_output = int((shot.tail_handles or 0) / (crank / 100.0))
        
        # Get frame range
        frame_range = shot.frame_range_display()
        
        # Get reference image path (convert to file:// URL)
        ref_image = None
        if shot.reference_image:
            from app import resolve_reference_image_path
            img_path = resolve_reference_image_path(shot.reference_image, shot.vfx_code.project_id if shot.vfx_code else None)
            ref_image = 'file://' + os.path.abspath(img_path) if img_path else None
        
        plate_data = {
            'plate_number': shot.plate_number or 0,
            'clip_name': shot.clip_name or '',
            'plate_type': shot.plate_type or '',
            'version': shot.version or 1,
            'status': vfx_obj.shot_status if vfx_obj else 'Prep',
            'status_color': get_status_color(vfx_obj.shot_status if vfx_obj else 'Prep'),
            'frame_range': frame_range,
            'total_frames': shot.total_source_frames() or 0,
            'reference_image': ref_image,
            'camera': shot.camera,
            'lens': shot.lens,
            'focal_length': shot.focal_length,
            't_stop': shot.t_stop,
            'iso': shot.iso,
            'resolution': shot.resolution,
            'cam_roll': shot.cam_roll,
            'shutter_angle': shot.shutter_angle,
            'camera_roll': shot.camera_roll,
            'camera_tilt': shot.camera_tilt,
            'distance': shot.distance,
            'lut': shot.lut,
            'color_space': shot.color_space,
            'gamma': shot.gamma,
            'codec': shot.codec,
            'source_in': shot.source_in,
            'source_out': shot.source_out,
            'duration_frames': shot.duration_frames,
            'tc_scan_in': shot.tc_scan_in() if shot.tc_scan_in else '',
            'tc_scan_out': shot.tc_scan_out() if shot.tc_scan_out else '',
            'total_source_frames': shot.total_source_frames() or 0,
            'head_handles': shot.head_handles or 0,
            'tail_handles': shot.tail_handles or 0,
            'head_handles_output': head_output,
            'tail_handles_output': tail_output,
            'pull_date': shot.pull_date.strftime('%Y-%m-%d') if shot.pull_date else '',
            'plate_rev': shot.plate_rev,
            'retime_notes': shot.retime_notes,
            'resize_reposition': shot.resize_reposition,
            'element_notes': shot.element_notes,
        }
        plates.append(plate_data)
    
    # Get VFX reference image
    vfx_ref_image = None
    if vfx_obj and vfx_obj.reference_image:
        from app import resolve_reference_image_path
        img_path = resolve_reference_image_path(vfx_obj.reference_image, vfx_obj.project_id)
        vfx_ref_image = 'file://' + os.path.abspath(img_path) if img_path else None
    
    # Prepare vendors list
    vendors = []
    if vfx_obj:
        if vfx_obj.vendor_1: vendors.append(vfx_obj.vendor_1)
        if vfx_obj.vendor_2: vendors.append(vfx_obj.vendor_2)
        if vfx_obj.vendor_3: vendors.append(vfx_obj.vendor_3)
        if vfx_obj.vendor_4: vendors.append(vfx_obj.vendor_4)
    
    template_data = {
        'vfx_code': vfx_code,
        'project_name': project.name,
        'vfx_reference_image': vfx_ref_image,
        'to_number': vfx_obj.to_number if vfx_obj else '',
        'to_date': vfx_obj.to_date.strftime('%Y-%m-%d') if vfx_obj and vfx_obj.to_date else '',
        'vendors': ', '.join(vendors) if vendors else 'N/A',
        'scope_of_work': vfx_obj.scope_of_work if vfx_obj else '',
        'vfx_note': vfx_obj.vfx_editorial_note if vfx_obj else '',
        'plates': plates,
    }
    
    # Load and render template
    with open('templates/pdf/plate_export.html', 'r') as f:
        template_str = f.read()
    
    template = Template(template_str)
    html_content = template.render(**template_data)
    
    # Generate PDF with xhtml2pdf
    pdf_buffer = BytesIO()
    pisa_status = pisa.CreatePDF(html_content, dest=pdf_buffer)
    
    if pisa_status.err:
        raise Exception("PDF generation failed")
    
    pdf_buffer.seek(0)
    return pdf_buffer

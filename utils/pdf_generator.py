"""PDF generation utilities for VFX tracker - matching UI exactly"""
import os
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfgen import canvas
from io import BytesIO
from datetime import datetime

# Status color mapping - matching UI
STATUS_COLORS = {
    'prep': '#e83e8c',      # Pink
    'ready': '#fd7e14',     # Orange
    'update': '#ffc107',    # Yellow
    'review': '#17a2b8',    # Cyan
    'final': '#28a745',     # Green
    'on hold': '#6c757d',   # Gray
}

def get_status_color(status):
    """Get hex color for a status"""
    if not status:
        return STATUS_COLORS['prep']
    status_lower = status.lower().replace(' ', '')
    for key, color in STATUS_COLORS.items():
        if key.replace(' ', '') == status_lower:
            return color
    return STATUS_COLORS['prep']  # Default

def generate_shot_pdf(shot):
    """Generate PDF for a single shot"""
    return generate_selected_shots_pdf(shot.clip_name, [shot], shot.project)

def generate_vfx_group_pdf(vfx_code, shots, project):
    """Generate PDF for all plates in a VFX shot group"""
    return generate_selected_shots_pdf(vfx_code, shots, project)

def load_reference_image(shot, width=4*inch, height=2.6*inch):
    """Load reference image - only shot-specific, no fallback"""
    # Only check shot-level reference (don't fall back to VFX code)
    if shot.reference_image:
        image_path = os.path.join('static', shot.reference_image)
        if os.path.exists(image_path):
            try:
                img = Image(image_path, width=width, height=height, kind='proportional')
                return img
            except Exception as e:
                print(f"Error loading shot image: {e}")
    
    return None

def generate_selected_shots_pdf(title, shots, project):
    """Generate PDF matching UI layout exactly"""
    buffer = BytesIO()
    
    # Landscape for width
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=landscape(letter), 
        topMargin=0.3*inch, 
        bottomMargin=0.3*inch,
        leftMargin=0.4*inch,
        rightMargin=0.4*inch
    )
    
    styles = getSampleStyleSheet()
    elements = []
    
    # Title section
    title_style = ParagraphStyle(
        'Title', 
        parent=styles['Heading1'], 
        fontSize=16, 
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=4,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    elements.append(Paragraph(title, title_style))
    
    subtitle_style = ParagraphStyle(
        'subtitle',
        parent=styles['Normal'],
        alignment=TA_CENTER,
        fontSize=8,
        textColor=colors.HexColor('#6c757d')
    )
    elements.append(Paragraph(
        f"{project.name}", 
        subtitle_style
    ))
    elements.append(Spacer(1, 0.1*inch))
    
    # Group by VFX code
    from collections import defaultdict
    vfx_groups = defaultdict(list)
    for shot in shots:
        vfx_key = shot.vfx_code_obj.vfx_code if (hasattr(shot, 'vfx_code_obj') and shot.vfx_code_obj) else (shot.vfx_code or 'Unknown')
        vfx_groups[vfx_key].append(shot)
    
    # Process each VFX group
    for vfx_idx, (vfx_code, group_shots) in enumerate(vfx_groups.items()):
        if vfx_idx > 0:
            elements.append(PageBreak())  # New page for each VFX code
        
        # Get VFX status to determine header color
        first_shot = group_shots[0]
        vfx_code_obj = first_shot.vfx_code_obj if hasattr(first_shot, 'vfx_code_obj') and first_shot.vfx_code_obj else None
        vfx_status = vfx_code_obj.shot_status if vfx_code_obj else 'Prep'
        header_color = get_status_color(vfx_status)
        
        # VFX Code Header - Orange/status color bar
        vfx_header_text = f"{vfx_code}"
        vfx_header = Table([[vfx_header_text]], colWidths=[10*inch])
        vfx_header.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(header_color)),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 14),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ]))
        elements.append(vfx_header)
        elements.append(Spacer(1, 0.1*inch))
        
        # VFX Info Section (matches UI top section)
        generate_vfx_info_section(elements, vfx_code_obj, first_shot)
        
        elements.append(Spacer(1, 0.1*inch))
        
        # VFX ELEMENTS header
        elements_header = Table([["VFX ELEMENTS"]], colWidths=[10*inch])
        elements_header.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(header_color)),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ]))
        elements.append(elements_header)
        elements.append(Spacer(1, 0.1*inch))
        
        # Each plate in the VFX group
        for plate_idx, shot in enumerate(group_shots):
            if plate_idx > 0:
                elements.append(PageBreak())  # New page for each plate
            
            generate_plate_section(elements, shot, header_color)
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer

def generate_vfx_info_section(elements, vfx_code_obj, shot):
    """Generate the top VFX info section matching UI"""
    # This section has: Reference Image | TO info/Vendors | Scope/Notes
    
    left_col = []
    
    # Reference Image - load VFX code level reference only
    ref_img = None
    if vfx_code_obj and vfx_code_obj.reference_image:
        image_path = os.path.join('static', vfx_code_obj.reference_image)
        if os.path.exists(image_path):
            try:
                ref_img = Image(image_path, width=2.8*inch, height=2*inch, kind='proportional')
            except Exception as e:
                print(f"Error loading VFX image: {e}")
    if ref_img:
        left_col.append(ref_img)
    else:
        # Placeholder
        ref_placeholder = Table([['IMAGE REFERENCE'], ['Click to upload']], colWidths=[2.8*inch])
        ref_placeholder.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f9fa')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#adb5bd')),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTSIZE', (0, 1), (-1, 1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 40),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 40),
        ]))
        left_col.append(ref_placeholder)
    
    left_col.append(Spacer(1, 0.08*inch))
    
    # TO# and TO Date
    to_data = [
        ['TO #', 'TO Date'],
        [vfx_code_obj.turnover_number if vfx_code_obj and vfx_code_obj.turnover_number else '', 
         vfx_code_obj.turnover_date.strftime('%Y-%m-%d') if vfx_code_obj and vfx_code_obj.turnover_date else '']
    ]
    to_table = Table(to_data, colWidths=[1.4*inch, 1.4*inch])
    to_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#f8f9fa')),
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#f8f9fa')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    left_col.append(to_table)
    left_col.append(Spacer(1, 0.08*inch))
    
    # Vendors
    vendors = []
    if vfx_code_obj:
        if vfx_code_obj.vendor_1: vendors.append(vfx_code_obj.vendor_1)
        if vfx_code_obj.vendor_2: vendors.append(vfx_code_obj.vendor_2)
        if vfx_code_obj.vendor_3: vendors.append(vfx_code_obj.vendor_3)
        if vfx_code_obj.vendor_4: vendors.append(vfx_code_obj.vendor_4)
    
    vendor_data = [['Vendor(s)']]
    for v in (vendors or ['', '', '', '']):
        vendor_data.append([v])
    
    vendor_table = Table(vendor_data[:5], colWidths=[2.8*inch])  # Max 4 vendors + header
    vendor_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    left_col.append(vendor_table)
    
    # Middle: Scope of Work
    scope = vfx_code_obj.scope_of_work if vfx_code_obj and vfx_code_obj.scope_of_work else 'Please complete'
    scope_para = Paragraph(scope, ParagraphStyle('scope', fontSize=8, leading=10))
    scope_table = Table([['Scope of Work'], [scope_para]], colWidths=[3.5*inch])
    scope_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    # Right: VFX Editorial Note
    note = vfx_code_obj.vfx_editorial_note if vfx_code_obj and vfx_code_obj.vfx_editorial_note else ''
    note_para = Paragraph(note, ParagraphStyle('note', fontSize=8, leading=10))
    note_table = Table([['VFX Editorial Note'], [note_para]], colWidths=[3.5*inch])
    note_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    # Combine all three columns
    main_layout = Table([[left_col, scope_table, note_table]], colWidths=[3*inch, 3.6*inch, 3.6*inch])
    main_layout.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    elements.append(main_layout)

def generate_plate_section(elements, shot, header_color):
    """Generate individual plate section matching UI card EXACTLY"""
    
    plate_elements = []
    
    # Plate header with number, name, element, version, status
    plate_status_color = get_status_color(shot.vfx_code_obj.shot_status if hasattr(shot, 'vfx_code_obj') and shot.vfx_code_obj else 'Prep')
    
    plate_header_data = [[
        f"#{shot.plate_number or 0}",
        shot.clip_name or '',
        shot.plate_type or '',
        f"v {shot.version or 1}",
        (shot.vfx_code_obj.shot_status if hasattr(shot, 'vfx_code_obj') and shot.vfx_code_obj else 'Prep')
    ]]
    
    plate_header = Table(plate_header_data, colWidths=[0.5*inch, 3.5*inch, 0.8*inch, 0.6*inch, 1.2*inch])
    plate_header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (3, 0), colors.HexColor('#343a40')),
        ('BACKGROUND', (4, 0), (4, 0), colors.HexColor(plate_status_color)),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('ALIGN', (2, 0), (-1, 0), 'CENTER'),
        ('LEFTPADDING', (1, 0), (1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    plate_elements.append(plate_header)
    plate_elements.append(Spacer(1, 0.08*inch))
    
    # Frame Range Banner - matching UI EXACTLY
    frame_range = shot.frame_range_display()
    
    frame_banner_data = [
        [
            f"{frame_range['head_start']}",
            f"{frame_range['head_frames']}",
            f"{frame_range['head_end']}",
            "●",
            f"{frame_range['shot_start']}",
            f"{frame_range['shot_frames']}",
            f"{frame_range['shot_end']}",
            "●",
            f"{frame_range['tail_start']}",
            f"{frame_range['tail_frames']}",
            f"{frame_range['tail_end']}",
        ],
        [
            '', 'HEAD HANDLES', '', '', '', 'ACTION', '', '', '', 'TAIL HANDLES', ''
        ],
        [
            '', '', '', '', f"TOTAL SCAN: {shot.total_source_frames() or 0} frames", '', '', '', '', '', ''
        ]
    ]
    
    frame_banner = Table(frame_banner_data, colWidths=[
        0.65*inch, 0.55*inch, 0.65*inch, 0.25*inch,
        0.65*inch, 0.55*inch, 0.65*inch, 0.25*inch,
        0.65*inch, 0.55*inch, 0.65*inch
    ])
    frame_banner.setStyle(TableStyle([
        # Orange boxes for counts
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor(header_color)),
        ('BACKGROUND', (5, 0), (5, 0), colors.HexColor(header_color)),
        ('BACKGROUND', (9, 0), (9, 0), colors.HexColor(header_color)),
        ('TEXTCOLOR', (1, 0), (1, 0), colors.white),
        ('TEXTCOLOR', (5, 0), (5, 0), colors.white),
        ('TEXTCOLOR', (9, 0), (9, 0), colors.white),
        ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (5, 0), (5, 0), 'Helvetica-Bold'),
        ('FONTNAME', (9, 0), (9, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (1, 0), (1, 0), 11),
        ('FONTSIZE', (5, 0), (5, 0), 11),
        ('FONTSIZE', (9, 0), (9, 0), 11),
        # Frame numbers
        ('FONTNAME', (0, 0), (-1, 0), 'Courier-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        # Labels
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, 1), 7),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor('#6c757d')),
        # Total scan
        ('SPAN', (0, 2), (-1, 2)),
        ('FONTSIZE', (0, 2), (-1, 2), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    plate_elements.append(frame_banner)
    plate_elements.append(Spacer(1, 0.12*inch))
    
    # Main content - THREE COLUMNS matching UI exactly
    # LEFT: Reference image + Camera + Color metadata (white cards with borders)
    # MIDDLE: Timecode info (white card with border)
    # RIGHT: Pull date, retime, notes (white cards with borders)
    
    left_cards = []
    
    # Reference Image Card
    ref_img = load_reference_image(shot, width=3.5*inch, height=2.3*inch)
    if ref_img:
        ref_card = Table([[ref_img]], colWidths=[3.7*inch])
        ref_card.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
            ('BACKGROUND', (0, 0), (-1, -1), colors.white),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        left_cards.append(ref_card)
        left_cards.append(Spacer(1, 0.08*inch))
    else:
        ref_placeholder = Table([['Reference']], colWidths=[3.7*inch])
        ref_placeholder.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f9fa')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#adb5bd')),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 40),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 40),
        ]))
        left_cards.append(ref_placeholder)
        left_cards.append(Spacer(1, 0.08*inch))
    
    # Camera Card
    camera_rows = [['Lens/Camera']]
    cam_data = []
    if shot.camera and shot.lens:
        cam_data.append(['Camera', shot.camera, 'Lens', shot.lens])
    if shot.focal_length and shot.t_stop:
        cam_data.append(['Focal Length', f"{shot.focal_length}mm", 'Aperture', f"T{shot.t_stop}"])
    if shot.iso and shot.resolution:
        cam_data.append(['ISO', str(shot.iso), 'Resolution', shot.resolution])
    if shot.shot_frame_rate or shot.fps:
        fps_val = shot.shot_frame_rate or str(shot.fps or '')
        cam_data.append(['FPS', fps_val, '', ''])
    if shot.cam_roll and shot.shutter_angle:
        cam_data.append(['Tape Name', shot.cam_roll, 'Shutter', str(shot.shutter_angle)])
    if shot.camera_roll and shot.camera_tilt:
        cam_data.append(['Camera Roll', f"{shot.camera_roll}°", 'Camera Tilt', f"{shot.camera_tilt}°"])
    if shot.distance:
        cam_data.append(['Distance', shot.distance, '', ''])
    
    camera_card = Table(camera_rows + cam_data, colWidths=[0.9*inch, 0.95*inch, 0.9*inch, 0.95*inch])
    camera_card.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
        ('SPAN', (0, 0), (-1, 0)),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TEXTCOLOR', (0, 1), (0, -1), colors.HexColor('#6c757d')),
        ('TEXTCOLOR', (2, 1), (2, -1), colors.HexColor('#6c757d')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('INNERGRID', (0, 1), (-1, -1), 0.5, colors.HexColor('#f0f0f0')),
    ]))
    left_cards.append(camera_card)
    left_cards.append(Spacer(1, 0.08*inch))
    
    # Color Card
    color_rows = [['Color & LUT']]
    color_data = []
    if shot.lut:
        color_data.append(['LUT Used', shot.lut, '', ''])
    if shot.color_space and shot.gamma:
        color_data.append(['Color Space', shot.color_space, 'Gamma', shot.gamma])
    if shot.codec:
        color_data.append(['Codec', shot.codec, '', ''])
    
    color_card = Table(color_rows + color_data, colWidths=[0.9*inch, 0.95*inch, 0.9*inch, 0.95*inch])
    style_list = [
        ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
        ('SPAN', (0, 0), (-1, 0)),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TEXTCOLOR', (0, 1), (0, -1), colors.HexColor('#6c757d')),
        ('TEXTCOLOR', (2, 1), (2, -1), colors.HexColor('#6c757d')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('INNERGRID', (0, 1), (-1, -1), 0.5, colors.HexColor('#f0f0f0')),
    ]
    if shot.lut:
        style_list.append(('SPAN', (1, 1), (-1, 1)))
    
    color_card.setStyle(TableStyle(style_list))
    left_cards.append(color_card)
    
    # MIDDLE: Timecode Card
    crank = shot.crank_speed or 100.0
    head_output = int((shot.head_handles or 0) / (crank / 100.0))
    tail_output = int((shot.tail_handles or 0) / (crank / 100.0))
    
    tc_data = [
        ['TC Cut In', 'TC Cut Out', 'Length'],
        [shot.source_in or '', shot.source_out or '', str(shot.duration_frames or 0)],
        ['', '', ''],
        ['TC Scan In', 'TC Scan Out', 'Total Scan'],
        [shot.tc_scan_in() or '', shot.tc_scan_out() or '', str(shot.total_source_frames() or 0)],
        ['', '', ''],
        ['Handles (Source)', 'Retime Handles (Output)', ''],
        [f"{shot.head_handles or 0}/{shot.tail_handles or 0}", f"{head_output}/{tail_output}", ''],
    ]
    
    tc_card = Table(tc_data, colWidths=[1.4*inch, 1.4*inch, 1.0*inch])
    tc_card.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#f8f9fa')),
        ('BACKGROUND', (0, 6), (-1, 6), colors.HexColor('#f8f9fa')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 3), (-1, 3), 'Helvetica-Bold'),
        ('FONTNAME', (0, 6), (-1, 6), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    
    # RIGHT: Notes Cards
    right_cards = []
    
    # Pull Date / Plate Rev Card
    pull_data = [
        ['Pull Date', 'Plate Rev'],
        [shot.pull_date.strftime('%Y-%m-%d') if shot.pull_date else '', shot.plate_rev or '']
    ]
    pull_card = Table(pull_data, colWidths=[1.65*inch, 1.65*inch])
    pull_card.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    right_cards.append(pull_card)
    right_cards.append(Spacer(1, 0.08*inch))
    
    # Retime / Resize Card
    retime_data = [
        ['Retime', 'Resize/Reposition'],
        [shot.retime_notes or '', shot.resize_reposition or '']
    ]
    retime_card = Table(retime_data, colWidths=[1.65*inch, 1.65*inch])
    retime_card.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    right_cards.append(retime_card)
    right_cards.append(Spacer(1, 0.08*inch))
    
    # Element Notes Card
    notes_para = Paragraph(shot.element_notes or '', ParagraphStyle('notes', fontSize=8, leading=10))
    notes_card = Table([['Element Notes'], [notes_para]], colWidths=[3.3*inch])
    notes_card.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    right_cards.append(notes_card)
    
    # Combine all three columns
    main_content = Table([[left_cards, tc_card, right_cards]], colWidths=[3.9*inch, 3.9*inch, 3.5*inch])
    main_content.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    plate_elements.append(main_content)
    
    # Wrap in KeepTogether and add to elements
    elements.append(KeepTogether(plate_elements))
    
    # Divider after plate
    elements.append(Spacer(1, 0.1*inch))
    divider = Table([['']], colWidths=[11*inch])
    divider.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, -1), 2, colors.HexColor('#dee2e6')),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(divider)

def calculate_frame_range(shot):
    """Use the Shot model's existing frame_range_display method"""
    return shot.frame_range_display()

def generate_camera_section(shot):
    """Generate camera metadata section"""
    camera_data = [['Lens/Camera']]
    
    rows = []
    if shot.camera: rows.append(['Camera', shot.camera])
    if shot.lens: rows.append(['Lens', shot.lens])
    if shot.focal_length: rows.append(['Focal Length', f"{shot.focal_length}mm"])
    if shot.t_stop: rows.append(['Aperture', f"T{shot.t_stop}"])
    if shot.iso: rows.append(['ISO', str(shot.iso)])
    if shot.resolution: rows.append(['Resolution', shot.resolution])
    if shot.shot_frame_rate or shot.fps: rows.append(['FPS', shot.shot_frame_rate or str(shot.fps or '')])
    if shot.cam_roll: rows.append(['Tape Name', shot.cam_roll])
    if shot.shutter_angle: rows.append(['Shutter', str(shot.shutter_angle)])
    if shot.camera_roll: rows.append(['Camera Roll', f"{shot.camera_roll}°"])
    if shot.camera_tilt: rows.append(['Camera Tilt', f"{shot.camera_tilt}°"])
    if shot.distance: rows.append(['Distance', shot.distance])
    
    # Build in 2 columns
    grid = []
    for i in range(0, len(rows), 2):
        if i + 1 < len(rows):
            grid.append([rows[i][0], rows[i][1], rows[i+1][0], rows[i+1][1]])
        else:
            grid.append([rows[i][0], rows[i][1], '', ''])
    
    camera_table = Table(camera_data + grid, colWidths=[0.95*inch, 1.05*inch, 0.95*inch, 1.05*inch])
    camera_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
        ('SPAN', (0, 0), (-1, 0)),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('TEXTCOLOR', (0, 1), (0, -1), colors.HexColor('#6c757d')),
        ('TEXTCOLOR', (2, 1), (2, -1), colors.HexColor('#6c757d')),
    ]))
    
    return camera_table

def generate_color_section(shot):
    """Generate color & LUT metadata section"""
    color_data = [['Color & LUT']]
    
    rows = []
    if shot.lut: rows.append(['LUT Used', shot.lut])
    if shot.color_space: rows.append(['Color Space', shot.color_space])
    if shot.gamma: rows.append(['Gamma', shot.gamma])
    if shot.codec: rows.append(['Codec', shot.codec])
    
    # Build in 2 columns (except LUT which spans)
    grid = []
    lut_row = None
    if shot.lut:
        lut_row = ['LUT Used', shot.lut, '', '']
        rows = rows[1:]  # Remove LUT from rows
    
    for i in range(0, len(rows), 2):
        if i + 1 < len(rows):
            grid.append([rows[i][0], rows[i][1], rows[i+1][0], rows[i+1][1]])
        else:
            grid.append([rows[i][0], rows[i][1], '', ''])
    
    if lut_row:
        grid.insert(0, lut_row)
    
    color_table = Table(color_data + grid, colWidths=[0.95*inch, 1.05*inch, 0.95*inch, 1.05*inch])
    style_list = [
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
        ('SPAN', (0, 0), (-1, 0)),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('TEXTCOLOR', (0, 1), (0, -1), colors.HexColor('#6c757d')),
        ('TEXTCOLOR', (2, 1), (2, -1), colors.HexColor('#6c757d')),
    ]
    
    # Span LUT row if exists
    if lut_row:
        style_list.append(('SPAN', (1, 1), (-1, 1)))
    
    color_table.setStyle(TableStyle(style_list))
    
    return color_table

def generate_timecode_section(shot):
    """Generate timecode section"""
    # Calculate retime handles (output)
    crank = shot.crank_speed or 100.0
    head_output = int((shot.head_handles or 0) / (crank / 100.0))
    tail_output = int((shot.tail_handles or 0) / (crank / 100.0))
    
    tc_data = [
        ['TC Cut In', 'TC Cut Out', 'Length'],
        [shot.source_in or '', shot.source_out or '', str(shot.duration_frames or 0)],
        ['', '', ''],
        ['TC Scan In', 'TC Scan Out', 'Total Scan'],
        [shot.tc_scan_in() or '', shot.tc_scan_out() or '', str(shot.total_source_frames() or 0)],
        ['', '', ''],
        ['Handles (Source)', 'Retime Handles (Output)', ''],
        [f"{shot.head_handles or 0}/{shot.tail_handles or 0}", 
         f"{head_output}/{tail_output}", ''],
    ]
    
    tc_table = Table(tc_data, colWidths=[1.3*inch, 1.3*inch, 1.0*inch])
    tc_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#f8f9fa')),
        ('BACKGROUND', (0, 6), (-1, 6), colors.HexColor('#f8f9fa')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 3), (-1, 3), 'Helvetica-Bold'),
        ('FONTNAME', (0, 6), (-1, 6), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    
    return [tc_table]

def generate_notes_section(shot):
    """Generate notes section"""
    notes_col = []
    
    # Pull date and plate rev
    pull_data = [
        ['Pull Date', 'Plate Rev'],
        [shot.pull_date.strftime('%Y-%m-%d') if shot.pull_date else '', shot.plate_rev or '']
    ]
    pull_table = Table(pull_data, colWidths=[1.65*inch, 1.65*inch])
    pull_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    notes_col.append(pull_table)
    notes_col.append(Spacer(1, 0.08*inch))
    
    # Retime and Resize
    retime_data = [
        ['Retime', 'Resize/Reposition'],
        [shot.retime_notes or '', shot.resize_reposition or '']
    ]
    retime_table = Table(retime_data, colWidths=[1.65*inch, 1.65*inch])
    retime_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
    ]))
    notes_col.append(retime_table)
    notes_col.append(Spacer(1, 0.08*inch))
    
    # Element notes
    notes_data = [['Element Notes'], [shot.element_notes or '']]
    notes_para = Paragraph(shot.element_notes or '', ParagraphStyle('notes', fontSize=7, leading=9))
    notes_table = Table([['Element Notes'], [notes_para]], colWidths=[3.3*inch])
    notes_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    notes_col.append(notes_table)
    
    return notes_col

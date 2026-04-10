from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO
from models import Shot

def generate_shot_pdf(shot):
    """Generate a vendor shot sheet PDF for a single shot"""
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    
    # Container for content
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#667eea'),
        spaceAfter=20,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=10,
        spaceBefore=15,
        fontName='Helvetica-Bold'
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=11,
        leading=14
    )
    
    # Title
    elements.append(Paragraph(f"VFX SHOT SHEET", title_style))
    elements.append(Paragraph(f"{shot.clip_name} - {shot.vfx_code or 'N/A'}", heading_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Get frame range and handles
    frame_range = shot.frame_range_display()
    source_head, source_tail = shot.source_handles()
    
    # Frame Range Display - THE MOST IMPORTANT INFO
    frame_range_data = [
        ['FRAME RANGE - STARTING FRAME: {}'.format(frame_range['shot_start'])],
    ]
    
    frame_range_table = Table(frame_range_data, colWidths=[6.5*inch])
    frame_range_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#667eea')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 14),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(frame_range_table)
    elements.append(Spacer(1, 0.1*inch))
    
    # Visual Frame Display
    frame_visual = f"{frame_range['head_start']} [{frame_range['head_frames']}] {frame_range['head_end']}    {frame_range['shot_start']} [{frame_range['shot_frames']}] {frame_range['shot_end']}    {frame_range['tail_start']} [{frame_range['tail_frames']}] {frame_range['tail_end']}"
    
    frame_visual_data = [[frame_visual]]
    frame_visual_table = Table(frame_visual_data, colWidths=[6.5*inch])
    frame_visual_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0f0f0')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Courier-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(frame_visual_table)
    elements.append(Spacer(1, 0.05*inch))
    
    # Labels
    labels_data = [["   Head Handles ─┘      └───── Shot ─────┘      └─ Tail Handles ─┘"]]
    labels_table = Table(labels_data, colWidths=[6.5*inch])
    labels_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Courier'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#7f8c8d')),
    ]))
    elements.append(labels_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Timecode Information
    elements.append(Paragraph("TIMECODE INFORMATION", heading_style))
    
    tc_data = [
        ['TC Cut In:', f"{shot.source_in} to {shot.source_out}"],
        ['TC Scan In:', f"{shot.tc_scan_in()} to {shot.tc_scan_out()}"],
        ['Range:', f"{frame_range['head_start']}-{frame_range['total_end']}"],
        ['Total Scan:', f"{shot.total_source_frames()} frames (source for vendor)"],
    ]
    
    tc_table = Table(tc_data, colWidths=[2*inch, 4.5*inch])
    tc_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f9fa')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(tc_table)
    elements.append(Spacer(1, 0.2*inch))
    
    # Frame Counts
    elements.append(Paragraph("FRAME INFORMATION", heading_style))
    
    frame_data = [
        ['Length:', f"{shot.duration_frames} frames (output)"],
        ['Handles:', f"{shot.head_handles}/{shot.tail_handles} (output) > {source_head}/{source_tail} (source)"],
    ]
    
    if shot.crank_speed != 100.0:
        frame_data.append(['Source Length:', f"{shot.source_frames_needed()} frames @ {shot.crank_speed}%"])
        frame_data.append(['RETIME:', f"{shot.crank_speed}% - Vendor receives {shot.source_frames_needed()} source frames"])
    
    frame_table = Table(frame_data, colWidths=[2*inch, 4.5*inch])
    frame_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f9fa')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    
    # Highlight retime rows if present
    if shot.crank_speed != 100.0:
        frame_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 2), (-1, 3), colors.HexColor('#fff3cd')),
            ('TEXTCOLOR', (0, 3), (-1, 3), colors.HexColor('#856404')),
        ]))
    
    elements.append(frame_table)
    elements.append(Spacer(1, 0.2*inch))
    
    # VFX Details
    elements.append(Paragraph("VFX DETAILS", heading_style))
    
    vfx_data = [
        ['Event Number:', str(shot.event_number)],
        ['VFX Code:', shot.vfx_code or 'N/A'],
        ['VFX Element:', shot.vfx_element or 'N/A'],
        ['Version:', f"v{shot.version}"],
        ['Plate Type:', shot.plate_type or 'N/A'],
        ['Vendor:', shot.vendor or 'N/A'],
        ['Status:', shot.status],
        ['Cam Roll:', shot.cam_roll or 'N/A'],
        ['FPS:', str(shot.fps)],
    ]
    
    vfx_table = Table(vfx_data, colWidths=[2*inch, 4.5*inch])
    vfx_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f9fa')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(vfx_table)
    
    # Notes
    if shot.notes:
        elements.append(Spacer(1, 0.2*inch))
        elements.append(Paragraph("NOTES", heading_style))
        elements.append(Paragraph(shot.notes, normal_style))
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_metadata_pdf(shots):
    """Generate PDF with metadata for selected shots - individual plate layout"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    from reportlab.lib.units import inch
    from io import BytesIO
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=(A4[1], A4[0]), topMargin=0.5*inch, bottomMargin=0.5*inch, leftMargin=0.5*inch, rightMargin=0.5*inch)
    
    # Get styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#667eea'),
        spaceAfter=20
    )
    
    plate_title_style = ParagraphStyle(
        'PlateTitle',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=15,
        spaceBefore=20
    )
    
    story = []
    
    # Main title
    story.append(Paragraph("Shot Metadata Report", title_style))
    story.append(Spacer(1, 20))
    
    # Process each shot individually
    for i, shot in enumerate(shots):
        if i > 0:  # Add page break between shots
            from reportlab.platypus import PageBreak
            story.append(PageBreak())
        
        # Plate title
        story.append(Paragraph(f"<b>{shot.clip_name}</b>", plate_title_style))
        
        # Create metadata grid - 3 columns of metadata
        page_width = A4[1] - 2*inch
        col_width = page_width / 3
        
        # Build metadata rows dynamically - only include fields with actual data
        all_fields = [
            # Format: (label, value)
            ("Camera Type", shot.camera),
            ("Camera Manufacturer", shot.camera_manufacturer),
            ("Camera Serial #", shot.camera_serial),
            ("Lens Type", shot.lens),
            ("Focal Length", shot.focal_length),
            ("Aperture", shot.t_stop),
            ("ISO", shot.iso),
            ("Shutter Angle", shot.shutter_angle),
            ("Shutter Speed", shot.shutter_speed),
            ("White Point", shot.white_balance),
            ("Distance", shot.distance),
            ("ND Filter", shot.nd_filter),
            ("Camera Tilt", shot.camera_tilt),
            ("Camera Roll", shot.camera_roll),
            ("Frame Rate", shot.shot_frame_rate),
            ("LUT", shot.lut),
            ("Resolution", shot.resolution),
            ("Codec", shot.codec),
            ("Color Space", shot.color_space),
            ("Gamma", shot.gamma),
            ("Start TC", shot.start_tc),
            ("End TC", shot.end_tc),
            ("Total Frames", shot.total_frames),
            ("Start Frame", shot.start_frame),
            ("End Frame", shot.end_frame),
        ]
        
        # Filter out empty/None values and format into rows of 3
        fields_with_data = [f"{label}: {value}" for label, value in all_fields if value and str(value).strip() and str(value).upper() != 'N/A']
        
        # Build rows of 3 columns - pad to 3 for consistent layout
        metadata_data = []
        for i in range(0, len(fields_with_data), 3):
            row = fields_with_data[i:i+3]
            # Pad to 3 columns
            while len(row) < 3:
                row.append("")
            metadata_data.append(row)
        
        # If no data at all, add a message
        if not metadata_data:
            metadata_data = [["No metadata available", "", ""]]
        
        # Create table with fixed widths
        metadata_table = Table(metadata_data, colWidths=[col_width, col_width, col_width])
        
        # Build style - hide borders for empty cells
        style_commands = [
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.HexColor('#f8f9fa'), colors.white]),
        ]
        
        # Add borders only around non-empty cells
        for row_idx, row in enumerate(metadata_data):
            for col_idx, cell in enumerate(row):
                if cell:  # Only add border if cell has content
                    style_commands.append(('BOX', (col_idx, row_idx), (col_idx, row_idx), 1, colors.HexColor('#ddd')))
        
        metadata_table.setStyle(TableStyle(style_commands))
        
        # Keep each shot's data together
        shot_section = KeepTogether([metadata_table])
        story.append(shot_section)
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer


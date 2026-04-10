"""
Implementation script for:
1. Internal Notes feature (expandable panel on VFX code header)
2. Batch Changes feature (link multiple VFX codes for simultaneous editing)
"""

# Step 1: Update models.py to add internal_notes column
print("Step 1: Updating models.py...")
with open('models.py', 'r') as f:
    models_content = f.read()

# Add internal_notes field after vfx_editorial_note
old_section = """    # VFX-level notes
    scope_of_work = db.Column(db.Text)
    vfx_editorial_note = db.Column(db.Text)
    reference_image = db.Column(db.String(500))"""

new_section = """    # VFX-level notes
    scope_of_work = db.Column(db.Text)
    vfx_editorial_note = db.Column(db.Text)
    internal_notes = db.Column(db.Text)  # Internal notes - NOT exported to PDFs
    reference_image = db.Column(db.String(500))"""

if 'internal_notes' not in models_content:
    models_content = models_content.replace(old_section, new_section)
    with open('models.py', 'w') as f:
        f.write(models_content)
    print("✓ Added internal_notes to VFXCode model")
else:
    print("  internal_notes already exists in models.py")

# Step 2: Update HTML template
print("\nStep 2: Updating templates/index_new.html...")
with open('templates/index_new.html', 'r') as f:
    html_content = f.read()

# First, add CSS for the notes panel and batch changes
css_insertion_point = ".vfx-code-container {"
css_to_add = """.vfx-code-container {
    position: relative; /* For absolute positioning of notes panel */
}

/* Internal Notes Panel */
.notes-tab {
    position: absolute;
    right: 0;
    top: 50%;
    transform: translateY(-50%);
    background: #6c757d;
    color: white;
    padding: 0.5rem 0.75rem;
    cursor: pointer;
    border-radius: 6px 0 0 6px;
    font-size: 0.85rem;
    font-weight: 600;
    z-index: 10;
    transition: background 0.3s;
}

.notes-tab:hover {
    background: #5a6268;
}

.notes-panel {
    position: absolute;
    right: 0;
    top: 0;
    bottom: 0;
    width: 350px;
    background: white;
    border-left: 3px solid #6c757d;
    transform: translateX(100%);
    transition: transform 0.3s ease;
    z-index: 5;
    display: flex;
    flex-direction: column;
    box-shadow: -2px 0 10px rgba(0,0,0,0.1);
}

.notes-panel.open {
    transform: translateX(0);
}

.notes-panel-header {
    padding: 1rem;
    background: #6c757d;
    color: white;
    font-weight: 700;
    font-size: 1rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.notes-panel-close {
    cursor: pointer;
    font-size: 1.5rem;
    line-height: 1;
    padding: 0 0.5rem;
}

.notes-panel-content {
    flex: 1;
    padding: 1rem;
    overflow-y: auto;
}

.notes-panel-content textarea {
    width: 100%;
    height: 100%;
    min-height: 200px;
    border: 2px solid #ddd;
    border-radius: 6px;
    padding: 0.75rem;
    font-size: 0.9rem;
    resize: vertical;
}

/* Batch Changes - Yellow highlight for linked fields */
.batch-linked {
    background-color: #fff3cd !important;
    border-color: #ffc107 !important;
}

.vfx-code-checkbox:checked ~ * .batch-linkable {
    background-color: #fff3cd;
}

/* VFX Code Container Styles */
.vfx-code-container {"""

if ".notes-tab {" not in html_content:
    html_content = html_content.replace(css_insertion_point, css_to_add)
    print("✓ Added CSS for notes panel and batch changes")
else:
    print("  CSS already contains notes panel styles")

# Add the notes tab and panel HTML to VFX code header
notes_html = """            <input type="checkbox" class="vfx-code-checkbox" value="{{ vfx_code.id }}" 
                   onchange="updateSelectionCount(); handleBatchSelection({{ vfx_code.id }}, this.checked)"
                   style="width: 24px; height: 24px; cursor: pointer;">
            <h2 class="vfx-code-title" style="flex: 1;">{{ vfx_code.vfx_code }}</h2>
            
            <!-- Internal Notes Tab -->
            <div class="notes-tab" onclick="toggleNotesPanel({{ vfx_code.id }})">
                Notes ▶
            </div>
        </div>
        
        <!-- Internal Notes Panel -->
        <div class="notes-panel" id="notes-panel-{{ vfx_code.id }}">
            <div class="notes-panel-header">
                Internal Notes
                <span class="notes-panel-close" onclick="toggleNotesPanel({{ vfx_code.id }})">×</span>
            </div>
            <div class="notes-panel-content">
                <textarea id="internal-notes-{{ vfx_code.id }}" 
                          placeholder="Internal notes (not exported to PDFs)..."
                          oninput="debouncedSaveNotes({{ vfx_code.id }})">{{ vfx_code.internal_notes or '' }}</textarea>
            </div>
        </div>"""

# Find and replace the VFX code header checkbox section
old_header = """            <input type="checkbox" class="vfx-code-checkbox" value="{{ vfx_code.id }}" onchange="updateSelectionCount()" 
                   onchange="toggleVFXCodeShots({{ vfx_code.id }}, this.checked)"
                   style="width: 24px; height: 24px; cursor: pointer;">
            <h2 class="vfx-code-title" style="flex: 1;">{{ vfx_code.vfx_code }}</h2>
        </div>"""

if "toggleNotesPanel" not in html_content:
    html_content = html_content.replace(old_header, notes_html)
    print("✓ Added notes tab and panel HTML")
else:
    print("  Notes panel HTML already exists")

# Add batch-linkable class to TO#, TO Date, and Vendor fields
# Update TO# field
old_to_num = """                    <div class="vfx-info-field" style="margin-bottom: 1rem;">
                        <label>TO #</label>
                        <input type="text" value="{{ vfx_code.turnover_number or '' }}" 
                               onblur="updateVFXField({{ vfx_code.id }}, 'turnover_number', this.value)">
                    </div>"""

new_to_num = """                    <div class="vfx-info-field" style="margin-bottom: 1rem;">
                        <label>TO #</label>
                        <input type="text" class="batch-linkable batch-to-num" 
                               data-vfx-id="{{ vfx_code.id }}"
                               value="{{ vfx_code.turnover_number or '' }}" 
                               onblur="updateVFXField({{ vfx_code.id }}, 'turnover_number', this.value)"
                               oninput="handleBatchInput('turnover_number', this.value)">
                    </div>"""

if 'class="batch-linkable batch-to-num"' not in html_content:
    html_content = html_content.replace(old_to_num, new_to_num)
    print("✓ Added batch-linkable to TO# field")

# Update TO Date field
old_to_date = """                    <div class="vfx-info-field" style="margin-bottom: 1rem;">
                        <label>TO Date</label>
                        <input type="date" value="{{ vfx_code.turnover_date or '' }}"
                               onchange="updateVFXField({{ vfx_code.id }}, 'turnover_date', this.value)">
                    </div>"""

new_to_date = """                    <div class="vfx-info-field" style="margin-bottom: 1rem;">
                        <label>TO Date</label>
                        <input type="date" class="batch-linkable batch-to-date"
                               data-vfx-id="{{ vfx_code.id }}"
                               value="{{ vfx_code.turnover_date or '' }}"
                               onchange="updateVFXField({{ vfx_code.id }}, 'turnover_date', this.value); handleBatchInput('turnover_date', this.value)">
                    </div>"""

if 'class="batch-linkable batch-to-date"' not in html_content:
    html_content = html_content.replace(old_to_date, new_to_date)
    print("✓ Added batch-linkable to TO Date field")

# Update Vendor fields
old_vendors = """                    <div class="vfx-info-field">
                        <label>Vendor(s)</label>
                        <div class="vendor-inputs">
                            <input type="text" placeholder="Vendor 1" value="{{ vfx_code.vendor_1 or '' }}"
                                   onblur="updateVFXField({{ vfx_code.id }}, 'vendor_1', this.value)">
                            <input type="text" placeholder="Vendor 2" value="{{ vfx_code.vendor_2 or '' }}"
                                   onblur="updateVFXField({{ vfx_code.id }}, 'vendor_2', this.value)">
                            <input type="text" placeholder="Vendor 3" value="{{ vfx_code.vendor_3 or '' }}"
                                   onblur="updateVFXField({{ vfx_code.id }}, 'vendor_3', this.value)">
                            <input type="text" placeholder="Vendor 4" value="{{ vfx_code.vendor_4 or '' }}"
                                   onblur="updateVFXField({{ vfx_code.id }}, 'vendor_4', this.value)">
                        </div>
                    </div>"""

new_vendors = """                    <div class="vfx-info-field">
                        <label>Vendor(s)</label>
                        <div class="vendor-inputs">
                            <input type="text" class="batch-linkable batch-vendor-1" 
                                   data-vfx-id="{{ vfx_code.id }}"
                                   placeholder="Vendor 1" value="{{ vfx_code.vendor_1 or '' }}"
                                   onblur="updateVFXField({{ vfx_code.id }}, 'vendor_1', this.value)"
                                   oninput="handleBatchInput('vendor_1', this.value)">
                            <input type="text" class="batch-linkable batch-vendor-2"
                                   data-vfx-id="{{ vfx_code.id }}"
                                   placeholder="Vendor 2" value="{{ vfx_code.vendor_2 or '' }}"
                                   onblur="updateVFXField({{ vfx_code.id }}, 'vendor_2', this.value)"
                                   oninput="handleBatchInput('vendor_2', this.value)">
                            <input type="text" class="batch-linkable batch-vendor-3"
                                   data-vfx-id="{{ vfx_code.id }}"
                                   placeholder="Vendor 3" value="{{ vfx_code.vendor_3 or '' }}"
                                   onblur="updateVFXField({{ vfx_code.id }}, 'vendor_3', this.value)"
                                   oninput="handleBatchInput('vendor_3', this.value)">
                            <input type="text" class="batch-linkable batch-vendor-4"
                                   data-vfx-id="{{ vfx_code.id }}"
                                   placeholder="Vendor 4" value="{{ vfx_code.vendor_4 or '' }}"
                                   onblur="updateVFXField({{ vfx_code.id }}, 'vendor_4', this.value)"
                                   oninput="handleBatchInput('vendor_4', this.value)">
                        </div>
                    </div>"""

if 'class="batch-linkable batch-vendor-1"' not in html_content:
    html_content = html_content.replace(old_vendors, new_vendors)
    print("✓ Added batch-linkable to Vendor fields")

# Add JavaScript functions at the end of the script section
js_functions = """
// ========================================
// INTERNAL NOTES FUNCTIONALITY
// ========================================

function toggleNotesPanel(vfxId) {
    const panel = document.getElementById(`notes-panel-${vfxId}`);
    panel.classList.toggle('open');
}

// Debounced auto-save for notes
let notesDebounceTimers = {};

function debouncedSaveNotes(vfxId) {
    // Clear existing timer
    if (notesDebounceTimers[vfxId]) {
        clearTimeout(notesDebounceTimers[vfxId]);
    }
    
    // Set new timer (save after 1 second of no typing)
    notesDebounceTimers[vfxId] = setTimeout(() => {
        saveInternalNotes(vfxId);
    }, 1000);
}

function saveInternalNotes(vfxId) {
    const textarea = document.getElementById(`internal-notes-${vfxId}`);
    const notes = textarea.value;
    
    fetch(`/vfx/${vfxId}/update/field`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({internal_notes: notes})
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log(`Internal notes saved for VFX ${vfxId}`);
        }
    })
    .catch(err => console.error('Failed to save internal notes:', err));
}

// ========================================
// BATCH CHANGES FUNCTIONALITY
// ========================================

let selectedVFXCodes = new Set();

function handleBatchSelection(vfxId, isChecked) {
    if (isChecked) {
        selectedVFXCodes.add(vfxId);
    } else {
        selectedVFXCodes.delete(vfxId);
    }
    
    // Update visual indicators
    updateBatchVisuals();
    
    // Also handle the shot checkboxes (existing functionality)
    toggleVFXCodeShots(vfxId, isChecked);
}

function updateBatchVisuals() {
    // Remove batch-linked class from all fields first
    document.querySelectorAll('.batch-linkable').forEach(field => {
        field.classList.remove('batch-linked');
    });
    
    // If 2+ VFX codes selected, highlight batch-linkable fields
    if (selectedVFXCodes.size >= 2) {
        selectedVFXCodes.forEach(vfxId => {
            document.querySelectorAll(`[data-vfx-id="${vfxId}"].batch-linkable`).forEach(field => {
                field.classList.add('batch-linked');
            });
        });
    }
}

function handleBatchInput(fieldName, value) {
    // Only apply batch changes if 2+ codes are selected
    if (selectedVFXCodes.size < 2) {
        return;
    }
    
    // Update all selected VFX codes with this value
    selectedVFXCodes.forEach(vfxId => {
        // Update the field in the UI
        const targetField = document.querySelector(`[data-vfx-id="${vfxId}"].batch-${fieldName.replace('_', '-')}`);
        if (targetField && targetField.dataset.vfxId != event.target.dataset.vfxId) {
            targetField.value = value;
            // Trigger the update
            updateVFXField(vfxId, fieldName, value);
        }
    });
}

"""

# Find the end of the script section and add our functions
script_end_marker = "</script>"
last_script_index = html_content.rfind(script_end_marker)

if "toggleNotesPanel" not in html_content:
    html_content = html_content[:last_script_index] + js_functions + html_content[last_script_index:]
    print("✓ Added JavaScript functions for notes and batch changes")
else:
    print("  JavaScript functions already exist")

# Write the updated HTML
with open('templates/index_new.html', 'w') as f:
    f.write(html_content)

print("\n✓ Template updated successfully!")
print("\n" + "="*50)
print("Implementation complete!")
print("="*50)
print("\nNext steps:")
print("1. Run the migration script to add internal_notes column to existing databases")
print("2. Test the application with: python3 app.py")

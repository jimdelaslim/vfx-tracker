// EDL Import with Version Control

// Check if VFX code exists when importing
async function checkVFXCode(vfxCode) {
    const response = await fetch('/check_vfx_code', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ vfx_code: vfxCode })
    });
    return await response.json();
}

// Update existing shot from import
async function updateShotFromImport(shotId, edlData) {
    const response = await fetch('/update_shot_from_import', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
            shot_id: shotId,
            edl_data: edlData
        })
    });
    return await response.json();
}

// Show confirmation dialog for updating existing shot
function showUpdateConfirmation(vfxCode, existingShot, edlData, callback) {
    const message = `VFX Code "${vfxCode}" already exists!
    
Current Version: v${existingShot.current_version}
Status: ${existingShot.status}
Turnover: ${existingShot.turnover_number || 'None'}

This will:
- Keep the original turnover number
- Update frame ranges and metadata
- Change status to "Updated"
- Increment version to v${existingShot.current_version + 1}

Continue with update?`;
    
    if (confirm(message)) {
        callback(true);
    } else {
        callback(false);
    }
}

// Prompt for manual VFX code entry
function promptForVFXCode(clipName, callback) {
    const vfxCode = prompt(`No VFX code found in clip name: "${clipName}"

Please enter VFX code:`);
    
    if (vfxCode && vfxCode.trim()) {
        callback(vfxCode.trim());
    } else {
        callback(null);
    }
}

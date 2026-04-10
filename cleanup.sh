#!/bin/bash

echo "🧹 Cleaning up vfx-tracker directory..."

# Create backup folder for old migration scripts
mkdir -p _OLD_SCRIPTS

# Move migration/debug scripts
echo "Moving old migration scripts to _OLD_SCRIPTS/..."
mv check_metadata_section.py _OLD_SCRIPTS/ 2>/dev/null
mv debug_index_project.py _OLD_SCRIPTS/ 2>/dev/null
mv debug_project_routes.py _OLD_SCRIPTS/ 2>/dev/null
mv final_polish_changes.py _OLD_SCRIPTS/ 2>/dev/null
mv force_reload_app.py _OLD_SCRIPTS/ 2>/dev/null
mv make_expanded_default_with_memory.py _OLD_SCRIPTS/ 2>/dev/null
mv make_new_index_default.py _OLD_SCRIPTS/ 2>/dev/null
mv migrate_database_schema.py _OLD_SCRIPTS/ 2>/dev/null
mv migrate_to_vfxcode_structure.py _OLD_SCRIPTS/ 2>/dev/null
mv regenerate_index_new.py _OLD_SCRIPTS/ 2>/dev/null
mv remove_duplicate_comment.py _OLD_SCRIPTS/ 2>/dev/null
mv remove_duplicate_routes.py _OLD_SCRIPTS/ 2>/dev/null
mv set_default_handles_zero.py _OLD_SCRIPTS/ 2>/dev/null
mv show_full_metadata_section.py _OLD_SCRIPTS/ 2>/dev/null
mv simple_handle_multiply.py _OLD_SCRIPTS/ 2>/dev/null
mv simplify_shot_form.py _OLD_SCRIPTS/ 2>/dev/null
mv test_update_route.py _OLD_SCRIPTS/ 2>/dev/null
mv update_edl_import.py _OLD_SCRIPTS/ 2>/dev/null
mv update_import_logic.py _OLD_SCRIPTS/ 2>/dev/null

# Move documentation files
mkdir -p _DOCS
echo "Moving documentation to _DOCS/..."
mv EDL_INTEGRATION_INSTRUCTIONS.txt _DOCS/ 2>/dev/null
mv _Project_Goal.txt _DOCS/ 2>/dev/null

# Delete old database backup
echo "Removing old database backup..."
rm instance/vfx_tracker.db.backup_before_redesign 2>/dev/null

# Keep base.html (it's used by all other templates via {% extends "base.html" %})
echo "✅ Keeping base.html (extended by other templates)"

# Delete old index.html (you're using index_new.html now)
echo "Deleting old index.html (using index_new.html now)..."
rm templates/index.html 2>/dev/null

echo ""
echo "✅ Cleanup complete!"
echo ""
echo "Summary:"
echo "  - Old scripts moved to _OLD_SCRIPTS/ (can delete this folder later)"
echo "  - Documentation moved to _DOCS/"
echo "  - Old database backup removed"
echo "  - Old index.html removed"
echo ""
echo "Your clean project structure:"
ls -la | grep -E "^d|\.py$|\.txt$"

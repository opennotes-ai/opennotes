#!/usr/bin/env bash
#
# Script to rename command files following the new naming convention
# and update command names within the files.
#
# Usage: ./scripts/rename-commands.sh

set -euo pipefail

cd "$(dirname "$0")/.."

# Define mappings: old_name:new_name
declare -a MAPPINGS=(
  "admin-config:config-admin"
  "rate-note:note-rate"
  "write-note:note-write"
  "request-note:note-request"
  "request-note-context:note-request-context"
  "view-notes:note-view"
  "notes-queue:note-queue"
  "list-requests:queue-requests"
  "status:status-bot"
)

COMMANDS_DIR="src/commands"

echo "Creating new command files with standardized names..."

for mapping in "${MAPPINGS[@]}"; do
  OLD_NAME="${mapping%%:*}"
  NEW_NAME="${mapping##*:}"

  OLD_FILE="${COMMANDS_DIR}/${OLD_NAME}.ts"
  NEW_FILE="${COMMANDS_DIR}/${NEW_NAME}.ts"

  if [ ! -f "$OLD_FILE" ]; then
    echo "  ⚠️  Skipping ${OLD_NAME} (file not found)"
    continue
  fi

  echo "  ✓ Creating ${NEW_NAME}.ts from ${OLD_NAME}.ts"

  # Copy file to new name
  cp "$OLD_FILE" "$NEW_FILE"

  # Update command name in the new file using sed
  # This updates: .setName('old-name') to .setName('new-name')
  sed -i '' "s/.setName('${OLD_NAME}')/.setName('${NEW_NAME}')/g" "$NEW_FILE"

  # Update logger references from 'old-name' to 'new-name'
  sed -i '' "s/command: '${OLD_NAME}'/command: '${NEW_NAME}'/g" "$NEW_FILE"

  # Update modal custom IDs (for commands that use modals)
  sed -i '' "s/\`${OLD_NAME}:/\`${NEW_NAME}:/g" "$NEW_FILE"
done

echo ""
echo "✅ New command files created successfully!"
echo ""
echo "Next steps:"
echo "  1. Create deprecated wrapper files for old command names"
echo "  2. Update command registration in src/bot.ts"
echo "  3. Run tests and type check"

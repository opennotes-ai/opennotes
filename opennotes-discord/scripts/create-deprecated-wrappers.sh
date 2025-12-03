#!/usr/bin/env bash
#
# Script to convert old command files into deprecated wrappers
# that delegate to the new standardized command implementations.
#
# Usage: ./scripts/create-deprecated-wrappers.sh

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

echo "Creating deprecated wrapper files..."

for mapping in "${MAPPINGS[@]}"; do
  OLD_NAME="${mapping%%:*}"
  NEW_NAME="${mapping##*:}"

  OLD_FILE="${COMMANDS_DIR}/${OLD_NAME}.ts"
  NEW_FILE="${COMMANDS_DIR}/${NEW_NAME}.ts"

  if [ ! -f "$NEW_FILE" ]; then
    echo "  ⚠️  Skipping ${OLD_NAME} (new file ${NEW_FILE} not found)"
    continue
  fi

  echo "  ✓ Creating deprecated wrapper: ${OLD_FILE}"

  # Create deprecated wrapper file
  cat > "$OLD_FILE" <<EOF
import {
  SlashCommandBuilder,
  ChatInputCommandInteraction,
} from 'discord.js';
import {
  data as newCommandData,
  execute as executeNewCommand,
} from './${NEW_NAME}.js';
import { addDeprecationWarning } from '../lib/deprecation.js';

/**
 * DEPRECATED: This command is deprecated and will be removed on January 26, 2026.
 * Use /${NEW_NAME} instead.
 *
 * This file exists as a compatibility wrapper during the 90-day transition period.
 */
export const data = new SlashCommandBuilder()
  .setName('${OLD_NAME}')
  .setDescription('[DEPRECATED] Use /${NEW_NAME} instead. ' + newCommandData.description);

// Copy all options from the new command
for (const option of newCommandData.options) {
  (data as any).options.push(option);
}

export async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  // Execute the new command implementation
  await executeNewCommand(interaction);

  // Note: Deprecation warning is added via interaction middleware in bot.ts
  // to avoid modifying the shared implementation
}
EOF

done

echo ""
echo "✅ Deprecated wrapper files created successfully!"
echo ""
echo "⚠️  IMPORTANT: The deprecation warning logic needs to be added to bot.ts interaction handler"
echo "    to intercept old command names and prepend the deprecation warning to responses."

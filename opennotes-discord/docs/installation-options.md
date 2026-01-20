# Installation Options

OpenNotes supports two installation modes based on your permission preferences.

## Minimal Installation

**6 permissions:** Send Messages, Embed Links, Use Slash Commands, View Channels, Create Public Threads, Send Messages in Threads

- Commands work in any channel
- Welcome message sent via DM to server owner
- Good for servers that prefer minimal bot permissions

## Full Installation (Recommended)

**9 permissions:** All minimal permissions + Manage Channels, Manage Messages, Manage Roles

- Dedicated `#open-notes` bot channel created automatically
- Welcome message pinned in bot channel
- Commands redirect users to bot channel for cleaner organization
- Channel permission overwrites configured for bot access

## Increasing Permissions from Minimal to Full

Server owners receive a separate DM with an "Increase permissions" link when installing with minimal permissions. Click the link to re-authorize with full permissions. The bot will automatically create the bot channel on next startup.

### Migration Note (January 2026)

If your server was previously running in full mode but now shows as minimal mode, this is because the **Manage Roles** permission was added as a new requirement for full mode. This permission enables the bot to configure channel permission overwrites for the dedicated bot channel.

To restore full functionality, re-authorize the bot using the "Increase permissions" link that the server owner will receive via DM. The bot will then have all 9 required permissions and can create or configure the dedicated bot channel.

## Permission Details

| Permission | Minimal | Full | Purpose |
|------------|---------|------|---------|
| Send Messages | ✓ | ✓ | Core messaging |
| Embed Links | ✓ | ✓ | Rich displays |
| Use Slash Commands | ✓ | ✓ | Primary interaction |
| View Channels | ✓ | ✓ | Channel access |
| Create Public Threads | ✓ | ✓ | Note publishing |
| Send Messages in Threads | ✓ | ✓ | Thread posting |
| Manage Channels | | ✓ | Bot channel creation |
| Manage Messages | | ✓ | Pin management |
| Manage Roles | | ✓ | Channel permission overwrites |

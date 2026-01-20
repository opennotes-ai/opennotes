# Installation Options

OpenNotes supports two installation modes based on your permission preferences.

## Minimal Installation

**6 permissions:** Send Messages, Embed Links, Use Slash Commands, View Channels, Create Public Threads, Send Messages in Threads

- Commands work in any channel
- Welcome message sent via DM to server owner
- Good for servers that prefer minimal bot permissions

## Full Installation (Recommended)

**8 permissions:** All minimal permissions + Manage Channels, Manage Messages

- Dedicated `#open-notes` bot channel created automatically
- Welcome message pinned in bot channel
- Commands redirect users to bot channel for cleaner organization

## Upgrading from Minimal to Full

Server owners receive a DM with an upgrade link when installing with minimal permissions. Click the link to re-authorize with full permissions. The bot will automatically create the bot channel on next startup.

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

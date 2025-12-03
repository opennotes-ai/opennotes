import dotenv from 'dotenv';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { readdirSync } from 'node:fs';

dotenv.config();

const DISCORD_TOKEN = process.env.DISCORD_TOKEN || process.env.DISCORD_BOT_TOKEN;
const APPLICATION_ID = process.env.DISCORD_APPLICATION_ID || process.env.DISCORD_CLIENT_ID;

if (!DISCORD_TOKEN || !APPLICATION_ID) {
  console.error('Missing DISCORD_TOKEN/DISCORD_BOT_TOKEN or DISCORD_APPLICATION_ID/DISCORD_CLIENT_ID');
  process.exit(1);
}

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const commands = [];

const commandsPath = join(__dirname, '../dist/commands');
const commandFiles = readdirSync(commandsPath).filter(file => file.endsWith('.js'));

console.log(`Found ${commandFiles.length} command files in ${commandsPath}`);

for (const file of commandFiles) {
  const filePath = join(commandsPath, file);
  const commandModule = await import(filePath);

  if ('data' in commandModule && 'execute' in commandModule) {
    commands.push(commandModule.data.toJSON());
    console.log(`  ✓ Loaded command: ${commandModule.data.name}`);
  } else {
    console.log(`  ⚠ Skipping ${file}: missing 'data' or 'execute' export`);
  }
}

async function registerCommands() {
  const url = `https://discord.com/api/v10/applications/${APPLICATION_ID}/commands`;

  try {
    console.log('Registering commands...');

    const response = await fetch(url, {
      method: 'PUT',
      headers: {
        'Authorization': `Bot ${DISCORD_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(commands),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Failed to register commands: ${response.status} - ${error}`);
    }

    const data = await response.json();
    console.log(`Successfully registered ${data.length} commands:`);
    data.forEach(cmd => {
      // Type 1 = CHAT_INPUT (slash commands), Type 2 = USER, Type 3 = MESSAGE
      const prefix = cmd.type === 1 ? '/' : '';
      const typeLabel = cmd.type === 3 ? ' (context menu)' : '';
      console.log(`  - ${prefix}${cmd.name}${typeLabel}`);
    });
  } catch (error) {
    console.error('Error registering commands:', error);
    process.exit(1);
  }
}

registerCommands();

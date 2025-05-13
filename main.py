import asyncio
import nextcord
from nextcord.ext import commands, tasks
import os
import sys
from dotenv import load_dotenv
import traceback

# Get the absolute path of the directory containing this file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COGS_DIR = os.path.join(BASE_DIR, "cogs")

# Debug token loading
load_dotenv(os.path.join(BASE_DIR, "tkn.env"))
token = os.getenv("BOT_TOKEN")
print(f"Token loaded: {'SUCCESS' if token else 'FAILED'}")
print(f"Working directory: {os.getcwd()}")
print(f"Base directory: {BASE_DIR}")
print(f"Cogs directory: {COGS_DIR}")
print(f"Cogs directory exists: {os.path.exists(COGS_DIR)}")

intents = nextcord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True  
intents.presences = True  
bot = commands.Bot(command_prefix="$", intents=intents)

async def set_rich_presence():
    activity = nextcord.Activity(
        type=nextcord.ActivityType.listening,
        name="/anime",)
    await bot.change_presence(status=nextcord.Status.dnd, activity=activity)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    await set_rich_presence()
    
    # Sync commands with Discord on startup
    print("Syncing application commands...")
    for guild in bot.guilds:
        try:
            synced = await bot.sync_application_commands(guild_id=guild.id)
            print(f"Synced {len(synced)} commands to {guild.name}")
        except Exception as e:
            print(f"Failed to sync commands to {guild.name}: {e}")

@bot.event
async def on_command_error(ctx, error):
    print(f"An error occurred: {error}")
    print(traceback.format_exc())
    await ctx.send(f"An error occurred: {error}")

@bot.event
async def on_guild_join(guild):
    """Sync commands when joining a new guild"""
    try:
        synced = await bot.sync_application_commands(guild_id=guild.id)
        print(f"Synced {len(synced)} commands to new guild: {guild.name}")
    except Exception as e:
        print(f"Failed to sync commands to {guild.name}: {e}")

async def load_cogs():

    if not os.path.exists(COGS_DIR):
        try:
            os.makedirs(COGS_DIR)
            print(f"Created cogs directory at: {COGS_DIR}")
        except Exception as e:
            print(f"Failed to create cogs directory: {e}")
            return
    
    # Load cogs directly in the cogs folder
    for filename in os.listdir(COGS_DIR):
        if filename.endswith(".py"):
            try:
                bot.load_extension(f"cogs.{filename[:-3]}")
                print(f"✅: {filename}")
            except Exception as e:
                print(f"Failed to load cog {filename}: {e}")
                print(traceback.format_exc())
    
    # Load cogs from subfolders
    for foldername in os.listdir(COGS_DIR):
        folder_path = os.path.join(COGS_DIR, foldername)
        if os.path.isdir(folder_path):
            # Make sure there's an __init__.py file
            init_file = os.path.join(folder_path, "__init__.py")
            if not os.path.exists(init_file):
                try:
                    with open(init_file, 'w') as f:
                        pass 
                    print(f"Created __init__.py in {foldername}")
                except Exception as e:
                    print(f"Failed to create __init__.py in {foldername}: {e}")
            
            for filename in os.listdir(folder_path):
                if filename.endswith(".py") and filename != "__init__.py":
                    try:
                        bot.load_extension(f"cogs.{foldername}.{filename[:-3]}")
                        print(f"✅: {foldername}/{filename}")
                    except Exception as e:
                        print(f"Failed to load cog {foldername}/{filename}: {e}")
                        print(traceback.format_exc())

if __name__ == "__main__":
    bot.loop.create_task(load_cogs())
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
    
    bot.run(token)
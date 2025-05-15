import nextcord
from nextcord.ext import commands
from nextcord import File, Embed, SlashOption, Interaction, ui, ButtonStyle
from io import BytesIO
import aiohttp
from PIL import Image
import json
import os
import sqlite3
import pathlib

class GreetingModal(ui.Modal):
    def __init__(self, title, message_type, callback_func, default_text=""):
        super().__init__(title)
        self.message_type = message_type
        self.callback_func = callback_func
        
        self.message = ui.TextInput(
            label=f"Enter your {message_type} message",
            placeholder="Use {user} for member mention, {server} for server name",
            style=nextcord.TextInputStyle.paragraph,
            default_value=default_text,
            required=True,
            max_length=1000
        )
        self.add_item(self.message)
        
        self.image_url = ui.TextInput(
            label="Image URL (optional)",
            placeholder="Leave empty to use default image",
            required=False,
            style=nextcord.TextInputStyle.short
        )
        self.add_item(self.image_url)

    async def callback(self, interaction: Interaction):
        await self.callback_func(interaction, self.message_type, self.message.value, self.image_url.value)

class MemberEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        
        # Ensure data directory exists
        data_dir = pathlib.Path("data")
        data_dir.mkdir(exist_ok=True)
        
        self.db_file = "data/greetings.db"
        self._setup_database()
        self._load_settings()

    def cog_unload(self):
        if self.session and not self.session.closed:
            self.bot.loop.create_task(self.session.close())

    def _setup_database(self):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS greeting_channels (
            guild_id TEXT PRIMARY KEY,
            channel_id TEXT
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS greeting_messages (
            guild_id TEXT,
            type TEXT,
            message TEXT,
            image_url TEXT,
            PRIMARY KEY (guild_id, type)
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def _load_settings(self):
        self.greeting_channels = {}  
        self.greeting_messages = {}  
        
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute("SELECT guild_id, channel_id FROM greeting_channels")
        for guild_id, channel_id in cursor.fetchall():
            self.greeting_channels[guild_id] = channel_id
        
        cursor.execute("SELECT guild_id, type, message, image_url FROM greeting_messages")
        for guild_id, msg_type, message, image_url in cursor.fetchall():
            if guild_id not in self.greeting_messages:
                self.greeting_messages[guild_id] = {}
            
            self.greeting_messages[guild_id][msg_type] = {
                "message": message,
                "image_url": image_url
            }
        
        conn.close()
    
    def _save_channel(self, guild_id, channel_id):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT OR REPLACE INTO greeting_channels (guild_id, channel_id) VALUES (?, ?)",
            (str(guild_id), str(channel_id))
        )
        
        conn.commit()
        conn.close()
        
        self.greeting_channels[str(guild_id)] = str(channel_id)
    
    def _save_message(self, guild_id, message_type, message, image_url):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT OR REPLACE INTO greeting_messages (guild_id, type, message, image_url) VALUES (?, ?, ?, ?)",
            (str(guild_id), message_type, message, image_url)
        )
        
        conn.commit()
        conn.close()
        
        if str(guild_id) not in self.greeting_messages:
            self.greeting_messages[str(guild_id)] = {}
        
        self.greeting_messages[str(guild_id)][message_type] = {
            "message": message,
            "image_url": image_url
        }
    
    def _get_message(self, guild_id, message_type):
        guild_id = str(guild_id)
        
        defaults = {
            "welcome": {
                "message": "Welcome {user} to {server}! We're happy to have you here.",
                "image_url": ""
            },
            "goodbye": {
                "message": "Goodbye {user}! We'll miss you in {server}.",
                "image_url": ""
            }
        }
        
        if (guild_id not in self.greeting_messages or 
            message_type not in self.greeting_messages[guild_id]):
            return defaults[message_type]
        
        return self.greeting_messages[guild_id][message_type]

    @nextcord.slash_command(name="greetings", description="Configure welcome and goodbye messages")
    async def greetings(self, interaction: nextcord.Interaction):
        pass

    @greetings.subcommand(name="channel", description="Set the welcome/goodbye message channel")
    @commands.has_permissions(administrator=True)
    async def set_greetings_channel(
        self, 
        interaction: nextcord.Interaction, 
        channel: nextcord.abc.GuildChannel = SlashOption(
            name="channel",
            description="The channel to send welcome and goodbye messages to",
            required=True
        )
    ):
        if not isinstance(channel, nextcord.TextChannel):
            await interaction.response.send_message("Please select a text channel!", ephemeral=True)
            return
        
        guild_id = interaction.guild.id
        self._save_channel(guild_id, channel.id)
        
        await interaction.response.send_message(
            f"Welcome and goodbye messages will now be sent to {channel.mention}!", 
            ephemeral=True
        )

    @greetings.subcommand(name="welcome", description="Customize welcome message")
    @commands.has_permissions(administrator=True)
    async def customize_welcome(self, interaction: nextcord.Interaction):
        guild_id = interaction.guild.id
        current_msg = self._get_message(guild_id, "welcome")
        
        modal = GreetingModal(
            "Customize Welcome Message", 
            "welcome", 
            self.save_greeting_message,
            default_text=current_msg["message"]
        )
        
        await interaction.response.send_modal(modal)

    @greetings.subcommand(name="goodbye", description="Customize goodbye message")
    @commands.has_permissions(administrator=True)
    async def customize_goodbye(self, interaction: nextcord.Interaction):
        guild_id = interaction.guild.id
        current_msg = self._get_message(guild_id, "goodbye")
        
        modal = GreetingModal(
            "Customize Goodbye Message", 
            "goodbye", 
            self.save_greeting_message,
            default_text=current_msg["message"]
        )
        
        await interaction.response.send_modal(modal)

    @greetings.subcommand(name="test", description="Test the welcome or goodbye message")
    @commands.has_permissions(administrator=True)
    async def test_message(
        self,
        interaction: nextcord.Interaction,
        message_type: str = SlashOption(
            name="type",
            description="Message type to test",
            choices={"Welcome": "welcome", "Goodbye": "goodbye"},
            required=True
        )
    ):
        guild_id = interaction.guild.id
        
        if str(guild_id) not in self.greeting_channels:
            await interaction.response.send_message(
                "Please set a greeting channel first using `/greetings channel`!", 
                ephemeral=True
            )
            return
            
        await interaction.response.defer()
        
        member = interaction.user
        
        if message_type == "welcome":
            await self.send_welcome_message(member)
        else:
            await self.send_goodbye_message(member)
        
        await interaction.followup.send(
            f"Test {message_type} message sent to <#{self.greeting_channels[str(guild_id)]}>",
            ephemeral=True
        )

    async def save_greeting_message(self, interaction, message_type, message, image_url):
        guild_id = interaction.guild.id
        self._save_message(guild_id, message_type, message, image_url)
        
        await interaction.response.send_message(
            f"Your {message_type} message has been saved! Use `/greetings test type:{message_type}` to test it.",
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_member_join(self, member):
        await self.send_welcome_message(member)
            
    @commands.Cog.listener()
    async def on_member_remove(self, member):
        await self.send_goodbye_message(member)
    
    async def send_welcome_message(self, member):
        guild = member.guild
        guild_id = str(guild.id)
        
        if guild_id not in self.greeting_channels:
            return
            
        channel_id = self.greeting_channels[guild_id]
        channel = guild.get_channel(int(channel_id))
        
        if channel is None:
            return
            
        try:
            msg_config = self._get_message(guild_id, "welcome")
            message = msg_config["message"]
            image_url = msg_config["image_url"]
            
            message = message.replace("{user}", member.mention)
            message = message.replace("{server}", guild.name)
            
            # Get the member count for the server
            member_count = guild.member_count
            
            embed = Embed(
                title=f"Welcome to {guild.name}",
                description=message,
                color=nextcord.Color.red()
            )
            
            # Add the member count to the footer
            embed.set_footer(text=f"You are our {member_count}th member!")
            embed.set_thumbnail(url=member.display_avatar.url)
            
            # Check if a custom image URL is provided and valid
            valid_img = False
            if image_url and image_url.strip():
                try:
                    # Validate image URL by attempting to fetch it
                    async with self.session.head(image_url, timeout=5) as resp:
                        if resp.status == 200:
                            embed.set_image(url=image_url)
                            valid_img = True
                except:
                    valid_img = False
            
            if not valid_img:
                # Fall back to generated image if custom URL is invalid
                welcome_image = await self.create_welcome_image(member)
                embed.set_image(url="attachment://greeting_banner.png")
                
                await channel.send(
                    embed=embed,
                    file=File(welcome_image, filename="greeting_banner.png")
                )
            else:
                await channel.send(embed=embed)
            
        except Exception as e:
            print(f"Error sending welcome message: {e}")
    
    async def send_goodbye_message(self, member):
        guild = member.guild
        guild_id = str(guild.id)
        
        if guild_id not in self.greeting_channels:
            return
            
        channel_id = self.greeting_channels[guild_id]
        channel = guild.get_channel(int(channel_id))
        
        if channel is None:
            return
            
        try:
            msg_config = self._get_message(guild_id, "goodbye")
            message = msg_config["message"]
            image_url = msg_config["image_url"]
            
            message = message.replace("{user}", member.mention)
            message = message.replace("{server}", guild.name)
            
            embed = Embed(
                title=f"Goodbye from {guild.name}",
                description=message,
                color=nextcord.Color.red()
            )
            
            # Add current member count to footer after someone left
            member_count = guild.member_count
            embed.set_footer(text=f"We now have {member_count} members")
            embed.set_thumbnail(url=member.display_avatar.url)
            
            # Check if a custom image URL is provided and valid
            valid_img = False
            if image_url and image_url.strip():
                try:
                    # Validate image URL by attempting to fetch it
                    async with self.session.head(image_url, timeout=5) as resp:
                        if resp.status == 200:
                            embed.set_image(url=image_url)
                            valid_img = True
                except:
                    valid_img = False
            
            if not valid_img:
                # Fall back to generated image if custom URL is invalid
                goodbye_image = await self.create_goodbye_image(member)
                embed.set_image(url="attachment://greeting_banner.png")
                
                await channel.send(
                    embed=embed,
                    file=File(goodbye_image, filename="greeting_banner.png")
                )
            else:
                await channel.send(embed=embed)
            
        except Exception as e:
            print(f"Error sending goodbye message: {e}")

    async def create_welcome_image(self, member):
        try:
            background_image_path = "assets/welcome_banner.jpg"
            if not os.path.exists(background_image_path):
                return await self.create_default_greeting_image(member, "welcome")
                
            return await self.create_greeting_image(member, background_image_path)
        except Exception as e:
            print(f"Error creating welcome image: {e}")
            return await self.create_default_greeting_image(member, "welcome")

    async def create_goodbye_image(self, member):
        try:
            background_image_path = "assets/goodbye_banner.jpg"
            if not os.path.exists(background_image_path):
                return await self.create_default_greeting_image(member, "goodbye")
                
            return await self.create_greeting_image(member, background_image_path)
        except Exception as e:
            print(f"Error creating goodbye image: {e}")
            return await self.create_default_greeting_image(member, "goodbye")

    async def create_greeting_image(self, member, background_path):
        try:
            img = Image.open(background_path)
            img = img.resize((600, 200))  

            # Get user's profile pic
            avatar_url = member.display_avatar.url
            avatar = await self.get_avatar_image(avatar_url)

            # Make the avatar circular
            mask = Image.new("L", avatar.size, 0)
            from PIL import ImageDraw
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0, avatar.size[0], avatar.size[1]), fill=255)
            avatar.putalpha(mask)

            # Position the avatar in the center
            bg_width, bg_height = img.size
            avatar_width, avatar_height = avatar.size
            avatar_position = ((bg_width - avatar_width) // 2, (bg_height - avatar_height) // 2)

            # Put the avatar on top
            transparent = Image.new("RGBA", img.size, (0, 0, 0, 0))
            transparent.paste(avatar, avatar_position, avatar)
            
            # Make sure background supports transparency
            if img.mode != "RGBA":
                img = img.convert("RGBA")
                
            # Merge the images
            final_img = Image.alpha_composite(img, transparent)
            byte_io = BytesIO()
            final_img.save(byte_io, "PNG")
            byte_io.seek(0)
            
            return byte_io
        except Exception as e:
            print(f"Error in create_greeting_image: {e}")
            return await self.create_default_greeting_image(member, "greeting")

    async def create_default_greeting_image(self, member, message_type):
        try:
            if message_type == "welcome":
                bg_color = (67, 181, 129)  # Discord green
            else:
                bg_color = (240, 71, 71)  # Discord red
            
            background = Image.new("RGBA", (600, 200), bg_color)
            
            # Get user's profile pic
            avatar_url = member.display_avatar.url
            avatar = await self.get_avatar_image(avatar_url)

            # Make the avatar circular
            mask = Image.new("L", avatar.size, 0)
            from PIL import ImageDraw
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0, avatar.size[0], avatar.size[1]), fill=255)
            avatar.putalpha(mask)

            # Position the avatar in the center
            bg_width, bg_height = background.size
            avatar_width, avatar_height = avatar.size
            avatar_position = ((bg_width - avatar_width) // 2, (bg_height - avatar_height) // 2)

            # Put the avatar on the background
            background.paste(avatar, avatar_position, avatar)
            
            # Save the image
            byte_io = BytesIO()
            background.save(byte_io, "PNG")
            byte_io.seek(0)
            
            return byte_io
        except Exception as e:
            print(f"Error in default greeting image: {e}")
            # Last-ditch fallback - just a gray box
            fallback = Image.new("RGB", (600, 200), (47, 49, 54))  # Discord dark theme color
            byte_io = BytesIO()
            fallback.save(byte_io, "PNG")
            byte_io.seek(0)
            return byte_io

    async def get_avatar_image(self, url):
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    avatar_data = await response.read()
                    avatar_img = Image.open(BytesIO(avatar_data))
                    
                    # Make it a good size
                    avatar_size = 100
                    avatar_img = avatar_img.resize((avatar_size, avatar_size))
                    
                    # Make sure it supports transparency
                    if avatar_img.mode != "RGBA":
                        avatar_img = avatar_img.convert("RGBA")
                        
                    return avatar_img
                else:
                    default = Image.new("RGBA", (100, 100), (128, 128, 128, 255))
                    return default
        except Exception as e:
            print(f"Error getting avatar image: {e}")
            # Use a placeholder if anything goes wrong
            default = Image.new("RGBA", (100, 100), (128, 128, 128, 255))
            return default

def setup(bot):
    bot.add_cog(MemberEvents(bot))
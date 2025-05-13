import nextcord
from nextcord.ext import commands, tasks
from nextcord import SlashOption, Interaction, ButtonStyle, ChannelType
import asyncio
import sqlite3
import time
import os
from datetime import datetime, timedelta
import traceback

# Custom UI Elements
class ChannelNameModal(nextcord.ui.Modal):
    def __init__(self, callback_func):
        super().__init__(title="Set Voice Channel Name")
        self.callback_func = callback_func
        
        self.channel_name = nextcord.ui.TextInput(
            label="Channel Name",
            placeholder="Enter a name for your voice channel",
            max_length=32,
            required=True
        )
        self.add_item(self.channel_name)
        
    async def callback(self, interaction: Interaction):
        await self.callback_func(interaction, self.channel_name.value)

class UserLimitModal(nextcord.ui.Modal):
    def __init__(self, callback_func):
        super().__init__(title="Set User Limit")
        self.callback_func = callback_func
        
        self.user_limit = nextcord.ui.TextInput(
            label="User Limit (0-99)",
            placeholder="Enter a number (0 for unlimited)",
            max_length=2,
            required=True
        )
        self.add_item(self.user_limit)
        
    async def callback(self, interaction: Interaction):
        try:
            limit = int(self.user_limit.value)
            if limit < 0 or limit > 99:
                await interaction.response.send_message("User limit must be between 0 and 99.", ephemeral=True)
                return
            await self.callback_func(interaction, limit)
        except ValueError:
            await interaction.response.send_message("Please enter a valid number.", ephemeral=True)

class VoiceChannelSetupView(nextcord.ui.View):
    def __init__(self, cog, user_id):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog
        self.user_id = user_id
        self.config = {
            "name": f"{self.cog.get_user_name(user_id)}'s Channel",
            "user_limit": 0,
            "private": False,
            "require_mic": False
        }
        
    async def on_timeout(self):
        # Handle view timeout
        for child in self.children:
            child.disabled = True
        
        # If the message still exists, update it
        if hasattr(self, 'message') and self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass

    @nextcord.ui.button(label="Create Channel", style=ButtonStyle.green, row=4)
    async def create_channel(self, button: nextcord.ui.Button, interaction: Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This setup menu is not for you.", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        
        # Check if user already has a channel
        existing_channel = await self.cog.get_user_channel(interaction.user.id)
        if existing_channel:
            await interaction.followup.send(
                f"You already have an active voice channel: {existing_channel.mention}. " +
                "Please use the `/vc edit` command to modify it or wait until it's automatically deleted.",
                ephemeral=True
            )
            return
            
        # Create the channel
        try:
            channel = await self.cog.create_voice_channel(interaction, self.config)
            
            if channel:
                # Update the message to show it's been created
                embed = nextcord.Embed(
                    title="Voice Channel Created!",
                    description=f"Your custom voice channel {channel.mention} has been created.",
                    color=nextcord.Color.green()
                )
                embed.add_field(name="Channel Settings", value=self.get_config_description(), inline=False)
                embed.add_field(name="Auto-Deletion", value="The channel will be automatically deleted after everyone leaves or if no one joins within 2 minutes.", inline=False)
                embed.set_footer(text="Use '/vc edit' to modify your channel settings")
                
                for child in self.children:
                    child.disabled = True
                
                await interaction.followup.send(
                    f"Channel created: {channel.mention}", 
                    ephemeral=True
                )
                await self.message.edit(embed=embed, view=self)
                
                # Register the channel for auto-deletion monitoring
                self.cog.register_empty_channel(channel.id, interaction.user.id, created=True)
            else:
                await interaction.followup.send(
                    "Failed to create voice channel. Please try again.",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.followup.send(
                f"An error occurred while creating your channel: {str(e)}",
                ephemeral=True
            )

    @nextcord.ui.button(label="Set Name", style=ButtonStyle.primary, row=0)
    async def set_name(self, button: nextcord.ui.Button, interaction: Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This setup menu is not for you.", ephemeral=True)
            return
            
        # Show modal for name input
        modal = ChannelNameModal(self.handle_name_change)
        await interaction.response.send_modal(modal)
    
    async def handle_name_change(self, interaction: Interaction, name: str):
        self.config["name"] = name
        await self.update_setup_message(interaction)
    
    @nextcord.ui.button(label="Set User Limit", style=ButtonStyle.primary, row=0)
    async def set_user_limit(self, button: nextcord.ui.Button, interaction: Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This setup menu is not for you.", ephemeral=True)
            return
            
        # Show modal for user limit input
        modal = UserLimitModal(self.handle_user_limit_change)
        await interaction.response.send_modal(modal)
    
    async def handle_user_limit_change(self, interaction: Interaction, limit: int):
        self.config["user_limit"] = limit
        await self.update_setup_message(interaction)
    
    @nextcord.ui.button(label="Toggle Privacy", style=ButtonStyle.primary, row=1)
    async def toggle_privacy(self, button: nextcord.ui.Button, interaction: Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This setup menu is not for you.", ephemeral=True)
            return
            
        self.config["private"] = not self.config["private"]
        await self.update_setup_message(interaction)
    
    @nextcord.ui.button(label="Toggle Soundboard", style=ButtonStyle.primary, row=1)
    async def toggle_soundboard(self, button: nextcord.ui.Button, interaction: Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This setup menu is not for you.", ephemeral=True)
            return
            
        # This feature is removed due to permission incompatibility
        await interaction.response.send_message(
            "Soundboard toggle is not available in this version.",
            ephemeral=True
        )
    
    @nextcord.ui.button(label="Toggle Mic Required", style=ButtonStyle.primary, row=2)
    async def toggle_mic(self, button: nextcord.ui.Button, interaction: Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This setup menu is not for you.", ephemeral=True)
            return
            
        self.config["require_mic"] = not self.config["require_mic"]
        await self.update_setup_message(interaction)
        
    @nextcord.ui.button(label="Cancel", style=ButtonStyle.danger, row=4)
    async def cancel(self, button: nextcord.ui.Button, interaction: Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This setup menu is not for you.", ephemeral=True)
            return
            
        for child in self.children:
            child.disabled = True
            
        await interaction.response.edit_message(view=self)
        
        # Change the embed to show cancellation
        embed = nextcord.Embed(
            title="Setup Cancelled",
            description="Voice channel setup was cancelled.",
            color=nextcord.Color.red()
        )
        await self.message.edit(embed=embed, view=None)
    
    async def update_setup_message(self, interaction: Interaction):
        embed = self.create_setup_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    def create_setup_embed(self):
        embed = nextcord.Embed(
            title="Custom Voice Channel Setup",
            description="Configure your voice channel using the buttons below.",
            color=nextcord.Color.blue()
        )
        
        embed.add_field(name="Current Configuration", value=self.get_config_description(), inline=False)
        embed.set_footer(text="Click 'Create Channel' when you're ready!")
        
        return embed
    
    def get_config_description(self):
        return (
            f"**Name:** {self.config['name']}\n"
            f"**User Limit:** {self.config['user_limit'] if self.config['user_limit'] > 0 else 'Unlimited'}\n"
            f"**Privacy:** {'Private' if self.config['private'] else 'Public'}\n"
            f"**Microphone Required:** {'Yes' if self.config['require_mic'] else 'No'}"
        )

class VoiceChannelEditView(nextcord.ui.View):
    def __init__(self, cog, user_id, channel_id):
        super().__init__(timeout=180)  # 3 minute timeout
        self.cog = cog
        self.user_id = user_id
        self.channel_id = channel_id
        
        # Load current settings from the channel
        self.load_current_settings()
    
    def load_current_settings(self):
        channel = self.cog.bot.get_channel(self.channel_id)
        if not channel:
            return
            
        self.config = {
            "name": channel.name,
            "user_limit": channel.user_limit or 0,
            "private": not channel.permissions_for(channel.guild.default_role).connect,
            "require_mic": not channel.permissions_for(channel.guild.default_role).use_voice_activation
        }
        
    async def on_timeout(self):
        # Handle view timeout
        for child in self.children:
            child.disabled = True
        
        if hasattr(self, 'message') and self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass
    
    @nextcord.ui.button(label="Save Changes", style=ButtonStyle.green, row=4)
    async def save_changes(self, button: nextcord.ui.Button, interaction: Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This edit menu is not for you.", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        
        success = await self.cog.update_voice_channel(interaction, self.channel_id, self.config)
        
        if success:
            embed = nextcord.Embed(
                title="Voice Channel Updated!",
                description=f"Your custom voice channel has been updated.",
                color=nextcord.Color.green()
            )
            embed.add_field(name="New Settings", value=self.get_config_description(), inline=False)
            
            for child in self.children:
                child.disabled = True
                
            await interaction.followup.send("Channel settings updated!", ephemeral=True)
            await self.message.edit(embed=embed, view=self)
        else:
            await interaction.followup.send(
                "Failed to update voice channel. The channel may have been deleted.",
                ephemeral=True
            )
    
    @nextcord.ui.button(label="Set Name", style=ButtonStyle.primary, row=0)
    async def set_name(self, button: nextcord.ui.Button, interaction: Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This edit menu is not for you.", ephemeral=True)
            return
            
        # Show modal for name input
        modal = ChannelNameModal(self.handle_name_change)
        await interaction.response.send_modal(modal)
    
    async def handle_name_change(self, interaction: Interaction, name: str):
        self.config["name"] = name
        await self.update_edit_message(interaction)
    
    @nextcord.ui.button(label="Set User Limit", style=ButtonStyle.primary, row=0)
    async def set_user_limit(self, button: nextcord.ui.Button, interaction: Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This edit menu is not for you.", ephemeral=True)
            return
            
        # Show modal for user limit input
        modal = UserLimitModal(self.handle_user_limit_change)
        await interaction.response.send_modal(modal)
    
    async def handle_user_limit_change(self, interaction: Interaction, limit: int):
        self.config["user_limit"] = limit
        await self.update_edit_message(interaction)
    
    @nextcord.ui.button(label="Toggle Privacy", style=ButtonStyle.primary, row=1)
    async def toggle_privacy(self, button: nextcord.ui.Button, interaction: Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This edit menu is not for you.", ephemeral=True)
            return
            
        self.config["private"] = not self.config["private"]
        await self.update_edit_message(interaction)
    
    @nextcord.ui.button(label="Toggle Soundboard", style=ButtonStyle.primary, row=1)
    async def toggle_soundboard(self, button: nextcord.ui.Button, interaction: Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This edit menu is not for you.", ephemeral=True)
            return
            
        # This feature is removed due to permission incompatibility
        await interaction.response.send_message(
            "Soundboard toggle is not available in this version.",
            ephemeral=True
        )
    
    @nextcord.ui.button(label="Toggle Mic Required", style=ButtonStyle.primary, row=2)
    async def toggle_mic(self, button: nextcord.ui.Button, interaction: Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This edit menu is not for you.", ephemeral=True)
            return
            
        self.config["require_mic"] = not self.config["require_mic"]
        await self.update_edit_message(interaction)
        
    @nextcord.ui.button(label="Cancel", style=ButtonStyle.danger, row=4)
    async def cancel(self, button: nextcord.ui.Button, interaction: Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This edit menu is not for you.", ephemeral=True)
            return
            
        for child in self.children:
            child.disabled = True
            
        await interaction.response.edit_message(view=self)
        
        # Change the embed to show cancellation
        embed = nextcord.Embed(
            title="Edit Cancelled",
            description="Voice channel edit was cancelled.",
            color=nextcord.Color.red()
        )
        await self.message.edit(embed=embed, view=None)
    
    async def update_edit_message(self, interaction: Interaction):
        embed = self.create_edit_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    def create_edit_embed(self):
        embed = nextcord.Embed(
            title="Edit Voice Channel",
            description="Modify your voice channel settings using the buttons below.",
            color=nextcord.Color.blue()
        )
        
        embed.add_field(name="Current Configuration", value=self.get_config_description(), inline=False)
        embed.set_footer(text="Click 'Save Changes' when you're ready!")
        
        return embed
    
    def get_config_description(self):
        return (
            f"**Name:** {self.config['name']}\n"
            f"**User Limit:** {self.config['user_limit'] if self.config['user_limit'] > 0 else 'Unlimited'}\n"
            f"**Privacy:** {'Private' if self.config['private'] else 'Public'}\n"
            f"**Microphone Required:** {'Yes' if self.config['require_mic'] else 'No'}"
        )

class AdminSettingsView(nextcord.ui.View):
    def __init__(self, cog, user_id):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog
        self.user_id = user_id
        self.message = None
        
        # Default settings
        self.settings = {
            "category_id": None,
            "allowed_roles": [],
            "everyone_allowed": True
        }
        
        # Load current settings
        self.bot_loop = asyncio.get_event_loop()
        self.bot_loop.create_task(self.load_settings())
        
    async def load_settings(self):
        """Load current settings from the database"""
        try:
            guild_id = None
            
            # Find the user in a guild to get guild_id
            for guild in self.cog.bot.guilds:
                member = guild.get_member(self.user_id)
                if member:
                    guild_id = guild.id
                    break
            
            if not guild_id:
                return
                
            # Load settings
            conn = sqlite3.connect(self.cog.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT category_id, allowed_roles, everyone_allowed FROM guild_settings WHERE guild_id = ?", 
                          (guild_id,))
            result = cursor.fetchone()
            
            conn.close()
            
            if result:
                category_id, allowed_roles_str, everyone_allowed = result
                
                self.settings["category_id"] = category_id
                
                if allowed_roles_str:
                    self.settings["allowed_roles"] = [int(role_id) for role_id in allowed_roles_str.split(",") if role_id]
                
                self.settings["everyone_allowed"] = bool(everyone_allowed)
        except Exception as e:
            print(f"Error loading settings: {e}")
            traceback.print_exc()
            
    @nextcord.ui.button(label="Select Category", style=ButtonStyle.primary, row=0)
    async def select_category(self, button: nextcord.ui.Button, interaction: Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This admin menu is not for you.", ephemeral=True)
            return
            
        # Create dropdown for category selection
        options = []
        
        for category in interaction.guild.categories:
            options.append(nextcord.SelectOption(
                label=category.name[:100],  # Limit to 100 chars
                value=str(category.id),
                description=f"ID: {category.id}"
            ))
            
        if not options:
            await interaction.response.send_message("No categories found in this server.", ephemeral=True)
            return
            
        # Create a select menu for categories
        select = nextcord.ui.Select(
            placeholder="Select a category for voice channels",
            options=options[:25],  # Discord limits to 25 options
            min_values=1,
            max_values=1
        )
        
        async def category_callback(select_interaction):
            if select_interaction.user.id != self.user_id:
                await select_interaction.response.send_message("This selection is not for you.", ephemeral=True)
                return
                
            category_id = int(select_interaction.data["values"][0])
            self.settings["category_id"] = category_id
            
            # Update the database
            await self.save_settings(select_interaction.guild.id)
            
            # Get the category name for confirmation
            category = interaction.guild.get_channel(category_id)
            category_name = category.name if category else "Unknown"
            
            await select_interaction.response.send_message(
                f"Category set to **{category_name}** for voice channels.",
                ephemeral=True
            )
            
            # Update the admin settings embed
            embed = self.create_settings_embed(interaction.guild)
            await self.message.edit(embed=embed)
            
        select.callback = category_callback
        
        # Create a temporary view for the select menu
        view = nextcord.ui.View(timeout=60)
        view.add_item(select)
        
        await interaction.response.send_message("Select a category:", view=view, ephemeral=True)
    
    @nextcord.ui.button(label="Add Allowed Role", style=ButtonStyle.primary, row=1)
    async def add_role(self, button: nextcord.ui.Button, interaction: Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This admin menu is not for you.", ephemeral=True)
            return
            
        # Create dropdown for role selection
        options = []
        
        for role in interaction.guild.roles:
            if role.id != interaction.guild.default_role.id and role.id not in self.settings["allowed_roles"]:
                options.append(nextcord.SelectOption(
                    label=role.name[:100],  # Limit to 100 chars
                    value=str(role.id),
                    description=f"ID: {role.id}"
                ))
            
        if not options:
            await interaction.response.send_message("No roles available to add.", ephemeral=True)
            return
            
        # Create a select menu for roles
        select = nextcord.ui.Select(
            placeholder="Select a role to allow voice channel creation",
            options=options[:25],  # Discord limits to 25 options
            min_values=1,
            max_values=1
        )
        
        async def role_callback(select_interaction):
            if select_interaction.user.id != self.user_id:
                await select_interaction.response.send_message("This selection is not for you.", ephemeral=True)
                return
                
            role_id = int(select_interaction.data["values"][0])
            
            # Add the role to allowed roles if not already present
            if role_id not in self.settings["allowed_roles"]:
                self.settings["allowed_roles"].append(role_id)
            
            # Update the database
            await self.save_settings(select_interaction.guild.id)
            
            # Get the role name for confirmation
            role = interaction.guild.get_role(role_id)
            role_name = role.name if role else "Unknown"
            
            await select_interaction.response.send_message(
                f"Role **{role_name}** can now create voice channels.",
                ephemeral=True
            )
            
            # Update the admin settings embed
            embed = self.create_settings_embed(interaction.guild)
            await self.message.edit(embed=embed)
            
        select.callback = role_callback
        
        # Create a temporary view for the select menu
        view = nextcord.ui.View(timeout=60)
        view.add_item(select)
        
        await interaction.response.send_message("Select a role to add:", view=view, ephemeral=True)
    
    @nextcord.ui.button(label="Remove Allowed Role", style=ButtonStyle.danger, row=1)
    async def remove_role(self, button: nextcord.ui.Button, interaction: Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This admin menu is not for you.", ephemeral=True)
            return
            
        # Check if there are any allowed roles
        if not self.settings["allowed_roles"]:
            await interaction.response.send_message("No roles are currently allowed.", ephemeral=True)
            return
            
        # Create dropdown for role removal
        options = []
        
        for role_id in self.settings["allowed_roles"]:
            role = interaction.guild.get_role(role_id)
            if role:
                options.append(nextcord.SelectOption(
                    label=role.name[:100],  # Limit to 100 chars
                    value=str(role.id),
                    description=f"ID: {role.id}"
                ))
            
        if not options:
            await interaction.response.send_message("No roles available to remove.", ephemeral=True)
            return
            
        # Create a select menu for roles
        select = nextcord.ui.Select(
            placeholder="Select a role to remove permission",
            options=options,
            min_values=1,
            max_values=1
        )
        
        async def role_callback(select_interaction):
            if select_interaction.user.id != self.user_id:
                await select_interaction.response.send_message("This selection is not for you.", ephemeral=True)
                return
                
            role_id = int(select_interaction.data["values"][0])
            
            # Remove the role from allowed roles
            if role_id in self.settings["allowed_roles"]:
                self.settings["allowed_roles"].remove(role_id)
            
            # Update the database
            await self.save_settings(select_interaction.guild.id)
            
            # Get the role name for confirmation
            role = interaction.guild.get_role(role_id)
            role_name = role.name if role else "Unknown"
            
            await select_interaction.response.send_message(
                f"Role **{role_name}** can no longer create voice channels.",
                ephemeral=True
            )
            
            # Update the admin settings embed
            embed = self.create_settings_embed(interaction.guild)
            await self.message.edit(embed=embed)
            
        select.callback = role_callback
        
        # Create a temporary view for the select menu
        view = nextcord.ui.View(timeout=60)
        view.add_item(select)
        
        await interaction.response.send_message("Select a role to remove:", view=view, ephemeral=True)
    
    @nextcord.ui.button(label="Toggle Everyone Access", style=ButtonStyle.primary, row=2)
    async def toggle_everyone(self, button: nextcord.ui.Button, interaction: Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This admin menu is not for you.", ephemeral=True)
            return
            
        # Toggle everyone access
        self.settings["everyone_allowed"] = not self.settings["everyone_allowed"]
        
        # Update the database
        await self.save_settings(interaction.guild.id)
        
        # Confirmation message
        message = "Everyone can now create voice channels." if self.settings["everyone_allowed"] else "Only specific roles can now create voice channels."
        await interaction.response.send_message(message, ephemeral=True)
        
        # Update the admin settings embed
        embed = self.create_settings_embed(interaction.guild)
        await self.message.edit(embed=embed)
    
    @nextcord.ui.button(label="Close", style=ButtonStyle.secondary, row=3)
    async def close(self, button: nextcord.ui.Button, interaction: Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This admin menu is not for you.", ephemeral=True)
            return
            
        # Disable all buttons
        for child in self.children:
            child.disabled = True
            
        # Update the message
        await interaction.response.edit_message(view=self)
        
        # Update the embed
        embed = nextcord.Embed(
            title="Voice Channel Admin Settings",
            description="Settings have been saved. Panel is now closed.",
            color=nextcord.Color.green()
        )
        
        await self.message.edit(embed=embed, view=None)
    
    async def save_settings(self, guild_id):
        """Save current settings to the database"""
        try:
            # Format allowed roles as comma-separated string
            allowed_roles_str = ",".join([str(role_id) for role_id in self.settings["allowed_roles"]])
            
            # Save to database
            conn = sqlite3.connect(self.cog.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                """
                INSERT OR REPLACE INTO guild_settings 
                (guild_id, category_id, allowed_roles, everyone_allowed)
                VALUES (?, ?, ?, ?)
                """,
                (
                    guild_id, 
                    self.settings["category_id"], 
                    allowed_roles_str, 
                    1 if self.settings["everyone_allowed"] else 0
                )
            )
            
            conn.commit()
            conn.close()
            
            return True
        except Exception as e:
            print(f"Error saving settings: {e}")
            traceback.print_exc()
            return False
    
    def create_settings_embed(self, guild):
        """Create an embed displaying current admin settings"""
        embed = nextcord.Embed(
            title="Voice Channel Admin Settings",
            description="Configure who can create voice channels and where they will be created.",
            color=nextcord.Color.blue()
        )
        
        # Category info
        category = None
        if self.settings["category_id"]:
            category = guild.get_channel(self.settings["category_id"])
        
        category_text = f"{category.mention} ({category.name})" if category else "No category selected (will create one)"
        embed.add_field(name="Voice Channel Category", value=category_text, inline=False)
        
        # Everyone access
        everyone_text = "✅ Enabled" if self.settings["everyone_allowed"] else "❌ Disabled"
        embed.add_field(name="Everyone Can Create Channels", value=everyone_text, inline=False)
        
        # Allowed roles
        roles_text = ""
        if self.settings["allowed_roles"]:
            for role_id in self.settings["allowed_roles"]:
                role = guild.get_role(role_id)
                if role:
                    roles_text += f"• {role.mention}\n"
        else:
            roles_text = "No specific roles configured."
        
        embed.add_field(name="Roles That Can Create Channels", value=roles_text, inline=False)
        embed.set_footer(text="Use the buttons below to modify these settings")
        
        return embed

class VoiceChannelsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "data/voice_channels.db"
        self.setup_database()
        
        # Dictionary to track empty channels and timestamps
        # {channel_id: {"user_id": user_id, "empty_since": timestamp, "created_at": timestamp}}
        self.empty_channels = {}
        
        # Start background tasks for auto-deletion
        self.check_empty_channels.start()
    
    def cog_unload(self):
        # Cancel background tasks when the cog is unloaded
        self.check_empty_channels.cancel()
    
    def setup_database(self):
        """Set up the voice channels database"""
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create tables
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS voice_channels (
                channel_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            )
            ''')
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                category_id INTEGER,
                allowed_roles TEXT,
                everyone_allowed INTEGER DEFAULT 1
            )
            ''')
            
            conn.commit()
            conn.close()
            print("Voice channels database setup successful")
        except Exception as e:
            print(f"Error setting up database: {e}")
            traceback.print_exc()
    
    def register_empty_channel(self, channel_id, user_id, created=False):
        """Register a channel as empty for auto-deletion tracking"""
        now = time.time()
        self.empty_channels[channel_id] = {
            "user_id": user_id,
            "empty_since": now,
            "created_at": now if created else None
        }
    
    def update_channel_activity(self, channel_id):
        """Update channel activity (reset empty tracking)"""
        if channel_id in self.empty_channels:
            # Channel is now active, remove from empty tracking
            del self.empty_channels[channel_id]
    
    @tasks.loop(seconds=5)
    async def check_empty_channels(self):
        """Check for and delete empty voice channels"""
        now = time.time()
        channels_to_check = list(self.empty_channels.items())
        
        for channel_id, data in channels_to_check:
            channel = self.bot.get_channel(channel_id)
            
            # If channel doesn't exist anymore, remove from tracking
            if not channel:
                if channel_id in self.empty_channels:
                    del self.empty_channels[channel_id]
                continue
            
            # Check if the channel is actually a custom voice channel
            is_custom = await self.is_custom_channel(channel_id)
            if not is_custom:
                if channel_id in self.empty_channels:
                    del self.empty_channels[channel_id]
                continue
            
            # If the channel is empty
            if len(channel.members) == 0:
                # For newly created channels that have never had members
                if data.get("created_at") and (now - data["created_at"] >= 120):  # 2 minutes
                    print(f"Deleting empty channel that was never used: {channel.name}")
                    await self.delete_voice_channel(channel)
                    continue
                
                # For channels that had members but are now empty
                if now - data["empty_since"] >= 5:  # 5 seconds
                    print(f"Deleting empty channel after everyone left: {channel.name}")
                    await self.delete_voice_channel(channel)
            else:
                # Channel has members, update activity
                self.update_channel_activity(channel_id)
    
    @check_empty_channels.before_loop
    async def before_check_empty_channels(self):
        """Wait for the bot to be ready before starting the task"""
        await self.bot.wait_until_ready()
        
        # Scan all voice channels to find existing custom channels
        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                is_custom = await self.is_custom_channel(channel.id)
                if is_custom:
                    # If the channel is empty, start tracking it
                    if len(channel.members) == 0:
                        user_id = await self.get_channel_owner(channel.id)
                        if user_id:
                            self.register_empty_channel(channel.id, user_id)
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Track voice channel join/leave events for auto-deletion"""
        # Handle member joining a voice channel
        if after.channel and not before.channel:
            # Check if the channel is a custom channel
            is_custom = await self.is_custom_channel(after.channel.id)
            if is_custom:
                self.update_channel_activity(after.channel.id)
        
        # Handle member leaving a voice channel
        if before.channel and not after.channel:
            # Check if the channel is a custom channel
            is_custom = await self.is_custom_channel(before.channel.id)
            if is_custom and len(before.channel.members) == 0:
                user_id = await self.get_channel_owner(before.channel.id)
                if user_id:
                    self.register_empty_channel(before.channel.id, user_id)
        
        # Handle member switching channels
        if before.channel and after.channel and before.channel != after.channel:
            # Check if the old channel is a custom channel and is now empty
            is_custom = await self.is_custom_channel(before.channel.id)
            if is_custom and len(before.channel.members) == 0:
                user_id = await self.get_channel_owner(before.channel.id)
                if user_id:
                    self.register_empty_channel(before.channel.id, user_id)
            
            # Check if the new channel is a custom channel
            is_custom = await self.is_custom_channel(after.channel.id)
            if is_custom:
                self.update_channel_activity(after.channel.id)
    
    @nextcord.slash_command(name="vc", description="Voice channel commands")
    async def vc(self, interaction: nextcord.Interaction):
        """Base voice channel command"""
        pass
    
    @vc.subcommand(name="setup", description="Set up a custom voice channel")
    async def vc_setup(self, interaction: nextcord.Interaction):
        """Set up a custom voice channel with personalized settings"""
        await interaction.response.defer(ephemeral=True)
        
        # Check bot permissions first
        if not interaction.guild.me.guild_permissions.manage_channels:
            await interaction.followup.send(
                "I don't have permission to manage channels. Please ask an administrator to grant me the 'Manage Channels' permission.",
                ephemeral=True
            )
            return
        
        # Check if user has permission to create voice channels
        if not await self.can_create_channel(interaction.user):
            await interaction.followup.send(
                "You don't have permission to create custom voice channels.", 
                ephemeral=True
            )
            return
        
        # Check if user already has an active voice channel
        existing_channel = await self.get_user_channel(interaction.user.id)
        if existing_channel:
            await interaction.followup.send(
                f"You already have an active voice channel: {existing_channel.mention}. " +
                "Please use the `/vc edit` command to modify it or wait until it's automatically deleted.",
                ephemeral=True
            )
            return
        
        # Create and send the setup view
        view = VoiceChannelSetupView(self, interaction.user.id)
        embed = view.create_setup_embed()
        
        # Send the setup message
        await interaction.followup.send("Setting up your custom voice channel:", ephemeral=True)
        setup_message = await interaction.channel.send(embed=embed, view=view)
        view.message = setup_message
    
    @vc.subcommand(name="edit", description="Edit your custom voice channel")
    async def vc_edit(self, interaction: nextcord.Interaction):
        """Edit your existing custom voice channel"""
        await interaction.response.defer(ephemeral=True)
        
        # Check if user has an active voice channel
        channel = await self.get_user_channel(interaction.user.id)
        if not channel:
            await interaction.followup.send(
                "You don't have an active voice channel to edit. Use `/vc setup` to create one.",
                ephemeral=True
            )
            return
        
        # Create and send the edit view
        view = VoiceChannelEditView(self, interaction.user.id, channel.id)
        embed = view.create_edit_embed()
        
        # Send the edit message
        await interaction.followup.send("Editing your custom voice channel:", ephemeral=True)
        edit_message = await interaction.channel.send(embed=embed, view=view)
        view.message = edit_message
    
    @vc.subcommand(name="admin", description="Configure server-wide voice channel settings")
    @commands.has_permissions(administrator=True)
    async def vc_admin(self, interaction: nextcord.Interaction):
        """Configure voice channel admin settings"""
        await interaction.response.defer(ephemeral=True)
        
        # Check if the user has administrator permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(
                "You need administrator permissions to configure voice channel settings.",
                ephemeral=True
            )
            return
        
        # Create and send the admin view
        view = AdminSettingsView(self, interaction.user.id)
        
        # Wait a moment for settings to load
        await asyncio.sleep(0.5)
        
        embed = view.create_settings_embed(interaction.guild)
        
        # Send the admin message
        await interaction.followup.send("Configuring voice channel admin settings:", ephemeral=True)
        admin_message = await interaction.channel.send(embed=embed, view=view)
        view.message = admin_message
    
    async def can_create_channel(self, user):
        """Check if a user has permission to create a custom voice channel"""
        # Administrators can always create channels
        if user.guild_permissions.administrator:
            return True
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get guild settings
        cursor.execute("SELECT allowed_roles, everyone_allowed FROM guild_settings WHERE guild_id = ?", 
                      (user.guild.id,))
        result = cursor.fetchone()
        
        conn.close()
        
        # If no settings found, default to everyone allowed
        if not result:
            return True
        
        allowed_roles, everyone_allowed = result
        
        # Check if everyone is allowed
        if everyone_allowed:
            return True
        
        # Check if user has any of the allowed roles
        if allowed_roles:
            role_ids = [int(role_id) for role_id in allowed_roles.split(",") if role_id]
            user_role_ids = [role.id for role in user.roles]
            
            # Check if user has any of the allowed roles
            for role_id in role_ids:
                if role_id in user_role_ids:
                    return True
        
        return False
    
    async def get_channel_owner(self, channel_id):
        """Get the user ID of the channel owner"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT user_id FROM voice_channels WHERE channel_id = ?", (channel_id,))
        result = cursor.fetchone()
        
        conn.close()
        
        return result[0] if result else None
    
    async def is_custom_channel(self, channel_id):
        """Check if a channel is a custom voice channel"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT 1 FROM voice_channels WHERE channel_id = ?", (channel_id,))
        result = cursor.fetchone()
        
        conn.close()
        
        return bool(result)
    
    async def get_user_channel(self, user_id):
        """Get the user's custom voice channel if it exists"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT channel_id FROM voice_channels WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        conn.close()
        
        if result:
            channel_id = result[0]
            channel = self.bot.get_channel(channel_id)
            return channel
        
        return None
    
    def get_user_name(self, user_id):
        """Get a user's display name for naming channels"""
        for guild in self.bot.guilds:
            member = guild.get_member(user_id)
            if member:
                return member.display_name
        
        return "User"
    
    async def create_voice_channel(self, interaction, config):
        """Create a custom voice channel with the given configuration"""
        try:
            guild = interaction.guild
            
            # Double-check bot permissions
            if not guild.me.guild_permissions.manage_channels:
                await interaction.followup.send("I don't have permission to manage channels.", ephemeral=True)
                return None
            
            # Create permissions overwrites
            overwrites = {
                guild.default_role: nextcord.PermissionOverwrite(
                    connect=not config["private"],
                    use_voice_activation=not config["require_mic"]
                ),
                interaction.user: nextcord.PermissionOverwrite(
                    connect=True,
                    manage_channels=True,
                    move_members=True,
                    mute_members=True,
                    use_voice_activation=True
                ),
                guild.me: nextcord.PermissionOverwrite(  # Ensure the bot has permissions
                    connect=True,
                    manage_channels=True,
                    move_members=True
                )
            }
            
            # Get voice channel category
            category = await self.get_vc_category(guild)
            
            # Create the channel
            channel = await guild.create_voice_channel(
                name=config["name"],
                overwrites=overwrites,
                user_limit=config["user_limit"] if config["user_limit"] > 0 else None,
                category=category
            )
            
            # Register the channel in the database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "INSERT INTO voice_channels (channel_id, user_id, guild_id, created_at) VALUES (?, ?, ?, ?)",
                (channel.id, interaction.user.id, guild.id, int(time.time()))
            )
            
            conn.commit()
            conn.close()
            
            # Start tracking for auto-deletion if no one joins
            self.register_empty_channel(channel.id, interaction.user.id, created=True)
            
            return channel
        except nextcord.Forbidden:
            print("Permission error creating voice channel - missing permissions")
            await interaction.followup.send(
                "I don't have permission to create voice channels. Please ask an administrator to check my permissions.",
                ephemeral=True
            )
            return None
        except nextcord.HTTPException as e:
            print(f"HTTP error creating voice channel: {e}")
            await interaction.followup.send(
                f"Discord API error: {e.text}. Please try again later.",
                ephemeral=True
            )
            return None
        except sqlite3.Error as e:
            print(f"Database error creating voice channel: {e}")
            await interaction.followup.send(
                "Database error while creating your channel. Please try again.",
                ephemeral=True
            )
            return None
        except Exception as e:
            print(f"Error creating voice channel: {e}")
            traceback.print_exc()  # Print full stack trace for debugging
            await interaction.followup.send(
                f"An unexpected error occurred: {str(e)}. Please try again or contact the bot administrator.",
                ephemeral=True
            )
            return None
    
    async def update_voice_channel(self, interaction, channel_id, config):
        """Update an existing voice channel with new settings"""
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return False
            
            # Update channel name and user limit
            await channel.edit(
                name=config["name"],
                user_limit=config["user_limit"] if config["user_limit"] > 0 else None
            )
            
            # Update permissions
            guild = interaction.guild
            await channel.set_permissions(
                guild.default_role,
                connect=not config["private"],
                use_voice_activation=not config["require_mic"]
            )
            
            return True
        except Exception as e:
            print(f"Error updating voice channel: {e}")
            traceback.print_exc()
            return False
    
    async def delete_voice_channel(self, channel):
        """Delete a custom voice channel and remove it from the database"""
        try:
            channel_id = channel.id
            
            # Get the channel owner before deleting
            user_id = await self.get_channel_owner(channel_id)
            deletion_reason = ""
            
            # Determine why the channel is being deleted
            if channel_id in self.empty_channels:
                data = self.empty_channels[channel_id]
                
                # If channel was created but never had members
                if data.get("created_at") and len(channel.members) == 0:
                    deletion_reason = "the channel was inactive for 2 minutes after creation with no one joining"
                else:
                    # Channel had members but is now empty
                    deletion_reason = "all members left the channel"
            else:
                deletion_reason = "automatic cleanup"
            
            # Delete the channel
            channel_name = channel.name
            await channel.delete(reason="Auto-deleted empty custom voice channel")
            
            # Send a DM to the owner if we can find them
            if user_id:
                try:
                    owner = await self.bot.fetch_user(user_id)
                    if owner:
                        dm_embed = nextcord.Embed(
                            title="Voice Channel Deleted",
                            description=f"Your voice channel **{channel_name}** has been automatically deleted because {deletion_reason}.",
                            color=nextcord.Color.blue()
                        )
                        dm_embed.set_footer(text="You can create a new channel anytime using /vc setup")
                        
                        await owner.send(embed=dm_embed)
                except Exception as e:
                    print(f"Failed to send DM to user {user_id}: {e}")
            
            # Remove from database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM voice_channels WHERE channel_id = ?", (channel_id,))
            
            conn.commit()
            conn.close()
            
            # Remove from tracking
            if channel_id in self.empty_channels:
                del self.empty_channels[channel_id]
                
            return True
        except Exception as e:
            print(f"Error deleting voice channel: {e}")
            traceback.print_exc()
            return False
    
    async def get_vc_category(self, guild):
        """Get the category for voice channels, create it if it doesn't exist"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get category from settings
            cursor.execute("SELECT category_id FROM guild_settings WHERE guild_id = ?", (guild.id,))
            result = cursor.fetchone()
            
            conn.close()
            
            category_id = result[0] if result and result[0] else None
            category = None
            
            if category_id:
                category = guild.get_channel(category_id)
            
            # If category doesn't exist, create a new one
            if not category:
                try:
                    # Check for permissions first
                    if not guild.me.guild_permissions.manage_channels:
                        print(f"Missing permissions to create category in guild {guild.id}")
                        return None
                        
                    category = await guild.create_category("Custom Voice Channels")
                    
                    # Update the category ID in the database
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    
                    cursor.execute(
                        "INSERT OR REPLACE INTO guild_settings (guild_id, category_id) VALUES (?, ?)",
                        (guild.id, category.id)
                    )
                    
                    conn.commit()
                    conn.close()
                    
                except Exception as e:
                    print(f"Error creating voice channel category: {e}")
                    traceback.print_exc()
                    
            return category
        except Exception as e:
            print(f"Error getting voice channel category: {e}")
            traceback.print_exc()
            return None

def setup(bot):
    bot.add_cog(VoiceChannelsCog(bot))
import nextcord
from nextcord.ext import commands
import re
import sqlite3
import os
import asyncio

class StylistCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.server_id = 1338369899453485088
        self.stylist_role_ids = [1372676758666477589, 1348364871074578443] 
        self.db_path = "data/stylist_roles.db"
        self._setup_database()
    
    def _setup_database(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_roles (
            user_id INTEGER PRIMARY KEY,
            role_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL
        )
        ''')
        conn.commit()
        conn.close()
    
    def _get_user_role(self, user_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT role_id FROM user_roles WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def _set_user_role(self, user_id, role_id, guild_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO user_roles (user_id, role_id, guild_id) VALUES (?, ?, ?)",
            (user_id, role_id, guild_id)
        )
        conn.commit()
        conn.close()
    
    def _delete_user_role(self, user_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    
    def is_valid_hex_color(self, hex_code):
        pattern = r'^#(?:[0-9a-fA-F]{3}){1,2}'
        return re.match(pattern, hex_code) is not None
    
    def has_stylist_permission(self, member: nextcord.Member):
        has_required_role = False
        if self.stylist_role_ids: # Check if the list is not empty
            has_required_role = any(role.id in self.stylist_role_ids for role in member.roles)
        
        is_booster = member.premium_since is not None
        
        return has_required_role or is_booster
    
    @nextcord.slash_command(
        name="stylist",
        description="Stylist role management commands",
        guild_ids=[1338369899453485088] 
    )
    async def stylist(self, interaction: nextcord.Interaction):
        pass
    
    @stylist.subcommand(name="create", description="Create a custom styled role")
    async def create_style(
        self, 
        interaction: nextcord.Interaction, 
        role_name: str = nextcord.SlashOption(
            description="Name for your custom role"
        ),
        hex_color: str = nextcord.SlashOption(
            description="Color for your role (format: #HEXCODE)"
        )
    ):
        if interaction.guild.id != self.server_id:
            await interaction.response.send_message("This command is not available in this server.", ephemeral=True)
            return
        
        if not self.has_stylist_permission(interaction.user):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return
        
        if not self.is_valid_hex_color(hex_color):
            await interaction.response.send_message("Invalid color format. Please use #HEXCODE format (e.g., #FF5733).", ephemeral=True)
            return
        
        existing_role_id = self._get_user_role(interaction.user.id)
        if existing_role_id:
            await interaction.response.send_message("You already have a custom role. Use `/stylist edit` to modify it or `/stylist delete` to remove it first.", ephemeral=True)
            return
        
        color_int = int(hex_color.lstrip('#'), 16)
        discord_color = nextcord.Color(color_int)
        
        position = 1 
        if not self.stylist_role_ids:
            await interaction.response.send_message("Configuration error: No stylist permission roles defined for positioning reference. Cannot create role.", ephemeral=True)
            return

        reference_role_id_for_positioning = self.stylist_role_ids[0]
        stylist_reference_role = interaction.guild.get_role(reference_role_id_for_positioning)

        if not stylist_reference_role:
            await interaction.response.send_message(f"Configuration error: The reference stylist role (ID: {reference_role_id_for_positioning}) was not found on this server. Cannot determine position.", ephemeral=True)
            return
        
        position = stylist_reference_role.position - 1
        if position < 1:
            position = 1

        try:
            new_role = await interaction.guild.create_role(
                name=role_name,
                color=discord_color,
                hoist=False,
                mentionable=False,
                reason=f"Custom style for {interaction.user.display_name}"
            )
            await new_role.edit(position=position)
            await interaction.user.add_roles(new_role)
            self._set_user_role(interaction.user.id, new_role.id, interaction.guild.id)
            await interaction.response.send_message(f"✅ Created and assigned your custom role: {role_name}", ephemeral=True)
        
        except nextcord.Forbidden:
            await interaction.response.send_message("I don't have permission to create, assign, or position roles. Please check my permissions.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)
    
    @stylist.subcommand(name="edit", description="Edit your custom styled role")
    async def edit_style(
        self, 
        interaction: nextcord.Interaction, 
        new_name: str = nextcord.SlashOption(
            description="New name for your custom role",
            required=False
        ),
        new_color: str = nextcord.SlashOption(
            description="New color for your role (format: #HEXCODE)",
            required=False
        )
    ):
        if interaction.guild.id != self.server_id:
            await interaction.response.send_message("This command is not available in this server.", ephemeral=True)
            return
        
        if not self.has_stylist_permission(interaction.user):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return
        
        role_id = self._get_user_role(interaction.user.id)
        if not role_id:
            await interaction.response.send_message("You don't have a custom role yet. Use `/stylist create` to make one first.", ephemeral=True)
            return
        
        if new_color and not self.is_valid_hex_color(new_color):
            await interaction.response.send_message("Invalid color format. Please use #HEXCODE format (e.g., #FF5733).", ephemeral=True)
            return
        
        role = interaction.guild.get_role(role_id)
        
        if not role:
            await interaction.response.send_message("I couldn't find your custom role. It may have been deleted. Removing from database.", ephemeral=True)
            self._delete_user_role(interaction.user.id)
            return
        
        try:
            changes = []
            if new_name:
                await role.edit(name=new_name)
                changes.append(f"name to '{new_name}'")
            
            if new_color:
                color_int = int(new_color.lstrip('#'), 16)
                discord_color = nextcord.Color(color_int)
                await role.edit(color=discord_color)
                changes.append(f"color to {new_color}")
            
            if not changes:
                await interaction.response.send_message("No changes were specified. Please provide a new name or color.", ephemeral=True)
                return
            
            await interaction.response.send_message(f"✅ Updated your custom role: {', '.join(changes)}", ephemeral=True)
        
        except nextcord.Forbidden:
            await interaction.response.send_message("I don't have permission to edit roles.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)
    
    @stylist.subcommand(name="remove", description="Remove your custom styled role temporarily")
    async def remove_style(self, interaction: nextcord.Interaction):
        if interaction.guild.id != self.server_id:
            await interaction.response.send_message("This command is not available in this server.", ephemeral=True)
            return
        
        if not self.has_stylist_permission(interaction.user):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return
        
        role_id_from_db = self._get_user_role(interaction.user.id)
        if not role_id_from_db:
            await interaction.response.send_message("You don't have a custom role record to remove.", ephemeral=True)
            return
        
        role = interaction.guild.get_role(role_id_from_db)
        
        if not role:
            await interaction.response.send_message("I couldn't find your custom role on Discord; it may have already been deleted. Removing from database.", ephemeral=True)
            self._delete_user_role(interaction.user.id)
            return
            
        try:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role)
                await interaction.response.send_message("✅ Your custom role has been temporarily removed. Use `/stylist readd` to get it back.", ephemeral=True)
            else:
                await interaction.response.send_message("You do not currently have this custom role assigned. No action taken.", ephemeral=True)
        
        except nextcord.Forbidden:
            await interaction.response.send_message("I don't have permission to remove roles.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)
    
    @stylist.subcommand(name="readd", description="Re-add your custom styled role")
    async def readd_style(self, interaction: nextcord.Interaction):
        if interaction.guild.id != self.server_id:
            await interaction.response.send_message("This command is not available in this server.", ephemeral=True)
            return
        
        if not self.has_stylist_permission(interaction.user):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return
        
        role_id_from_db = self._get_user_role(interaction.user.id)
        if not role_id_from_db:
            await interaction.response.send_message("You don't have a custom role record to re-add. Use `/stylist create` to make one first.", ephemeral=True)
            return
        
        role = interaction.guild.get_role(role_id_from_db)
        
        if not role:
            await interaction.response.send_message("I couldn't find your custom role on Discord; it may have been deleted. Removing from database.", ephemeral=True)
            self._delete_user_role(interaction.user.id)
            return
            
        if role in interaction.user.roles:
            await interaction.response.send_message("You already have your custom role.", ephemeral=True)
            return
            
        try:
            await interaction.user.add_roles(role)
            await interaction.response.send_message("✅ Your custom role has been re-added.", ephemeral=True)
        
        except nextcord.Forbidden:
            await interaction.response.send_message("I don't have permission to add roles.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)
    
    @stylist.subcommand(name="delete", description="Permanently delete your custom styled role")
    async def delete_style(self, interaction: nextcord.Interaction):
        if interaction.guild.id != self.server_id:
            await interaction.response.send_message("This command is not available in this server.", ephemeral=True)
            return
        
        if not self.has_stylist_permission(interaction.user):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return
        
        role_id_from_db = self._get_user_role(interaction.user.id)
        if not role_id_from_db:
            await interaction.response.send_message("You don't have a custom role record to delete.", ephemeral=True)
            return
        
        role = interaction.guild.get_role(role_id_from_db)
        
        try:
            if role:
                await role.delete(reason=f"Custom style deleted by {interaction.user.display_name}")
            
            self._delete_user_role(interaction.user.id)
            
            if role:
                await interaction.response.send_message("✅ Your custom role has been permanently deleted from Discord and the database.", ephemeral=True)
            else:
                await interaction.response.send_message("✅ Your custom role was not found on Discord (perhaps already deleted), but it has been removed from the database.", ephemeral=True)

        except nextcord.Forbidden:
            await interaction.response.send_message("I don't have permission to delete roles.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

def setup(bot):
    bot.add_cog(StylistCog(bot))
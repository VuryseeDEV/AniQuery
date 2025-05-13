import nextcord
from nextcord.ext import commands
from nextcord import slash_command, Interaction, SlashOption, Embed, ButtonStyle, ui, File
import asyncio
import os
from datetime import datetime
import mysql.connector
from mysql.connector import pooling
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class DatabaseManager:
    def __init__(self, bot=None):
        self.bot = bot
        
        # Database configuration
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'user': os.getenv('DB_USER', 'animebot'),
            'password': os.getenv('DB_PASSWORD', ''),
            'database': os.getenv('TICKET_DB_NAME', 'anime_tickets'),
            'raise_on_warnings': True
        }
        
        # Create connection pool
        try:
            self.pool = mysql.connector.pooling.MySQLConnectionPool(
                pool_name="anime_ticket_pool",
                pool_size=10,
                **self.db_config
            )
            print(f"✅ Connected to MySQL pool for {self.db_config['database']}")
        except Exception as e:
            print(f"❌ Ticket database connection pool error: {e}")
            self.pool = None
    
    def get_connection(self):
        """Get a connection from the pool"""
        try:
            if self.pool:
                return self.pool.get_connection()
            else:
                return mysql.connector.connect(**self.db_config)
        except Exception as e:
            print(f"Database connection error: {e}")
            return None
    
    async def get_ticket_config(self, guild_id):
        """Get ticket configuration for a guild"""
        conn = self.get_connection()
        if not conn:
            return None
            
        cursor = None
        try:
            cursor = conn.cursor(dictionary=True)
            query = "SELECT * FROM ticket_config WHERE guild_id = %s"
            cursor.execute(query, (guild_id,))
            result = cursor.fetchone()
            return result
        except Exception as e:
            print(f"Error getting ticket config: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
            conn.close()
    
    async def update_ticket_config(self, guild_id, **kwargs):
        """Update ticket configuration"""
        if not kwargs:
            return False
            
        conn = self.get_connection()
        if not conn:
            return False
            
        cursor = None
        try:
            cursor = conn.cursor()
            
            # Check if config exists
            query_check = "SELECT 1 FROM ticket_config WHERE guild_id = %s"
            cursor.execute(query_check, (guild_id,))
            exists = cursor.fetchone() is not None
            
            if exists:
                # Update existing config
                set_clauses = []
                params = []
                for key, value in kwargs.items():
                    set_clauses.append(f"{key} = %s")
                    params.append(value)
                
                query = f"UPDATE ticket_config SET {', '.join(set_clauses)} WHERE guild_id = %s"
                params.append(guild_id)
                cursor.execute(query, params)
            else:
                # Insert new config
                keys = ['guild_id'] + list(kwargs.keys())
                placeholders = ', '.join(['%s'] * len(keys))
                query = f"INSERT INTO ticket_config ({', '.join(keys)}) VALUES ({placeholders})"
                params = [guild_id] + list(kwargs.values())
                cursor.execute(query, params)
            
            conn.commit()
            return True
        except Exception as e:
            print(f"Error updating ticket config: {e}")
            conn.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            conn.close()
    
    async def increment_ticket_counter(self, guild_id):
        """Increment ticket counter"""
        conn = self.get_connection()
        if not conn:
            return None
            
        cursor = None
        try:
            cursor = conn.cursor()
            
            # Try to update counter
            query_update = """
            UPDATE ticket_config 
            SET ticket_counter = ticket_counter + 1
            WHERE guild_id = %s
            """
            cursor.execute(query_update, (guild_id,))
            
            # If no rows affected, insert new record
            if cursor.rowcount == 0:
                query_insert = """
                INSERT INTO ticket_config (guild_id, ticket_counter)
                VALUES (%s, 1)
                """
                cursor.execute(query_insert, (guild_id,))
            
            conn.commit()
            
            # Get new counter value
            query_select = "SELECT ticket_counter FROM ticket_config WHERE guild_id = %s"
            cursor.execute(query_select, (guild_id,))
            result = cursor.fetchone()
            
            return result[0] if result else 1
        except Exception as e:
            print(f"Error incrementing ticket counter: {e}")
            conn.rollback()
            return None
        finally:
            if cursor:
                cursor.close()
            conn.close()

# --- UI Components ---
class TicketView(ui.View):
    """Button for creating tickets"""
    def __init__(self, db_manager):
        super().__init__(timeout=None)
        self.db_manager = db_manager
        
        # Only include the Open Ticket button (removed View My Tickets)
        self.add_item(ui.Button(
            label="Open Ticket",
            style=ButtonStyle.primary,
            custom_id="open_ticket",
            emoji="🎫"
        ))

class TicketControlView(ui.View):
    """Buttons for controlling a ticket thread"""
    def __init__(self):
        super().__init__(timeout=None)
        
        # Add Close Ticket button
        self.add_item(ui.Button(
            label="Close Ticket",
            style=ButtonStyle.danger,
            custom_id="close_ticket",
            emoji="🔒"
        ))

# --- Main Ticket Cog ---
class TicketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = DatabaseManager(bot)
        self.bot.loop.create_task(self.setup_cog())

    async def setup_cog(self):
        await self.bot.wait_until_ready()
        print("Starting Ticket Cog setup...")

        # Register persistent views
        self.ticket_view = TicketView(self.db)
        self.ticket_control_view = TicketControlView()
        self.bot.add_view(self.ticket_view)
        self.bot.add_view(self.ticket_control_view)
        
        print("✅ Ticket cog setup complete. Persistent views registered.")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: Interaction):
        """Handle button clicks for the ticket system"""
        if interaction.type != nextcord.InteractionType.component:
            return

        custom_id = interaction.data.get('custom_id', '')
        
        # Open Ticket button
        if custom_id == "open_ticket":
            try:
                await interaction.response.defer(ephemeral=True)
                is_deferred = True
            except nextcord.errors.HTTPException as e:
                if e.code == 40060:  # Interaction already acknowledged
                    is_deferred = False
                else:
                    raise
                    
            await self.create_ticket(interaction, is_deferred)
        
        # Close Ticket button
        elif custom_id == "close_ticket":
            try:
                await interaction.response.defer(ephemeral=True)
                is_deferred = True
            except nextcord.errors.HTTPException as e:
                if e.code == 40060:
                    is_deferred = False
                else:
                    raise
                    
            await self.close_ticket(interaction, is_deferred)

    async def create_ticket(self, interaction: Interaction, is_deferred=True):
        """Handle ticket creation"""
        guild = interaction.guild
        user = interaction.user
        
        # Get ticket configuration
        config = await self.db.get_ticket_config(guild.id)
        if not config:
            if is_deferred:
                await interaction.followup.send("The ticket system hasn't been set up yet.", ephemeral=True)
            else:
                await interaction.edit_original_response(content="The ticket system hasn't been set up yet.")
            return
        
        # Get channel where tickets should be created
        channel_id = config.get('ticket_channel_id')
        if not channel_id:
            if is_deferred:
                await interaction.followup.send("Ticket channel not configured.", ephemeral=True)
            else:
                await interaction.edit_original_response(content="Ticket channel not configured.")
            return
            
        channel = guild.get_channel(channel_id)
        if not channel:
            if is_deferred:
                await interaction.followup.send("Ticket channel not found.", ephemeral=True)
            else:
                await interaction.edit_original_response(content="Ticket channel not found.")
            return
        
        # Increment ticket counter
        ticket_number = await self.db.increment_ticket_counter(guild.id)
        if ticket_number is None:
            if is_deferred:
                await interaction.followup.send("Failed to create ticket number.", ephemeral=True)
            else:
                await interaction.edit_original_response(content="Failed to create ticket number.")
            return
        
        # Create ticket thread
        thread_name = f"ticket-{ticket_number}-{user.name[:20]}"
        try:
            thread = await channel.create_thread(
                name=thread_name,
                type=nextcord.ChannelType.private_thread,
                auto_archive_duration=10080  # 7 days
            )
            await thread.add_user(user)
            
            # If mod roles are configured, fetch and mention them in the ticket
            if config and config.get("mod_role_ids"):
                mod_role_ids = str(config["mod_role_ids"]).split(",")
                for role_id in mod_role_ids:
                    try:
                        role_id = int(role_id.strip())
                        role = guild.get_role(role_id)
                        if role:
                            await thread.send(f"{role.mention} A new ticket has been created.")
                    except (ValueError, TypeError):
                        continue  # Skip invalid role IDs
            
            # Send welcome message with control buttons
            welcome_embed = Embed(
                title=f"Ticket #{ticket_number}",
                description="Support staff will be with you shortly.",
                color=0x00A8FF
            )
            
            await thread.send(
                content=f"{user.mention}, your ticket has been created.",
                embed=welcome_embed,
                view=self.ticket_control_view  # Add control buttons
            )
            
            message = f"Ticket #{ticket_number} created! Click here to access it: {thread.mention}"
            if is_deferred:
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.edit_original_response(content=message)
            
        except Exception as e:
            print(f"Error creating ticket thread: {e}")
            error_message = f"Error creating ticket: {e}"
            if is_deferred:
                await interaction.followup.send(error_message, ephemeral=True)
            else:
                await interaction.edit_original_response(content=error_message)
    
    async def close_ticket(self, interaction: Interaction, is_deferred=True):
        """Close a ticket thread"""
        if not isinstance(interaction.channel, nextcord.Thread):
            message = "This command can only be used in ticket threads!"
            if is_deferred:
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.edit_original_response(content=message)
            return
        
        thread = interaction.channel
        
        try:
            # Send closing message
            await thread.send(f"🔒 Ticket closed by {interaction.user.mention}")
            
            # Lock and archive the thread
            await thread.edit(archived=True, locked=True)
            
            # Confirmation message
            message = "Ticket closed successfully!"
            if is_deferred:
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.edit_original_response(content=message)
                
        except Exception as e:
            print(f"Error closing ticket: {e}")
            error_message = f"Error closing ticket: {e}"
            if is_deferred:
                await interaction.followup.send(error_message, ephemeral=True)
            else:
                await interaction.edit_original_response(content=error_message)

    @slash_command(name="ticket", description="Ticket management commands")
    async def ticket(self, interaction: Interaction):
        """Base ticket command"""
        pass

    @ticket.subcommand(name="setup", description="Set up the ticket system")
    @commands.has_permissions(administrator=True)
    async def ticket_setup(
        self,
        interaction: Interaction,
        channel: nextcord.TextChannel = SlashOption(
            name="channel",
            description="Channel where tickets will be created",
            required=True
        ),
        mod_role1: nextcord.Role = SlashOption(
            name="mod_role1",
            description="First moderator role that will have access to all tickets",
            required=False
        ),
        mod_role2: nextcord.Role = SlashOption(
            name="mod_role2",
            description="Second moderator role that will have access to all tickets",
            required=False
        ),
        mod_role3: nextcord.Role = SlashOption(
            name="mod_role3",
            description="Third moderator role that will have access to all tickets",
            required=False
        )
    ):
        """Set up the ticket system"""
        await interaction.response.defer(ephemeral=True)
        
        # Prepare configuration data
        config_data = {
            'ticket_channel_id': channel.id
        }
        
        # Collect valid mod roles
        mod_roles = []
        role_mentions = []
        
        if mod_role1:
            mod_roles.append(str(mod_role1.id))
            role_mentions.append(mod_role1.mention)
        if mod_role2:
            mod_roles.append(str(mod_role2.id))
            role_mentions.append(mod_role2.mention)
        if mod_role3:
            mod_roles.append(str(mod_role3.id))
            role_mentions.append(mod_role3.mention)
        
        # Add mod role IDs if provided
        if mod_roles:
            config_data['mod_role_ids'] = ','.join(mod_roles)
        
        # Save configuration
        success = await self.db.update_ticket_config(
            interaction.guild.id,
            **config_data
        )
        
        if not success:
            await interaction.followup.send("Failed to save configuration.", ephemeral=True)
            return
        
        # Create ticket panel
        embed = Embed(
            title="Support Tickets",
            description="Click the button below to create a support ticket.",
            color=0x00A8FF
        )
        
        await channel.send(embed=embed, view=self.ticket_view)
        
        # Confirmation message
        confirmation = f"Ticket system set up successfully in {channel.mention}!"
        if role_mentions:
            confirmation += f"\nModerator roles configured: {', '.join(role_mentions)}"
            
        await interaction.followup.send(
            confirmation,
            ephemeral=True
        )
    
    # Add command to manage mod roles for tickets
    @ticket.subcommand(name="mod_roles", description="Set up moderator roles for tickets")
    @commands.has_permissions(administrator=True)
    async def set_mod_roles(
        self,
        interaction: Interaction,
        mod_role1: nextcord.Role = SlashOption(
            name="mod_role1",
            description="First moderator role that will have access to all tickets",
            required=False
        ),
        mod_role2: nextcord.Role = SlashOption(
            name="mod_role2",
            description="Second moderator role that will have access to all tickets",
            required=False
        ),
        mod_role3: nextcord.Role = SlashOption(
            name="mod_role3",
            description="Third moderator role that will have access to all tickets",
            required=False
        )
    ):
        """Configure which moderator roles have access to all tickets"""
        await interaction.response.defer(ephemeral=True)
        
        # Collect valid mod roles
        mod_roles = []
        role_mentions = []
        
        if mod_role1:
            mod_roles.append(str(mod_role1.id))
            role_mentions.append(mod_role1.mention)
        if mod_role2:
            mod_roles.append(str(mod_role2.id))
            role_mentions.append(mod_role2.mention)
        if mod_role3:
            mod_roles.append(str(mod_role3.id))
            role_mentions.append(mod_role3.mention)
        
        # Update config with valid role IDs
        if mod_roles:
            roles_str = ','.join(mod_roles)
            success = await self.db.update_ticket_config(
                interaction.guild.id,
                mod_role_ids=roles_str
            )
            
            if success:
                await interaction.followup.send(
                    f"Moderator roles updated successfully! The following roles will now have access to all tickets: {', '.join(role_mentions)}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send("Failed to update moderator roles. Check bot logs for details.", ephemeral=True)
        else:
            await interaction.followup.send("No roles selected. Please select at least one role.", ephemeral=True)
    
    # Add command for users to add another member to their ticket
    @ticket.subcommand(name="add_member", description="Add another member to this ticket")
    async def add_member(
        self,
        interaction: Interaction,
        member: nextcord.Member = SlashOption(
            name="member",
            description="The member to add to this ticket",
            required=True
        )
    ):
        """Lets users add another member to their ticket thread"""
        await interaction.response.defer(ephemeral=True)
        
        # Check if in a thread
        if not isinstance(interaction.channel, nextcord.Thread):
            await interaction.followup.send("This command can only be used in ticket threads!", ephemeral=True)
            return
        
        thread = interaction.channel
        
        try:
            # Add the member to the thread
            await thread.add_user(member)
            
            # Notify about the addition
            await thread.send(f"{member.mention} has been added to this ticket by {interaction.user.mention}")
            
            await interaction.followup.send(f"Added {member.display_name} to the ticket.", ephemeral=True)
        except nextcord.errors.Forbidden:
            await interaction.followup.send("I don't have permission to add members to this thread.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error adding member: {e}", ephemeral=True)

def setup(bot):
    bot.add_cog(TicketCog(bot))
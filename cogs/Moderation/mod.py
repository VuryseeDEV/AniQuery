import nextcord
from nextcord.ext import commands
from nextcord import Interaction, Embed, SlashOption
import asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import os
import mysql.connector
from mysql.connector import pooling

"""
Ultra-simplified moderation cog with just lock and unlock commands
"""

class ModCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        load_dotenv()
        
        
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'user': os.getenv('DB_USER', 'animebot'),
            'password': os.getenv('DB_PASSWORD', ''),
            'database': os.getenv('MOD_DB_NAME', 'mod_db'),
            'raise_on_warnings': True
        }
        
        
        self.connect_db()
        
        
        self.unlock_tasks = {}
        
        
        self.bot.loop.create_task(self.create_tables())
    
    def connect_db(self):
        """Connect to the database"""
        try:
            self.pool = pooling.MySQLConnectionPool(
                pool_name="mod_pool",
                pool_size=5,
                **self.db_config
            )
            print(f"✅ Connected to MySQL pool for mod functionality")
        except Exception as e:
            print(f"❌ Database connection pool error: {e}")
            self.pool = None
    
    def get_connection(self):
        """Get a database connection"""
        if not self.pool:
            try:
                
                self.connect_db()
            except:
                return None
        
        try:
            return self.pool.get_connection()
        except Exception as e:
            print(f"Error getting database connection: {e}")
            return None
    
    async def create_tables(self):
        """Create necessary tables"""
        await self.bot.wait_until_ready()
        
        conn = self.get_connection()
        if not conn:
            print("Failed to get database connection")
            return
        
        try:
            cursor = conn.cursor()
            
            
            locked_channels_query = """
            CREATE TABLE IF NOT EXISTS locked_channels (
                id INT AUTO_INCREMENT PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                locked_by BIGINT NOT NULL,
                locked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                unlock_time DATETIME NOT NULL,
                reason VARCHAR(255),
                UNIQUE KEY unique_channel (guild_id, channel_id)
            )
            """
            cursor.execute(locked_channels_query)
            
            print("✅ Database tables created/verified")
            
            
            self.bot.loop.create_task(self.restore_locks())
            
        except Exception as e:
            print(f"Error creating tables: {e}")
        finally:
            cursor.close()
            conn.close()
    
    async def restore_locks(self):
        """Restore active channel locks"""
        conn = self.get_connection()
        if not conn:
            return
        
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM locked_channels")
            locks = cursor.fetchall()
            
            if not locks:
                print("No locks to restore")
                return
            
            print(f"Restoring {len(locks)} channel locks")
            
            for lock in locks:
                try:
                    channel_id = lock['channel_id']
                    channel = self.bot.get_channel(channel_id)
                    
                    if not channel:
                        continue
                    
                    
                    now = datetime.now()
                    unlock_time = lock['unlock_time']
                    
                    if now >= unlock_time:
                        
                        await self.remove_lock(lock['guild_id'], channel_id)
                        
                        await self.reset_channel_permissions(channel)
                    else:
                        
                        seconds_left = (unlock_time - now).total_seconds()
                        self.bot.loop.create_task(self.delayed_unlock(channel_id, seconds_left))
                        
                        
                        embed = Embed(
                            title="🔒 Channel Lock Restored",
                            description=f"This channel is locked and will be unlocked <t:{int(unlock_time.timestamp())}:R>",
                            color=0xFF5555
                        )
                        await channel.send(embed=embed)
                except Exception as e:
                    print(f"Error restoring lock for channel {lock['channel_id']}: {e}")
        except Exception as e:
            print(f"Error restoring locks: {e}")
        finally:
            cursor.close()
            conn.close()
    
    async def delayed_unlock(self, channel_id, delay_seconds):
        """Wait and then unlock a channel"""
        try:
            await asyncio.sleep(delay_seconds)
            
            
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return
            
            
            guild_id = channel.guild.id
            await self.remove_lock(guild_id, channel_id)
            
            
            await self.reset_channel_permissions(channel)
            
            
            embed = Embed(
                title="🔓 Channel Unlocked",
                description="This channel has been automatically unlocked.",
                color=0x55FF55
            )
            await channel.send(embed=embed)
            
        except asyncio.CancelledError:
            
            pass
        except Exception as e:
            print(f"Error in delayed unlock: {e}")
    
    async def add_lock(self, guild_id, channel_id, user_id):
        """Add a lock to the database"""
        conn = self.get_connection()
        if not conn:
            return False
        
        try:
            cursor = conn.cursor()
            
            
            unlock_time = datetime.now() + timedelta(hours=3650)
            
            
            query = """
            INSERT INTO locked_channels 
                (guild_id, channel_id, locked_by, unlock_time) 
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                locked_by = %s,
                locked_at = CURRENT_TIMESTAMP,
                unlock_time = %s
            """
            
            cursor.execute(query, (
                guild_id, channel_id, user_id, unlock_time,
                user_id, unlock_time
            ))
            
            conn.commit()
            print(f"Added lock: guild={guild_id}, channel={channel_id}")
            return True
        except Exception as e:
            print(f"Error adding lock: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    async def remove_lock(self, guild_id, channel_id):
        """Remove a lock from the database"""
        conn = self.get_connection()
        if not conn:
            return False
        
        try:
            cursor = conn.cursor()
            query = "DELETE FROM locked_channels WHERE guild_id = %s AND channel_id = %s"
            cursor.execute(query, (guild_id, channel_id))
            conn.commit()
            
            print(f"Removed lock: guild={guild_id}, channel={channel_id}")
            return True
        except Exception as e:
            print(f"Error removing lock: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    async def is_locked(self, guild_id, channel_id):
        """Check if a channel is locked"""
        conn = self.get_connection()
        if not conn:
            return False
        
        try:
            cursor = conn.cursor(dictionary=True)
            query = "SELECT * FROM locked_channels WHERE guild_id = %s AND channel_id = %s"
            cursor.execute(query, (guild_id, channel_id))
            
            result = cursor.fetchone()
            
            if result:
                print(f"Channel {channel_id} is locked: {result}")
                return True, result
            else:
                print(f"Channel {channel_id} is not locked")
                return False, None
        except Exception as e:
            print(f"Error checking lock: {e}")
            return False, None
        finally:
            cursor.close()
            conn.close()
    
    async def lock_channel_permissions(self, channel):
        """Set channel permissions to locked"""
        try:
            everyone_role = channel.guild.default_role
            overwrite = channel.overwrites_for(everyone_role)
            overwrite.send_messages = False
            await channel.set_permissions(everyone_role, overwrite=overwrite)
            return True
        except Exception as e:
            print(f"Error setting channel permissions: {e}")
            return False
    
    async def reset_channel_permissions(self, channel):
        """Reset channel permissions to default"""
        try:
            everyone_role = channel.guild.default_role
            overwrite = channel.overwrites_for(everyone_role)
            overwrite.send_messages = None  
            await channel.set_permissions(everyone_role, overwrite=overwrite)
            return True
        except Exception as e:
            print(f"Error resetting channel permissions: {e}")
            return False

    @nextcord.slash_command(name="lock", description="Lock the channel")
    async def lock(self, interaction: Interaction):
        """Simple command to lock a channel"""
        
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.",
                ephemeral=True
            )
            return
        
        
        if not interaction.guild.me.guild_permissions.manage_channels:
            await interaction.response.send_message(
                "❌ I don't have permission to manage channels.",
                ephemeral=True
            )
            return
        
        channel = interaction.channel
        guild_id = interaction.guild.id
        channel_id = channel.id
        user_id = interaction.user.id
        
        
        is_locked, lock_data = await self.is_locked(guild_id, channel_id)
        
        if is_locked:
            unlock_time = lock_data['unlock_time']
            await interaction.response.send_message(
                embed=Embed(
                    title="🔒 Channel Already Locked",
                    description=f"This channel is already locked and will be unlocked <t:{int(unlock_time.timestamp())}:R>",
                    color=0xFF5555
                )
            )
            return
        
        
        success = await self.add_lock(guild_id, channel_id, user_id)
        
        if not success:
            await interaction.response.send_message(
                "❌ Failed to lock the channel. Database error.",
                ephemeral=True
            )
            return
        
        
        await self.lock_channel_permissions(channel)
        
        
        unlock_time = datetime(9999, 12, 31, 23, 59, 59) 
        
        
        self.bot.loop.create_task(self.delayed_unlock(channel_id, 86400))  
        
        
        embed = Embed(
            title="🔒 Channel Locked",
            description=f"This channel has been locked by {interaction.user.mention} indefinitely.",
            color=0xFF5555
        )
        
        embed.add_field(
            name="Unlock Time",
            value=f"<t:{int(unlock_time.timestamp())}:F>"
        )
        
        await interaction.response.send_message(embed=embed)

    @nextcord.slash_command(name="unlock", description="Unlock the channel")
    async def unlock(self, interaction: Interaction):
        """Simple command to unlock a channel"""
        
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.",
                ephemeral=True
            )
            return
        
        
        if not interaction.guild.me.guild_permissions.manage_channels:
            await interaction.response.send_message(
                "❌ I don't have permission to manage channels.",
                ephemeral=True
            )
            return
        
        channel = interaction.channel
        guild_id = interaction.guild.id
        channel_id = channel.id
        
        
        is_locked, _ = await self.is_locked(guild_id, channel_id)
        
        if not is_locked:
            await interaction.response.send_message(
                "❌ This channel is not locked.",
                ephemeral=True
            )
            return
        
        
        success = await self.remove_lock(guild_id, channel_id)
        
        if not success:
            await interaction.response.send_message(
                "❌ Failed to unlock the channel. Database error.",
                ephemeral=True
            )
            return
        
        
        await self.reset_channel_permissions(channel)
        
        
        embed = Embed(
            title="🔓 Channel Unlocked",
            description=f"This channel has been unlocked by {interaction.user.mention}.",
            color=0x55FF55
        )
        
        await interaction.response.send_message(embed=embed)
    @nextcord.slash_command(name="purge", description="Quickly delete a specified number of messages from the channel.")
    async def purge(
        self, 
        interaction: nextcord.Interaction, 
        amount: int = SlashOption(
            name="amount",
            description="Number of messages to delete",
            required=True
        )
    ):
        
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(
                "❌ You do not have permission to use this command.", ephemeral=True
            )
            return
        
        
        await interaction.response.defer(ephemeral=True)
        
        
        amount = min(amount, 1000)
        
        try:
            
            messages = []
            async for message in interaction.channel.history(limit=amount + 50):
                
                if (nextcord.utils.utcnow() - message.created_at).days < 14:
                    messages.append(message)
                    if len(messages) >= amount:
                        break
            
            
            if not messages:
                await interaction.followup.send("No messages could be deleted (Messages age > 14 days old).", ephemeral=True)
                return
                
            
            deleted_count = 0
            chunks = [messages[i:i + 100] for i in range(0, len(messages), 100)]
            
            for chunk in chunks:
                if chunk:
                    await interaction.channel.delete_messages(chunk)
                    deleted_count += len(chunk)
                    
            
            await interaction.followup.send(f"✅ Successfully deleted {deleted_count} messages.", ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

def setup(bot):
    bot.add_cog(ModCog(bot))
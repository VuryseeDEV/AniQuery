import nextcord
import random
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List
from nextcord import Interaction, Embed, ButtonStyle, Member, TextChannel
from nextcord.ext import commands, tasks
from nextcord.ui import View, Button

def convert_time(duration: str) -> Optional[int]:
    """Convert a duration string to seconds (e.g., '5m' -> 300)"""
    time_units = {
        "s": 1,     
        "m": 60,    
        "h": 3600,  
        "d": 86400, 
        "w": 604800 
    }

    if not duration or len(duration) < 2:
        return None
        
    unit = duration[-1].lower()
    if unit not in time_units:
        return None

    try:
        value = int(duration[:-1])
        if value <= 0:
            return None
    except ValueError:
        return None

    return value * time_units[unit]

def format_time(seconds: int) -> str:
    """Format seconds into a readable time string"""
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''}"
    elif seconds < 604800:
        days = seconds // 86400
        return f"{days} day{'s' if days != 1 else ''}"
    else:
        weeks = seconds // 604800
        return f"{weeks} week{'s' if weeks != 1 else ''}"

class GiveawayView(View):
    def __init__(self, bot, giveaway_manager, channel_id, host, timeout=60, prize="No prize specified", 
                 server_name="Unknown Server", winner_count=1, required_role=None, description=None):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.giveaway_manager = giveaway_manager
        self.channel_id = channel_id
        self.host = host
        self.prize = prize
        self.server_name = server_name
        self.entries = []
        self.winner_count = winner_count
        self.required_role = required_role
        self.description = description
        self.message = None
        self.end_time = datetime.now() + timedelta(seconds=timeout)
        
        
        self.giveaway_id = None  
        self.update_task = self.bot.loop.create_task(self.update_countdown())
        
    async def update_countdown(self):
        """Updates the countdown timer on the giveaway embed"""
        try:
            while not self.is_finished():
                await asyncio.sleep(60)  
                if self.message:
                    remaining = self.end_time - datetime.now()
                    if remaining.total_seconds() > 0:
                        embed = self.message.embeds[0]
                        time_left = format_time(int(remaining.total_seconds()))
                        
                        
                        desc_parts = embed.description.split("\n")
                        for i, line in enumerate(desc_parts):
                            if "Giveaway ends" in line:
                                desc_parts[i] = f"⏰ Giveaway ends in: **{time_left}**"
                                break
                        
                        embed.description = "\n".join(desc_parts)
                        
                        embed.set_footer(text=f"Hosted by: {self.host.display_name} • Entries: {len(self.entries)}")
                        
                        await self.message.edit(embed=embed)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error in update_countdown: {e}")

    def is_eligible(self, user: Member) -> bool:
        """Check if a user is eligible to enter the giveaway"""
        if self.required_role and self.required_role not in [role.id for role in user.roles]:
            return False
        return True

    async def on_timeout(self):
        """Called when the giveaway ends"""
        try:
            self.update_task.cancel()
            
            for child in self.children:
                child.disabled = True
            
            
            winners = []
            if self.entries:
                
                actual_winner_count = min(self.winner_count, len(self.entries))
                
                winners = random.sample(self.entries, actual_winner_count)
            
            
            if winners:
                if len(winners) == 1:
                    winner_text = winners[0].mention
                else:
                    winner_text = ", ".join([w.mention for w in winners])
            else:
                winner_text = "No one entered 😢"
            
            
            embed = Embed(
                title=f"🎉 Giveaway Ended - {self.prize} 🎉",
                description=f"Winner{'s' if self.winner_count > 1 else ''}: {winner_text}",
                color=nextcord.Color.gold(),
            )
            embed.set_footer(text=f"Hosted by: {self.host.display_name} • Total entries: {len(self.entries)}")
            
            await self.message.edit(embed=embed, view=self)
            
            
            channel = self.bot.get_channel(self.channel_id)
            if channel and winners:
                winner_mentions = " ".join([w.mention for w in winners])
                await channel.send(f"🎊 Congratulations {winner_mentions}! You won **{self.prize}**!")
            
            
            for winner in winners:
                try:
                    dm_message = (f"🎉 Congratulations! You won **{self.prize}** from the giveaway in "
                                 f"**{self.server_name}**!\n\n"
                                 f"Host: {self.host.mention}\n"
                                 f"Please contact them to claim your prize!")
                    await winner.send(dm_message)
                except nextcord.errors.Forbidden:
                    if channel:
                        await channel.send(f"⚠️ I couldn't DM {winner.mention}. Make sure they allow DMs from server members.")
            
            
            if self.giveaway_id:
                self.giveaway_manager.remove_giveaway(self.giveaway_id)
                
        except Exception as e:
            print(f"Error in on_timeout: {e}")

    @nextcord.ui.button(label="Enter Giveaway", style=ButtonStyle.green, emoji="🎁")
    async def enter_giveaway(self, button: Button, interaction: Interaction):
        """Button that allows users to enter the giveaway"""
        user = interaction.user
        
        
        if not self.is_eligible(user):
            role = interaction.guild.get_role(self.required_role)
            role_name = role.name if role else "Unknown Role"
            await interaction.response.send_message(
                f"⚠️ You need the `{role_name}` role to enter this giveaway!", 
                ephemeral=True
            )
            return
            
        if user not in self.entries:
            self.entries.append(user)
            await interaction.response.send_message(
                f"✅ {user.mention}, you have entered the giveaway for **{self.prize}**!", 
                ephemeral=True
            )
            
            
            if self.message:
                embed = self.message.embeds[0]
                embed.set_footer(text=f"Hosted by: {self.host.display_name} • Entries: {len(self.entries)}")
                await self.message.edit(embed=embed)
        else:
            await interaction.response.send_message("⚠️ You have already entered this giveaway!", ephemeral=True)
    
    @nextcord.ui.button(label="View Entries", style=ButtonStyle.secondary, emoji="👥")
    async def view_entries(self, button: Button, interaction: Interaction):
        """Button to view current giveaway entries"""
        
        if interaction.user.id != self.host.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("⚠️ Only the giveaway host or server administrators can view entries!", ephemeral=True)
            return
            
        if not self.entries:
            await interaction.response.send_message("No one has entered the giveaway yet.", ephemeral=True)
            return
            
        
        entries_text = "\n".join([f"• {entry.display_name}" for entry in self.entries])
        
        
        if len(entries_text) <= 2000:
            embed = Embed(
                title=f"Giveaway Entries - {self.prize}",
                description=entries_text,
                color=nextcord.Color.blue()
            )
            embed.set_footer(text=f"Total entries: {len(self.entries)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(f"There are {len(self.entries)} entries in this giveaway.", ephemeral=True)


class GiveawayManager:
    def __init__(self, bot):
        self.bot = bot
        self.active_giveaways = {}
        self.load_active_giveaways.start()
        
    def cog_unload(self):
        self.load_active_giveaways.cancel()
        
    @tasks.loop(minutes=15)
    async def load_active_giveaways(self):
        """Check active giveaways periodically to ensure they're still running"""
        
        pass
        
    def add_giveaway(self, giveaway_id, giveaway):
        """Add a giveaway to the active giveaways dictionary"""
        self.active_giveaways[giveaway_id] = giveaway
        
    def remove_giveaway(self, giveaway_id):
        """Remove a giveaway from the active giveaways dictionary"""
        if giveaway_id in self.active_giveaways:
            del self.active_giveaways[giveaway_id]
    
    def get_active_giveaways(self, guild_id=None):
        """Get all active giveaways, optionally filtered by guild"""
        if guild_id:
            return {k: v for k, v in self.active_giveaways.items() if v.message and v.message.guild.id == guild_id}
        return self.active_giveaways


class Giveaway(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.giveaway_manager = GiveawayManager(bot)

    @nextcord.slash_command(name="giveaway", description="Start or manage giveaways")
    async def giveaway_group(self, interaction: Interaction):
        pass

    @giveaway_group.subcommand(name="start", description="Start a new giveaway")
    async def giveaway_start(
        self, 
        interaction: Interaction, 
        duration: str, 
        prize: str,
        winners: int = 1,
        channel: Optional[TextChannel] = None,
        required_role: Optional[nextcord.Role] = None,
        description: Optional[str] = None
    ):
        """
        Start a new giveaway
        Parameters
        ----------
        duration: How long the giveaway should last (e.g. 5m, 1h, 2d)
        prize: What you're giving away
        winners: Number of winners (default: 1)
        channel: The channel to post the giveaway in (default: current channel)
        required_role: Role required to enter the giveaway
        description: Additional details about the giveaway
        """
        
        if not prize or len(prize) > 256:
            await interaction.response.send_message(
                "⚠️ Prize must be between 1 and 256 characters!",
                ephemeral=True
            )
            return
            
        if winners < 1 or winners > 20:
            await interaction.response.send_message(
                "⚠️ Number of winners must be between 1 and 20!",
                ephemeral=True
            )
            return
            
        time_in_seconds = convert_time(duration)
        if time_in_seconds is None:
            await interaction.response.send_message(
                "⚠️ Invalid time format! Use `s` (seconds), `m` (minutes), `h` (hours), `d` (days), `w` (weeks). Example: `5m`",
                ephemeral=True
            )
            return
            
        
        if time_in_seconds > 2592000:  
            await interaction.response.send_message(
                "⚠️ Giveaway duration cannot exceed 30 days!",
                ephemeral=True
            )
            return
        
        
        target_channel = channel or interaction.channel
        
        
        if not target_channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message(
                f"⚠️ I don't have permission to send messages in {target_channel.mention}!",
                ephemeral=True
            )
            return
            
        
        embed = Embed(
            title=f"🎉 GIVEAWAY: {prize} 🎉",
            color=nextcord.Color.blue(),
        )
        
        description_parts = []
        if description:
            description_parts.append(f"**Details:** {description}")
            
        description_parts.extend([
            f"🏆 Prize: **{prize}**",
            f"👑 Host: {interaction.user.mention}",
            f"🔢 Winners: **{winners}**",
            f"⏰ Giveaway ends in: **{format_time(time_in_seconds)}**"
        ])
        
        if required_role:
            description_parts.append(f"🔒 Required role: {required_role.mention}")
            
        description_parts.append("\n👇 Click the button below to enter!")
        
        embed.description = "\n".join(description_parts)
        embed.set_footer(text=f"Hosted by: {interaction.user.display_name} • Entries: 0")
        
        
        view = GiveawayView(
            self.bot,
            self.giveaway_manager,
            target_channel.id,
            interaction.user,
            timeout=time_in_seconds,
            prize=prize,
            server_name=interaction.guild.name,
            winner_count=winners,
            required_role=required_role.id if required_role else None,
            description=description
        )
        
        
        await interaction.response.send_message(
            f"✅ Creating giveaway in {target_channel.mention}!",
            ephemeral=True
        )
        
        
        message = await target_channel.send(embed=embed, view=view)
        view.message = message
        
        
        giveaway_id = f"{interaction.guild.id}-{message.id}"
        view.giveaway_id = giveaway_id
        self.giveaway_manager.add_giveaway(giveaway_id, view)
        
    @giveaway_group.subcommand(name="end", description="End a giveaway early")
    async def giveaway_end(self, interaction: Interaction, message_id: str):
        """
        End a giveaway early
        Parameters
        ----------
        message_id: The ID of the giveaway message to end
        """
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "⚠️ You need administrator permissions to end giveaways!",
                ephemeral=True
            )
            return
            
        giveaway_id = f"{interaction.guild.id}-{message_id}"
        if giveaway_id in self.giveaway_manager.active_giveaways:
            giveaway = self.giveaway_manager.active_giveaways[giveaway_id]
            
            
            await interaction.response.send_message(
                f"✅ Ending the giveaway for **{giveaway.prize}** now!",
                ephemeral=True
            )
            
            
            giveaway.stop()
            await giveaway.on_timeout()
        else:
            await interaction.response.send_message(
                "⚠️ Could not find an active giveaway with that message ID!",
                ephemeral=True
            )
            
    @giveaway_group.subcommand(name="list", description="List all active giveaways")
    async def giveaway_list(self, interaction: Interaction):
        """List all active giveaways in the server"""
        active_giveaways = self.giveaway_manager.get_active_giveaways(interaction.guild.id)
        
        if not active_giveaways:
            await interaction.response.send_message(
                "There are no active giveaways in this server.",
                ephemeral=True
            )
            return
            
        embed = Embed(
            title="Active Giveaways",
            color=nextcord.Color.blue(),
            description=f"There are **{len(active_giveaways)}** active giveaways in this server."
        )
        
        for giveaway_id, giveaway in active_giveaways.items():
            if giveaway.message:
                time_left = format_time(int((giveaway.end_time - datetime.now()).total_seconds()))
                channel = self.bot.get_channel(giveaway.channel_id)
                channel_name = channel.mention if channel else "Unknown Channel"
                
                embed.add_field(
                    name=f"🎁 {giveaway.prize}",
                    value=(
                        f"**Time left:** {time_left}\n"
                        f"**Winners:** {giveaway.winner_count}\n"
                        f"**Channel:** {channel_name}\n"
                        f"**Entries:** {len(giveaway.entries)}\n"
                        f"**Message ID:** {giveaway.message.id}"
                    ),
                    inline=False
                )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @giveaway_group.subcommand(name="reroll", description="Reroll a giveaway winner")
    async def giveaway_reroll(
        self, 
        interaction: Interaction, 
        message_id: str, 
        winner_count: int = 1,
        send_dm: bool = True
    ):
        """
        Reroll a winner for an ended giveaway
        Parameters
        ----------
        message_id: The ID of the giveaway message to reroll
        winner_count: Number of winners to reroll (default: 1)
        send_dm: Whether to send a DM to the new winner(s) (default: True)
        """
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "⚠️ You need administrator permissions to reroll giveaways!",
                ephemeral=True
            )
            return
            
        try:
            message_id = int(message_id)
            message = await interaction.channel.fetch_message(message_id)
        except (ValueError, nextcord.NotFound, nextcord.Forbidden):
            await interaction.response.send_message(
                "⚠️ I couldn't find that message! Make sure you have the correct message ID and that the message is in this channel.",
                ephemeral=True
            )
            return
            
        
        if not message.embeds or "Giveaway Ended" not in message.embeds[0].title:
            await interaction.response.send_message(
                "⚠️ That doesn't seem to be an ended giveaway message!",
                ephemeral=True
            )
            return
            
        
        entries = []
        for component in message.components:
            for child in component.children:
                if hasattr(child, "view") and hasattr(child.view, "entries"):
                    entries = child.view.entries
                    break
            if entries:
                break
                
        
        if not entries:
            await interaction.response.send_message(
                "⚠️ I couldn't find any entries for this giveaway. It might be too old or no one entered.",
                ephemeral=True
            )
            return
            
        
        prize = message.embeds[0].title.replace("🎉 Giveaway Ended - ", "").replace(" 🎉", "")
        
        
        if len(entries) <= winner_count:
            new_winners = entries
        else:
            new_winners = random.sample(entries, winner_count)
        
        
        if new_winners:
            if len(new_winners) == 1:
                winner_text = new_winners[0].mention
            else:
                winner_text = ", ".join([w.mention for w in new_winners])
        else:
            winner_text = "No one entered 😢"
        
        
        await interaction.response.send_message(
            f"🎊 The giveaway for **{prize}** has been rerolled!\n"
            f"New winner{'s' if len(new_winners) > 1 else ''}: {winner_text}"
        )
        
        
        if send_dm and new_winners:
            for winner in new_winners:
                try:
                    await winner.send(
                        f"🎉 Congratulations! You won **{prize}** from a giveaway reroll in "
                        f"**{interaction.guild.name}**!\n\n"
                        f"Host: {interaction.user.mention}\n"
                        f"Please contact them to claim your prize!"
                    )
                except nextcord.errors.Forbidden:
                    await interaction.channel.send(
                        f"⚠️ I couldn't DM {winner.mention}. Make sure they allow DMs from server members."
                    )

def setup(bot):
    bot.add_cog(Giveaway(bot))
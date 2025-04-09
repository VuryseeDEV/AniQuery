import nextcord
from nextcord.ext import commands
import re
import aiohttp
import io


CUSTOM_EMOJI_PATTERN = re.compile(r'<(?P<animated>a)?:(?P<name>[a-zA-Z0-9_]+):(?P<id>\d+)>')
EMOJI_URL_FORMAT = 'https://cdn.discordapp.com/emojis/{0}.{1}'

class EmojiStealer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @nextcord.slash_command(
        name="steal_emoji",
        description="Steal emojis and add them to this server",
        default_member_permissions=nextcord.Permissions(manage_emojis=True)
    )
    async def steal_emoji(
        self,
        interaction: nextcord.Interaction,
        emojis: str = nextcord.SlashOption(
            description="Paste the emoji(s) you want to steal. Can be multiple.",
            required=True
        ),
        rename: str = nextcord.SlashOption(
            description="Optional: Rename the emoji(s) with comma-separated names",
            required=False
        )
    ):
        
        if not interaction.user.guild_permissions.manage_emojis:
            await interaction.response.send_message("You need 'Manage Emojis' permission to use this command!", ephemeral=True)
            return

        
        new_names = []
        if rename:
            new_names = [name.strip() for name in rename.split(',')]

        
        emoji_matches = CUSTOM_EMOJI_PATTERN.finditer(emojis)
        emoji_list = []

        for match in emoji_matches:
            emoji_list.append({
                'name': match.group('name'),
                'id': match.group('id'),
                'animated': match.group('animated') is not None
            })

        if not emoji_list:
            await interaction.response.send_message("No custom emojis found! Make sure you're sending Discord custom emojis.", ephemeral=True)
            return

        
        await interaction.response.send_message(f"Processing {len(emoji_list)} emoji(s)...", ephemeral=True)

        
        async with aiohttp.ClientSession() as session:
            added_emojis = []
            skipped_emojis = []

            for index, emoji_data in enumerate(emoji_list):
                emoji_name = emoji_data['name']
                emoji_id = emoji_data['id']
                is_animated = emoji_data['animated']
                
                
                if index < len(new_names) and new_names[index]:
                    emoji_name = new_names[index]

                
                emoji_format = 'gif' if is_animated else 'png'
                emoji_url = EMOJI_URL_FORMAT.format(emoji_id, emoji_format)

                try:
                    
                    async with session.get(emoji_url) as response:
                        if response.status != 200:
                            skipped_emojis.append(f"{emoji_name} (Failed to download, status: {response.status})")
                            continue

                        emoji_bytes = await response.read()
                        image = io.BytesIO(emoji_bytes)

                        
                        new_emoji = await interaction.guild.create_custom_emoji(
                            name=emoji_name,
                            image=image.getvalue(),
                            reason=f"Emoji stolen by {interaction.user}"
                        )
                        added_emojis.append(f"{new_emoji} (:{new_emoji.name}:)")

                except nextcord.HTTPException as e:
                    if e.code == 30008:
                        skipped_emojis.append(f"{emoji_name} (Emoji limit reached)")
                    elif e.status == 400:
                        skipped_emojis.append(f"{emoji_name} (Invalid emoji)")
                    else:
                        skipped_emojis.append(f"{emoji_name} (Error: {e.text})")
                except Exception as e:
                    skipped_emojis.append(f"{emoji_name} (Unknown error: {str(e)})")

            
            result_message = ""
            if added_emojis:
                result_message += f"✅ Successfully added {len(added_emojis)} emoji(s):\n" + "\n".join(added_emojis) + "\n\n"
            if skipped_emojis:
                result_message += f"❌ Failed to add {len(skipped_emojis)} emoji(s):\n" + "\n".join(skipped_emojis)
            
            if not result_message:
                result_message = "No emojis were processed."

            
            await interaction.followup.send(result_message, ephemeral=True)

    @commands.command(name="steal")
    @commands.has_permissions(manage_emojis=True)
    async def steal_emoji_prefix(self, ctx, *args):
        """
        Prefix command version of steal_emoji
        Usage: !steal :emoji1: :emoji2: :emoji3:
        Or with renaming: !steal :emoji1: :emoji2: :emoji3: --rename name1,name2,name3
        """
        if not args:
            await ctx.send("Please provide at least one emoji to steal.")
            return
            
        
        content = " ".join(args)
        
        
        rename_param = None
        if "--rename" in content:
            parts = content.split("--rename")
            content = parts[0].strip()
            if len(parts) > 1:
                rename_param = parts[1].strip()
                
        
        emoji_matches = CUSTOM_EMOJI_PATTERN.finditer(content)
        emoji_list = []

        for match in emoji_matches:
            emoji_list.append({
                'name': match.group('name'),
                'id': match.group('id'),
                'animated': match.group('animated') is not None
            })

        if not emoji_list:
            await ctx.send("No custom emojis found! Make sure you're sending Discord custom emojis.")
            return
            
        
        new_names = []
        if rename_param:
            new_names = [name.strip() for name in rename_param.split(',')]

        
        processing_msg = await ctx.send(f"Processing {len(emoji_list)} emoji(s)...")

        
        async with aiohttp.ClientSession() as session:
            added_emojis = []
            skipped_emojis = []

            for index, emoji_data in enumerate(emoji_list):
                emoji_name = emoji_data['name']
                emoji_id = emoji_data['id']
                is_animated = emoji_data['animated']
                
                
                if index < len(new_names) and new_names[index]:
                    emoji_name = new_names[index]

                
                emoji_format = 'gif' if is_animated else 'png'
                emoji_url = EMOJI_URL_FORMAT.format(emoji_id, emoji_format)

                try:
                    
                    async with session.get(emoji_url) as response:
                        if response.status != 200:
                            skipped_emojis.append(f"{emoji_name} (Failed to download, status: {response.status})")
                            continue

                        emoji_bytes = await response.read()
                        image = io.BytesIO(emoji_bytes)

                        
                        new_emoji = await ctx.guild.create_custom_emoji(
                            name=emoji_name,
                            image=image.getvalue(),
                            reason=f"Emoji stolen by {ctx.author}"
                        )
                        added_emojis.append(f"{new_emoji} (:{new_emoji.name}:)")

                except nextcord.HTTPException as e:
                    if e.code == 30008:
                        skipped_emojis.append(f"{emoji_name} (Emoji limit reached)")
                    elif e.status == 400:
                        skipped_emojis.append(f"{emoji_name} (Invalid emoji)")
                    else:
                        skipped_emojis.append(f"{emoji_name} (Error: {e.text})")
                except Exception as e:
                    skipped_emojis.append(f"{emoji_name} (Unknown error: {str(e)})")

            
            result_message = ""
            if added_emojis:
                result_message += f"✅ Successfully added {len(added_emojis)} emoji(s):\n" + "\n".join(added_emojis) + "\n\n"
            if skipped_emojis:
                result_message += f"❌ Failed to add {len(skipped_emojis)} emoji(s):\n" + "\n".join(skipped_emojis)
            
            if not result_message:
                result_message = "No emojis were processed."

            
            await processing_msg.edit(content=result_message)

    @nextcord.slash_command(
        name="emoji_info",
        description="Get information about an emoji"
    )
    async def emoji_info(
        self,
        interaction: nextcord.Interaction,
        emoji: str = nextcord.SlashOption(
            description="The emoji you want information about",
            required=True
        )
    ):
        emoji_match = CUSTOM_EMOJI_PATTERN.search(emoji)
        
        if not emoji_match:
            await interaction.response.send_message("That doesn't appear to be a custom emoji!", ephemeral=True)
            return
        
        emoji_name = emoji_match.group('name')
        emoji_id = emoji_match.group('id')
        is_animated = emoji_match.group('animated') is not None
        emoji_format = 'gif' if is_animated else 'png'
        emoji_url = EMOJI_URL_FORMAT.format(emoji_id, emoji_format)
        
        embed = nextcord.Embed(title=f"Emoji Information: {emoji_name}", color=0x3498db)
        embed.add_field(name="Name", value=emoji_name, inline=True)
        embed.add_field(name="ID", value=emoji_id, inline=True)
        embed.add_field(name="Animated", value="Yes" if is_animated else "No", inline=True)
        embed.add_field(name="Steal Command", value=f"`/steal_emoji emojis:{emoji}`", inline=False)
        embed.set_image(url=emoji_url)
        embed.set_footer(text=f"Requested by {interaction.user.display_name}")
        
        await interaction.response.send_message(embed=embed)

def setup(bot):
    bot.add_cog(EmojiStealer(bot))
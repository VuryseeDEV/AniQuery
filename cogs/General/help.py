import nextcord
from nextcord.ext import commands

class HelpCog(commands.Cog):
    """A simple cog containing a help command that outputs a link"""
    
    def __init__(self, bot):
        self.bot = bot
        
    @nextcord.slash_command(
        name="help",
        description="Get help with using the bot"
    )
    async def help_command(self, interaction: nextcord.Interaction):
        """Provides a link to the bot's documentation page"""
        embed = nextcord.Embed(
            title="Bot Help",
            description="For detailed information about commands and features, check out our documentation:",
            color=0x7289DA  # Discord blurple color
        )
        
        embed.add_field(
            name="Documentation", 
            value="[Click here to visit the documentation](https://aniquery.vurydev.cloud/bot)"
        )
        
        embed.set_footer(text="If you need further assistance, join our support server!")
        
        await interaction.response.send_message(embed=embed)

def setup(bot):
    bot.add_cog(HelpCog(bot))
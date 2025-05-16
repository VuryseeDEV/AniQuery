import nextcord
from nextcord.ext import commands, tasks
from nextcord import Interaction, SlashOption, ChannelType
import aiohttp
import asyncio
import sqlite3
import xml.etree.ElementTree as ET

class XCom(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.conn = sqlite3.connect("xcom.db")
        self.cursor = self.conn.cursor()
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS xcom (
                guild_id INTEGER,
                twitter_user TEXT,
                channel_id INTEGER,
                last_tweet_link TEXT
            )
        """)
        self.conn.commit()
        self.check_tweets.start()

    def cog_unload(self):
        self.check_tweets.cancel()
        self.conn.close()

    @nextcord.slash_command(name="xcom", description="Notify when a user tweets (X.com)", default_member_permissions=nextcord.Permissions(administrator=True))
    async def xcom(
        self,
        interaction: Interaction,
        user: str = SlashOption(description="Twitter/X username (without @)"),
        channel: nextcord.TextChannel = SlashOption(description="Channel to send notifications in", channel_types=[ChannelType.text])
    ):
        self.cursor.execute("SELECT * FROM xcom WHERE guild_id = ?", (interaction.guild.id,))
        row = self.cursor.fetchone()

        if row:
            self.cursor.execute("UPDATE xcom SET twitter_user = ?, channel_id = ? WHERE guild_id = ?",
                                (user.lower(), channel.id, interaction.guild.id))
        else:
            self.cursor.execute("INSERT INTO xcom (guild_id, twitter_user, channel_id, last_tweet_link) VALUES (?, ?, ?, ?)",
                                (interaction.guild.id, user.lower(), channel.id, None))
        self.conn.commit()
        await interaction.response.send_message(f"✅ Now tracking @{user} tweets in {channel.mention}", ephemeral=True)

    async def fetch_latest_tweet_link(self, username: str):
        url = f"https://nitter.net/{username}/rss"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        return None
                    xml_text = await resp.text()
            except:
                return None

        try:
            root = ET.fromstring(xml_text)
            item = root.find('./channel/item')
            if item is not None:
                link = item.find('link').text
                return link
        except:
            return None

        return None

    @tasks.loop(minutes=2)
    async def check_tweets(self):
        self.cursor.execute("SELECT * FROM xcom")
        rows = self.cursor.fetchall()
        for guild_id, username, channel_id, last_link in rows:
            new_link = await self.fetch_latest_tweet_link(username)
            if new_link and new_link != last_link:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    await channel.send(f"📢 New tweet from **@{username}**:\n{new_link}")
                self.cursor.execute("UPDATE xcom SET last_tweet_link = ? WHERE guild_id = ?", (new_link, guild_id))
                self.conn.commit()

    @check_tweets.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

def setup(bot):
    bot.add_cog(XCom(bot))

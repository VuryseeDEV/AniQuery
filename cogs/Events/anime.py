import nextcord
from nextcord.ext import commands, tasks
from nextcord import SlashOption, Interaction
import aiohttp
import asyncio
from datetime import datetime, timedelta
import time

class AnimeSubscribeView(nextcord.ui.View):
    """View for subscribing to an anime series"""
    def __init__(self, anime_id, anime_title, user_id, db):
        super().__init__(timeout=60)
        self.anime_id = anime_id
        self.anime_title = anime_title
        self.user_id = user_id
        self.db = db

    @nextcord.ui.button(label="Subscribe", style=nextcord.ButtonStyle.primary, emoji="🔔")
    async def subscribe_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This button is not for you!", ephemeral=True)
            return
            
        
        await self.db.add_subscription(self.user_id, self.anime_id, self.anime_title)
        
        await interaction.response.send_message(f"✅ You've subscribed to **{self.anime_title}**! You'll receive notifications when new episodes air.", ephemeral=True)
        self.stop()

class SeasonSelect(nextcord.ui.Select):
    """Select dropdown for different seasons of a series"""
    def __init__(self, seasons, user_id, db):
        self.user_id = user_id
        self.db = db
        self.seasons = {str(s["id"]): s for s in seasons}
        
        options = []
        for season in seasons:
            season_text = f"{season.get('season', 'Unknown')} {season.get('seasonYear', '')}"
            options.append(nextcord.SelectOption(
                label=f"{season['title'][:80]}",
                description=f"Season: {season_text}" if season_text.strip() else "Unknown season",
                value=str(season["id"])
            ))
            
        super().__init__(placeholder="Select a season to subscribe...", options=options, min_values=1, max_values=1)
        
    async def callback(self, interaction: nextcord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This menu is not for you!", ephemeral=True)
            return
            
        selected_id = self.values[0]
        selected_anime = self.seasons[selected_id]
        
        
        await self.db.add_subscription(self.user_id, int(selected_id), selected_anime["title"])
        
        await interaction.response.send_message(f"✅ You've subscribed to **{selected_anime['title']}**! You'll receive notifications when new episodes air.", ephemeral=True)
        self.view.stop()

class SeasonSelectView(nextcord.ui.View):
    """View for selecting a season from related anime series"""
    def __init__(self, seasons, user_id, db):
        super().__init__(timeout=60)
        self.add_item(SeasonSelect(seasons, user_id, db))

class SubscriptionPaginator(nextcord.ui.View):
    """Paginator for user's anime subscriptions"""
    def __init__(self, subscriptions, user_id, db):
        super().__init__(timeout=180)
        self.subscriptions = subscriptions
        self.current_page = 0
        self.items_per_page = 10
        self.user_id = user_id
        self.db = db
        self.message = None
        self.update_buttons()

    def update_buttons(self):
        """Update buttons based on current page and subscription count"""
        self.clear_items()
        
        
        if len(self.subscriptions) > self.items_per_page:
            if self.current_page > 0:
                prev_button = nextcord.ui.Button(label="Previous", style=nextcord.ButtonStyle.secondary)
                prev_button.callback = self.previous_page
                self.add_item(prev_button)
            
            if (self.current_page + 1) * self.items_per_page < len(self.subscriptions):
                next_button = nextcord.ui.Button(label="Next", style=nextcord.ButtonStyle.secondary)
                next_button.callback = self.next_page
                self.add_item(next_button)
        
        
        start_idx = self.current_page * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(self.subscriptions))
        
        if start_idx < end_idx:
            options = []
            for i in range(start_idx, end_idx):
                sub = self.subscriptions[i]
                options.append(nextcord.SelectOption(
                    label=f"Unsubscribe: {sub['anime_title'][:70]}",
                    value=str(sub["anime_id"])
                ))
                
            if options:
                unsub_select = nextcord.ui.Select(
                    placeholder="Select anime to unsubscribe...", 
                    options=options
                )
                unsub_select.callback = self.unsub_callback
                self.add_item(unsub_select)

    async def get_current_page_embed(self):
        """Create embed for current page of subscriptions"""
        start_idx = self.current_page * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(self.subscriptions))
        page_subs = self.subscriptions[start_idx:end_idx]
        
        embed = nextcord.Embed(
            title="Your Anime Subscriptions", 
            color=0x00A8FF
        )
        
        if not page_subs:
            embed.description = "You don't have any anime subscriptions."
            return embed
        
        description = "Select an anime from the dropdown to unsubscribe:\n\n"
        for i, sub in enumerate(page_subs, 1):
            try:
                subscription_date = datetime.strptime(str(sub['date_subscribed']), '%Y-%m-%d %H:%M:%S')
                timestamp = int(subscription_date.timestamp())
            except (ValueError, TypeError):
                timestamp = 0
            
            description += f"**{start_idx + i}. {sub['anime_title']}**\n"
            description += f"ID: {sub['anime_id']} • Subscribed: <t:{timestamp}:R>\n\n"
        
        if len(description) > 4096:
            description = description[:4093] + "..."
        
        embed.description = description
        
        if len(self.subscriptions) > self.items_per_page:
            embed.set_footer(text=f"Page {self.current_page + 1}/{(len(self.subscriptions) + self.items_per_page - 1) // self.items_per_page}")
        
        return embed
    
    async def previous_page(self, interaction: nextcord.Interaction):
        """Go to previous page of subscriptions"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This menu is not for you!", ephemeral=True)
            return
            
        try:
            if self.current_page > 0:
                self.current_page -= 1
                self.update_buttons()
                embed = await self.get_current_page_embed()
                await interaction.response.edit_message(embed=embed, view=self)
        except Exception as e:
            print(f"Error updating pagination: {e}")
    
    async def next_page(self, interaction: nextcord.Interaction):
        """Go to next page of subscriptions"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This menu is not for you!", ephemeral=True)
            return
            
        try:
            if (self.current_page + 1) * self.items_per_page < len(self.subscriptions):
                self.current_page += 1
                self.update_buttons()
                embed = await self.get_current_page_embed()
                await interaction.response.edit_message(embed=embed, view=self)
        except Exception as e:
            print(f"Error updating pagination: {e}")
            
    async def unsub_callback(self, interaction: nextcord.Interaction):
        """Handle unsubscribe selection"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This menu is not for you!", ephemeral=True)
            return
            
        try:
            selected_id = int(interaction.data['values'][0])
            
            
            await self.db.remove_subscription(self.user_id, selected_id)
            
            
            for i, sub in enumerate(self.subscriptions):
                if sub["anime_id"] == selected_id:
                    del self.subscriptions[i]
                    break
            
            
            self.update_buttons()
            embed = await self.get_current_page_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception as e:
            print(f"Error unsubscribing: {e}")
            await interaction.response.send_message("An error occurred while unsubscribing. Please try again.", ephemeral=True)
    
    async def on_timeout(self):
        """Handle view timeout"""
        if self.message:
            try:
                await self.message.edit(view=None)
            except:
                pass

class AnimeCog(commands.Cog):
    """Cog for managing anime subscriptions and notifications"""
    def __init__(self, bot):
        self.bot = bot
        from utils.db import DatabaseManager
        self.db = DatabaseManager(bot)
        self.session = None
        
        
        self.check_airing.start()
        
        
        bot.loop.create_task(self.setup())
        
    async def setup(self):
        """Setup the database and other resources"""
        await self.bot.wait_until_ready()
        await self.db.setup_database()
        
    def cog_unload(self):
        """Clean up resources when cog is unloaded"""
        self.check_airing.cancel()
        if self.session and not self.session.closed:
            asyncio.create_task(self.session.close())
            
    async def get_session(self):
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
            
    async def query_anilist(self, query, variables=None):
        """Send GraphQL query to AniList API with rate limiting handling"""
        if variables is None:
            variables = {}
            
        session = await self.get_session()
        url = 'https://graphql.anilist.co'
        
        
        await asyncio.sleep(0.5)
        
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                async with session.post(url, json={'query': query, 'variables': variables},
                                     headers={"Content-Type": "application/json", "Accept": "application/json"}) as response:
                    if response.status == 429:  
                        retry_after = int(response.headers.get('Retry-After', 60))
                        print(f"Rate limited by AniList API, retrying after {retry_after} seconds (attempt {retry_count + 1}/{max_retries})")
                        await asyncio.sleep(retry_after)
                        retry_count += 1
                        continue
                        
                    if not response.ok:
                        print(f"AniList API error: Status {response.status}, {await response.text()}")
                        if retry_count < max_retries - 1:
                            retry_count += 1
                            await asyncio.sleep(2 ** retry_count)  
                            continue
                        return {"errors": [{"message": f"API responded with status {response.status}"}]}
                    
                    return await response.json()
            except Exception as e:
                print(f"Error querying AniList API: {e}")
                if retry_count < max_retries - 1:
                    retry_count += 1
                    await asyncio.sleep(2 ** retry_count)  
                    continue
                return {"errors": [{"message": str(e)}]}
        
        return {"errors": [{"message": "Max retries exceeded"}]}

    @nextcord.slash_command(name="anime", description="Anime commands")
    async def anime(self, interaction: nextcord.Interaction):
        """Base anime command group"""
        pass
        
    @anime.subcommand(name="search", description="Search for an anime to subscribe")
    async def anime_search(self, interaction: nextcord.Interaction, query: str):
        """Search for an anime on AniList and display details"""
        try:
            await interaction.response.defer()
            
            
            anilist_query = '''
            query ($search: String) {
                Page(page: 1, perPage: 10) {
                    media(search: $search, type: ANIME, sort: POPULARITY_DESC) {
                        id
                        title {
                            romaji
                            english
                        }
                        description
                        coverImage {
                            large
                        }
                        format
                        episodes
                        status
                        seasonYear
                        season
                        nextAiringEpisode {
                            episode
                            airingAt
                        }
                        studios(isMain: true) {
                            nodes {
                                name
                            }
                        }
                        genres
                        siteUrl
                        relations {
                            edges {
                                relationType
                                node {
                                    id
                                    title {
                                        romaji
                                    }
                                    format
                                    type
                                    status
                                    seasonYear
                                    season
                                }
                            }
                        }
                    }
                }
            }
            '''
            
            
            result = await self.query_anilist(anilist_query, {'search': query})
            
            if 'errors' in result:
                await interaction.followup.send(f"Error: {result['errors'][0]['message']}")
                return
                
            anime_list = result['data']['Page']['media']
            
            if not anime_list:
                await interaction.followup.send("No results found. Try a different search term.")
                return
                
            anime = anime_list[0]  
            
            
            await self.db.cache_anime(anime)
            
            
            embed = nextcord.Embed(title=anime['title']['romaji'], url=anime['siteUrl'], color=0x00A8FF)
            
            if anime['title']['english'] and anime['title']['english'] != anime['title']['romaji']:
                embed.add_field(name="English Title", value=anime['title']['english'], inline=False)
                
            if anime['description']:
                
                description = anime['description'].replace('<br>', '\n').replace('<i>', '*').replace('</i>', '*')
                if len(description) > 1024:
                    description = description[:1021] + "..."
                embed.add_field(name="Description", value=description, inline=False)
                
            if anime['episodes']:
                embed.add_field(name="Episodes", value=str(anime['episodes']), inline=True)
                
            if anime['status']:
                embed.add_field(name="Status", value=anime['status'].replace('_', ' ').title(), inline=True)
                
            if anime['season'] and anime['seasonYear']:
                embed.add_field(name="Season", value=f"{anime['season'].title()} {anime['seasonYear']}", inline=True)
                
            if anime['studios']['nodes']:
                studio_names = [studio['name'] for studio in anime['studios']['nodes']]
                embed.add_field(name="Studio", value=', '.join(studio_names), inline=True)
                
            if anime['genres']:
                embed.add_field(name="Genres", value=', '.join(anime['genres']), inline=True)
                
            if anime['nextAiringEpisode']:
                next_ep = anime['nextAiringEpisode']
                timestamp = f"<t:{next_ep['airingAt']}:R>"
                embed.add_field(
                    name="Next Episode", 
                    value=f"Episode {next_ep['episode']} airing {timestamp}", 
                    inline=False
                )
                
            if anime['coverImage']['large']:
                embed.set_thumbnail(url=anime['coverImage']['large'])
                
            embed.set_footer(text=f"Data from AniList • ID: {anime['id']}")
            
            
            related_seasons = []
            
            if anime['relations']['edges']:
                for edge in anime['relations']['edges']:
                    relation = edge['relationType']
                    node = edge['node']
                    
                    if (node['type'] == 'ANIME' and 
                        relation in ['PREQUEL', 'SEQUEL'] and 
                        node['format'] not in ['MOVIE', 'SPECIAL', 'OVA']):
                        related_seasons.append({
                            "id": node['id'],
                            "title": node['title']['romaji'],
                            "season": node['season'].title() if node['season'] else None,
                            "seasonYear": node['seasonYear'],
                            "relationType": relation
                        })
            
            
            current_anime = {
                "id": anime['id'],
                "title": anime['title']['romaji'],
                "season": anime['season'].title() if anime['season'] else None,
                "seasonYear": anime['seasonYear']
            }
            
            
            if related_seasons:
                all_seasons = [current_anime] + related_seasons
                view = SeasonSelectView(all_seasons, interaction.user.id, self.db)
                await interaction.followup.send(embed=embed, view=view)
            else:
                view = AnimeSubscribeView(anime['id'], anime['title']['romaji'], interaction.user.id, self.db)
                await interaction.followup.send(embed=embed, view=view)
        except Exception as e:
            print(f"Error in anime_search command: {e}")
            await interaction.followup.send("An error occurred while searching for anime. Please try again later.")
    
    @commands.cooldown(1, 5, commands.BucketType.user)
    @anime.subcommand(name="airing", description="Show anime airing on a specific day")
    async def anime_airing(
        self, 
        interaction: nextcord.Interaction, 
        day: str = SlashOption(
            name="day",
            description="Choose which day to view the anime schedule for",
            choices={
                "Monday": "monday",
                "Tuesday": "tuesday", 
                "Wednesday": "wednesday", 
                "Thursday": "thursday", 
                "Friday": "friday", 
                "Saturday": "saturday", 
                "Sunday": "sunday",
                "Today": "today"
            },
            required=True
        )
    ):
        """Display anime airing on the specified day"""
        try:
            await interaction.response.defer()
            
            now = datetime.now()
            
            
            if day == "today":
                
                target_date = now.date()
                day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][target_date.weekday()]
            else:
                
                day_of_week = {
                    "monday": 0, "tuesday": 1, "wednesday": 2, 
                    "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6
                }[day]
                
                
                days_ahead = day_of_week - now.weekday()
                if days_ahead < 0:  
                    days_ahead += 7
                    
                target_date = now.date() + timedelta(days=days_ahead)
                day_name = day.capitalize()
            
            
            start_time = int(datetime.combine(target_date, datetime.min.time()).timestamp())
            end_time = int(datetime.combine(target_date, datetime.max.time()).timestamp())
            
            
            anilist_query = '''
            query ($start: Int, $end: Int) {
                Page(page: 1, perPage: 20) {
                    airingSchedules(airingAt_greater: $start, airingAt_lesser: $end) {
                        id
                        airingAt
                        episode
                        media {
                            id
                            title {
                                romaji
                                english
                            }
                            coverImage {
                                large
                            }
                            siteUrl
                        }
                    }
                }
            }
            '''
            
            variables = {'start': start_time, 'end': end_time}
            result = await self.query_anilist(anilist_query, variables)
            
            if 'errors' in result:
                error_msg = result['errors'][0]['message'] if result['errors'] else "Unknown error"
                await interaction.followup.send(f"Error retrieving anime data: {error_msg}")
                return
           
            
            if 'data' not in result or 'Page' not in result['data'] or 'airingSchedules' not in result['data']['Page']:
                await interaction.followup.send("Error: Received unexpected data format from anime API. Please try again later.")
                return
                
            airing_shows = result['data']['Page']['airingSchedules']
            
            if not airing_shows:
                await interaction.followup.send(f"No anime scheduled to air on {day_name}.")
                return
                
            
            embed = nextcord.Embed(title=f"Anime Airing on {day_name}", color=0x00A8FF)
            
            
            episode_count = len(airing_shows)
            embed.description = f"{episode_count} {'episodes' if episode_count != 1 else 'episode'} scheduled"
            
            
            sorted_anime = sorted(airing_shows, key=lambda x: x['airingAt'])
            
            
            content = ""
            for airing in sorted_anime:
                media = airing['media']
                title = media['title']['romaji']
                time_unix = airing['airingAt']
                next_ep = airing['episode']
                
                
                time_str = f"<t:{time_unix}:t>"
                
                
                content += f"**{title}**\n"
                content += f"Episode {next_ep} at {time_str}\n\n"
                
                
                self.bot.loop.create_task(self.db.cache_anime({
                    'id': media['id'],
                    'title': media['title'],
                    'coverImage': media['coverImage'],
                    'siteUrl': media['siteUrl']
                }))
                
                self.bot.loop.create_task(self.db.update_airing_schedule(
                    media['id'], next_ep, time_unix
                ))
            
            
            if len(content) <= 4096 - len(embed.description) - 2:  
                embed.description = f"{embed.description}\n\n{content}"
            else:
                
                max_length = 4096 - len(embed.description) - 30  
                truncated_content = content[:max_length]
                last_newline = truncated_content.rfind('\n\n')
                if last_newline > 0:
                    truncated_content = truncated_content[:last_newline]
                
                embed.description = f"{embed.description}\n\n{truncated_content}\n\n*...and more episodes not shown*"
            
            
            date_str = target_date.strftime("%B %d, %Y")
            embed.set_footer(text=f"{day_name}, {date_str} • Data from AniList")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error in anime_airing command: {e}")
            await interaction.followup.send("An error occurred while fetching anime schedules. Please try again later.")
    
    @anime.subcommand(name="subscriptions", description="Manage your anime subscriptions")
    async def anime_subscriptions(self, interaction: nextcord.Interaction):
        """View and manage your anime subscriptions"""
        try:
            await interaction.response.defer()
            
            
            subscriptions = await self.db.get_user_subscriptions(interaction.user.id)
            
            if not subscriptions:
                await interaction.followup.send("You don't have any anime subscriptions. Use `/anime search` to find and subscribe to anime.")
                return
                
            
            paginator = SubscriptionPaginator(subscriptions, interaction.user.id, self.db)
            embed = await paginator.get_current_page_embed()
            
            message = await interaction.followup.send(embed=embed, view=paginator)
            if message:
                paginator.message = message
        
        except Exception as e:
            print(f"Error listing subscriptions: {e}")
            await interaction.followup.send("An error occurred while loading your subscriptions. Please try again later.")
        
    @anime.subcommand(name="settings", description="Configure your anime notification settings")
    async def anime_settings(
        self, 
        interaction: nextcord.Interaction,
        notifications: bool = SlashOption(
            name="notifications",
            description="Enable or disable DM notifications",
            required=False
        ),
        title_format: str = SlashOption(
            name="title_format",
            description="Preferred title format for notifications",
            choices={"Romaji (Japanese)": "romaji", "English": "english"},
            required=False
        )
    ):
        """Configure anime notification settings"""
        await interaction.response.defer(ephemeral=True)
        
        
        settings = await self.db.get_user_settings(interaction.user.id)
        
        
        if notifications is None and title_format is None:
            embed = nextcord.Embed(
                title="Your Anime Notification Settings",
                color=0x00A8FF,
                description="Your current notification settings:"
            )
            embed.add_field(
                name="DM Notifications",
                value="Enabled ✅" if settings.get('notification_enabled', True) else "Disabled ❌",
                inline=True
            )
            embed.add_field(
                name="Title Format",
                value=f"{'Romaji (Japanese)' if settings.get('preferred_title_format') == 'romaji' else 'English'}",
                inline=True
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        
        updated = await self.db.update_user_settings(
            interaction.user.id,
            notification_enabled=notifications,
            preferred_title_format=title_format
        )
        
        
        settings = await self.db.get_user_settings(interaction.user.id)
        
        
        embed = nextcord.Embed(
            title="Anime Notification Settings Updated",
            color=0x00A8FF,
            description="Your notification settings have been updated:"
        )
        embed.add_field(
            name="DM Notifications",
            value="Enabled ✅" if settings.get('notification_enabled', True) else "Disabled ❌",
            inline=True
        )
        embed.add_field(
            name="Title Format",
            value=f"{'Romaji (Japanese)' if settings.get('preferred_title_format') == 'romaji' else 'English'}",
            inline=True
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    @anime.subcommand(name="guild_settings", description="Configure server notification settings")
    @commands.has_permissions(manage_guild=True)
    async def guild_settings(
        self, 
        interaction: nextcord.Interaction,
        channel: nextcord.TextChannel = SlashOption(
            name="channel",
            description="Channel for public anime notifications (or 'none' to disable)",
            required=False
        ),
        public_notifications: bool = SlashOption(
            name="public_notifications",
            description="Enable or disable public notifications",
            required=False
        )
    ):
        """Configure server-wide anime notification settings"""
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You need the 'Manage Server' permission to use this command.", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        
        
        settings = await self.db.get_guild_settings(interaction.guild.id)
        
        
        if channel is None and public_notifications is None:
            current_channel = interaction.guild.get_channel(settings.get('notification_channel_id')) if settings.get('notification_channel_id') else None
            
            embed = nextcord.Embed(
                title="Server Anime Notification Settings",
                color=0x00A8FF,
                description="Current server notification settings:"
            )
            embed.add_field(
                name="Notification Channel",
                value=current_channel.mention if current_channel else "Not set",
                inline=True
            )
            embed.add_field(
                name="Public Notifications",
                value="Enabled ✅" if settings.get('public_notifications', False) else "Disabled ❌",
                inline=True
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        
        channel_id = channel.id if channel else None
        updated = await self.db.update_guild_settings(
            interaction.guild.id,
            notification_channel_id=channel_id,
            public_notifications=public_notifications
        )
        
        
        settings = await self.db.get_guild_settings(interaction.guild.id)
        current_channel = interaction.guild.get_channel(settings.get('notification_channel_id')) if settings.get('notification_channel_id') else None
        
        
        embed = nextcord.Embed(
            title="Server Anime Notification Settings Updated",
            color=0x00A8FF,
            description="Server notification settings have been updated:"
        )
        embed.add_field(
            name="Notification Channel",
            value=current_channel.mention if current_channel else "Not set",
            inline=True
        )
        embed.add_field(
            name="Public Notifications",
            value="Enabled ✅" if settings.get('public_notifications', False) else "Disabled ❌",
            inline=True
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    @tasks.loop(minutes=15)
    async def check_airing(self): #TEST
        """Check for recently aired episodes and notify subscribers"""
        try:
            
            aired_episodes = await self.db.get_recently_aired(hours_ago=1)
            
            if not aired_episodes:
                return
                
            for ep in aired_episodes:
                anime_id = ep['anime_id']
                title_romaji = ep['title_romaji']
                title_english = ep['title_english']
                episode = ep['episode']
                url = ep['site_url']
                cover_url = ep['cover_image_url']
                
                
                subscribers = await self.db.get_anime_subscribers(anime_id)
                
                if not subscribers:
                    continue
                
                
                embed = nextcord.Embed(
                    title=f"New Episode Alert!",
                    description=f"Episode {episode} of {title_romaji} just aired!",
                    color=0x00A8FF,
                    url=url
                )
                
                if cover_url:
                    embed.set_thumbnail(url=cover_url)
                    
                if title_english and title_english != title_romaji:
                    embed.description = f"Episode {episode} of {title_romaji} ({title_english}) just aired!"
                
                embed.set_footer(text="You received this because you're subscribed to this anime.")
                
                
                for sub in subscribers:
                    user_id = sub['user_id']
                    
                    
                    settings = await self.db.get_user_settings(user_id)
                    if not settings.get('notification_enabled', True):
                        continue
                        
                    
                    already_sent = await self.check_notification_sent(user_id, anime_id, episode)
                    if already_sent:
                        continue
                    
                    
                    title_format = settings.get('preferred_title_format', 'romaji')
                    notification_embed = embed.copy()
                    
                    if title_format == 'english' and title_english:
                        notification_embed.description = f"Episode {episode} of {title_english} just aired!"
                    
                    
                    try:
                        user = await self.bot.fetch_user(user_id)
                        await user.send(embed=notification_embed)
                        await self.db.add_notification(user_id, anime_id, episode, successful=True)
                    except Exception as e:
                        print(f"Failed to DM user {user_id}: {e}")
                        await self.db.add_notification(user_id, anime_id, episode, successful=False)
                
                
                for guild in self.bot.guilds:
                    settings = await self.db.get_guild_settings(guild.id)
                    
                    if not settings.get('public_notifications', False) or not settings.get('notification_channel_id'):
                        continue
                        
                    
                    has_subscribers = False
                    for sub in subscribers:
                        member = guild.get_member(sub['user_id'])
                        if member:
                            has_subscribers = True
                            break
                            
                    if not has_subscribers:
                        continue
                        
                    
                    channel = guild.get_channel(settings['notification_channel_id'])
                    if channel:
                        try:
                            public_embed = embed.copy()
                            public_embed.set_footer(text=f"New episode notification • {guild.name}")
                            await channel.send(embed=public_embed)
                        except Exception as e:
                            print(f"Failed to send public notification to guild {guild.id}: {e}")
                    
        except Exception as e:
            print(f"Error in check_airing task: {e}")
            
    async def check_notification_sent(self, user_id, anime_id, episode):
        """Check if a notification was already sent to a user"""
        query = """
        SELECT id FROM notification_history 
        WHERE user_id = %s AND anime_id = %s AND episode_number = %s
        """
        result = await self.db.execute_query(query, (user_id, anime_id, episode), fetch=True)
        return bool(result)

    @check_airing.before_loop
    async def before_check_airing(self):
        """Wait for bot to be ready before starting task"""
        await self.bot.wait_until_ready()

def setup(bot):
    bot.add_cog(AnimeCog(bot))
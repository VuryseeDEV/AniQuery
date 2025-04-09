import nextcord
from nextcord.ext import commands
import asyncio
import random
import datetime
from typing import List, Dict, Any, Optional

class AnimeSelectView(nextcord.ui.View):
    """View with a select menu for choosing an anime from recommendations"""
    def __init__(self, anime_list, db, timeout=180):
        super().__init__(timeout=timeout)
        self.anime_list = anime_list
        self.db = db
        
        # Create select menu
        select_options = []
        for anime in anime_list:
            title = anime['title']['romaji']
            # Truncate if too long
            if len(title) > 100:
                title = title[:97] + "..."
            select_options.append(nextcord.SelectOption(
                label=title,
                value=str(anime['id']),
                description=f"Released: {anime.get('seasonYear', 'Unknown')}"
            ))
        
        # Add select menu to view
        self.select = AnimeSelect(select_options, db, self)
        self.add_item(self.select)
        self.message = None

class AnimeSelect(nextcord.ui.Select):
    """TEST"""
    def __init__(self, options, db, parent_view):
        self.db = db
        self.parent_view = parent_view
        
        super().__init__(
            placeholder="Select an anime for more details...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: nextcord.Interaction):
        """Handle anime selection"""
        await interaction.response.defer()
        
        selected_id = int(self.values[0])
        
        # Find the selected anime in the list
        selected_anime = None
        for anime in self.parent_view.anime_list:
            if anime['id'] == selected_id:
                selected_anime = anime
                break
        
        if not selected_anime:
            await interaction.followup.send("Error: Could not find selected anime.", ephemeral=True)
            return
        
        try:
            # Get detailed anime info using the existing anime command cog functionality
            from cogs.Events.anime import AnimeCog
            anime_cog = self.db.bot.get_cog('AnimeCog')
            
            # If we couldn't get the AnimeCog, get details directly
            if not anime_cog:
                # Get detailed anime info 
                # Cache anime data in database
                await self.db.cache_anime(selected_anime)
                
                # Create embed
                embed = nextcord.Embed(
                    title=selected_anime['title']['romaji'], 
                    url=selected_anime.get('siteUrl', f"https://anilist.co/anime/{selected_id}"), 
                    color=0x00A8FF
                )
                
                if selected_anime['title']['english'] and selected_anime['title']['english'] != selected_anime['title']['romaji']:
                    embed.add_field(name="English Title", value=selected_anime['title']['english'], inline=False)
                    
                if selected_anime.get('description'):
                    # Clean description and truncate if needed
                    description = selected_anime['description'].replace('<br>', '\n').replace('<i>', '*').replace('</i>', '*')
                    if len(description) > 1024:
                        description = description[:1021] + "..."
                    embed.add_field(name="Description", value=description, inline=False)
                    
                if selected_anime.get('episodes'):
                    embed.add_field(name="Episodes", value=str(selected_anime['episodes']), inline=True)
                    
                if selected_anime.get('status'):
                    embed.add_field(name="Status", value=selected_anime['status'].replace('_', ' ').title(), inline=True)
                    
                if selected_anime.get('season') and selected_anime.get('seasonYear'):
                    embed.add_field(name="Season", value=f"{selected_anime['season'].title()} {selected_anime['seasonYear']}", inline=True)
                    
                if selected_anime.get('studios', {}).get('nodes'):
                    studio_names = [studio['name'] for studio in selected_anime['studios']['nodes']]
                    embed.add_field(name="Studio", value=', '.join(studio_names), inline=True)
                    
                if selected_anime.get('genres'):
                    embed.add_field(name="Genres", value=', '.join(selected_anime['genres']), inline=True)
                    
                if selected_anime.get('nextAiringEpisode'):
                    next_ep = selected_anime['nextAiringEpisode']
                    timestamp = f"<t:{next_ep['airingAt']}:R>"
                    embed.add_field(
                        name="Next Episode", 
                        value=f"Episode {next_ep['episode']} airing {timestamp}", 
                        inline=False
                    )
                    
                if selected_anime.get('coverImage', {}).get('large'):
                    embed.set_thumbnail(url=selected_anime['coverImage']['large'])
                    
                embed.set_footer(text=f"Data from AniList • ID: {selected_anime['id']}")
                
                # Send the detailed view
                await interaction.followup.send(embed=embed)
            else:
                # Use the same query and formatting as the anime search command
                anilist_query = '''
                query ($id: Int) {
                  Media(id: $id, type: ANIME) {
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
                '''
                
                # Get detailed info using anime cog's query method
                result = await anime_cog.query_anilist(anilist_query, {'id': selected_id})
                
                if 'errors' in result:
                    await interaction.followup.send(f"Error: {result['errors'][0]['message']}")
                    return
                    
                anime = result['data']['Media']
                
                # Cache anime data in database
                await anime_cog.db.cache_anime(anime)
                
                # Create embed using the same code as in anime search
                embed = nextcord.Embed(title=anime['title']['romaji'], url=anime['siteUrl'], color=0x00A8FF)
                
                if anime['title']['english'] and anime['title']['english'] != anime['title']['romaji']:
                    embed.add_field(name="English Title", value=anime['title']['english'], inline=False)
                    
                if anime['description']:
                    # Clean description and truncate if needed
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
                
                # Check for related seasons
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
                
                # Add season info if there are related seasons
                if related_seasons:
                    seasons_text = []
                    for season in related_seasons:
                        relation = season['relationType'].lower()
                        season_info = f"{season['season']} {season['seasonYear']}" if season['season'] and season['seasonYear'] else "Unknown season"
                        seasons_text.append(f"• {relation.capitalize()}: {season['title']} ({season_info})")
                    
                    embed.add_field(name="Related Seasons", value="\n".join(seasons_text), inline=False)
                
                # Send the detailed view
                await interaction.followup.send(embed=embed)
                
                # Create subscribe view if needed
                # Not adding subscription functionality here as it would replicate the AnimeCog logic
                
        except Exception as e:
            print(f"Error showing anime details: {e}")
            await interaction.followup.send(f"An error occurred while fetching anime details. Please try again later.", ephemeral=True)

class AniListCog(commands.Cog):
    """Cog for interacting with AniList API and providing anime recommendations"""
    def __init__(self, bot):
        self.bot = bot
        # Get database and AniList API from existing cogs
        from utils.db import DatabaseManager
        self.db = DatabaseManager(bot)
        
        # Get AniList API from utils
        from utils.anilist import AniListAPI
        self.anilist = AniListAPI()
        
        # Complete list of genres used by AniList
        self.common_genres = [
            "Action", "Adventure", "Comedy", "Drama", "Ecchi", "Fantasy", 
            "Horror", "Mahou Shoujo", "Mecha", "Music", "Mystery", "Psychological", 
            "Romance", "Sci-Fi", "Slice of Life", "Sports", "Supernatural", 
            "Thriller", "Hentai", "Isekai", "Josei", "Kids", "Seinen", 
            "Shoujo", "Shounen", "Yaoi", "Yuri", "Parody", "Demons", 
            "Game", "Historical", "Martial Arts", "Military", "School",
            "Space", "Vampire", "Cars", "Dementia", "Harem", "Magic"
        ]
    
    @nextcord.slash_command(name="anilist", description="AniList related commands")
    async def anilist(self, interaction: nextcord.Interaction):
        """Base command for AniList related commands"""
        pass
    
    @anilist.subcommand(
        name="recommend", 
        description="Get anime recommendations based on year range and genres"
    )
    async def recommend(
        self, 
        interaction: nextcord.Interaction,
        year_min: int = nextcord.SlashOption(
            name="year_min",
            description="Minimum year (1980+)",
            required=True,
            min_value=1980,
            max_value=2100  # Setting a high max value to future-proof
        ),
        year_max: int = nextcord.SlashOption(
            name="year_max",
            description="Maximum year (defaults to current year)",
            required=False,
            min_value=1980,
            max_value=2100
        ),
        genres: str = nextcord.SlashOption(
            name="genres",
            description="Genres (comma-separated, e.g., 'Action,Romance,Comedy')",
            required=False
        )
    ):
        """Get anime recommendations based on year range and genres"""
        await interaction.response.defer()
        
        try:
            # If year_max is not provided, use current year
            current_year = datetime.datetime.now().year
            if not year_max:
                year_max = current_year
            
            # Validate year range
            if year_min > year_max:
                await interaction.followup.send("Error: Minimum year cannot be greater than maximum year.", ephemeral=True)
                return
            
            # Allow any future years for announced anime or future seasons
            # This makes the bot "future-proof" - it will work even as years advance
            # AniList data includes announced future seasons
            
            # Parse genres
            genre_list = []
            if genres:
                # Split by comma and strip whitespace
                genre_list = [g.strip() for g in genres.split(',')]
                
                # Clean up genre names to match AniList's format exactly
                # First, capitalize each word in multi-word genres
                genre_list = [g.title() for g in genre_list]
                
                # Handle special cases to match AniList conventions exactly
                genre_mapping = {
                    "Sci-fi": "Sci-Fi",
                    "Scifi": "Sci-Fi",
                    "Science Fiction": "Sci-Fi",
                    "Slice Of Life": "Slice of Life",
                    "Mahou Shoujo": "Mahou Shoujo",
                    "Magical Girl": "Mahou Shoujo",
                    "Shounen": "Shounen",
                    "Shonen": "Shounen",
                    "Shoujo": "Shoujo",
                    "Shojo": "Shoujo",
                    "Seinen": "Seinen",
                    "Josei": "Josei"
                }
                
                # Apply mapping for special cases
                genre_list = [genre_mapping.get(g, g) for g in genre_list]
                
                # Validate that all genres are in the allowed list
                valid_genres = []
                for genre in genre_list:
                    if genre in self.common_genres:
                        valid_genres.append(genre)
                    else:
                        # Try to find a close match
                        found = False
                        for valid_genre in self.common_genres:
                            if valid_genre.lower() == genre.lower():
                                valid_genres.append(valid_genre)
                                found = True
                                break
                        
                        if not found and interaction:
                            print(f"Warning: Genre '{genre}' not found in AniList genres, skipping")
                
                genre_list = valid_genres
            
            # Query AniList for anime matching the criteria
            result = await self.query_recommendations(year_min, year_max, genre_list)
            
            if not result or not result.get('data') or not result['data'].get('Page') or not result['data']['Page'].get('media') or len(result['data']['Page']['media']) == 0:
                await interaction.followup.send("No anime found matching your criteria. Try different years or genres.", ephemeral=True)
                return
            
            # Get the list of anime
            anime_list = result['data']['Page']['media']
            
            # Randomly select 5 anime (or less if there are fewer results)
            if len(anime_list) > 5:
                selected_anime = random.sample(anime_list, 5)
            else:
                selected_anime = anime_list
            
            # Create the recommendations embed
            embed = nextcord.Embed(
                title="Anime Recommendations",
                description=f"Based on years {year_min}-{year_max}" + (f" and genres: {', '.join(genre_list)}" if genre_list else ""),
                color=0x00A8FF
            )
            
            # Add each anime to the embed
            for i, anime in enumerate(selected_anime, 1):
                title = anime['title']['romaji']
                english_title = anime['title'].get('english')
                title_display = f"{title}" + (f" / {english_title}" if english_title and english_title != title else "")
                
                season_info = []
                if anime.get('season') and anime.get('seasonYear'):
                    season_info.append(f"{anime['season'].title()} {anime['seasonYear']}")
                
                if anime.get('episodes'):
                    season_info.append(f"{anime['episodes']} episodes")
                
                if anime.get('genres'):
                    genres_text = ', '.join(anime['genres'][:3])  # Show up to 3 genres
                    if len(anime['genres']) > 3:
                        genres_text += ", ..."
                
                embed_value = (
                    f"**Year:** {anime.get('seasonYear', 'Unknown')}\n"
                    f"**Season:** {anime['season'].title() if anime.get('season') else 'Unknown'}\n"
                    f"**Genres:** {', '.join(anime['genres'][:3]) + ('...' if len(anime['genres']) > 3 else '')}"
                )
                
                embed.add_field(
                    name=f"{i}. {title_display}",
                    value=embed_value,
                    inline=False
                )
            
            # Add a note about the selection menu
            embed.set_footer(text="Use the menu below to get more details about any of these anime")
            
            # If any anime has a cover image, use the first one as the thumbnail
            for anime in selected_anime:
                if anime.get('coverImage', {}).get('large'):
                    embed.set_thumbnail(url=anime['coverImage']['large'])
                    break
            
            # Create and send the view with select menu
            view = AnimeSelectView(selected_anime, self.db)
            response = await interaction.followup.send(embed=embed, view=view)
            
            # Store the message for view reference
            if hasattr(response, 'id'):
                view.message = response
            
        except Exception as e:
            print(f"Error in anime recommendations: {e}")
            await interaction.followup.send("An error occurred while fetching anime recommendations. Please try again later.", ephemeral=True)
    
    async def query_recommendations(self, year_min, year_max, genres=None):
        """Query AniList API for anime recommendations"""
        query = """
        query ($page: Int, $perPage: Int, $yearMin: Int, $yearMax: Int, $genres: [String]) {
          Page(page: $page, perPage: $perPage) {
            media(
              type: ANIME, 
              format_in: [TV, MOVIE, OVA, ONA, SPECIAL],
              sort: [POPULARITY_DESC, SCORE_DESC],
              seasonYear_greater: $yearMin,
              seasonYear_lesser: $yearMax,
              genre_in: $genres,
              countryOfOrigin: "JP"
            ) {
              id
              title {
                romaji
                english
              }
              description
              seasonYear
              season
              episodes
              status
              genres
              coverImage {
                large
              }
              studios {
                nodes {
                  name
                }
              }
              nextAiringEpisode {
                airingAt
                episode
              }
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
        """
        
        # Randomly select a page between 1-5 for variety
        page = random.randint(1, 5)
        
        variables = {
            "page": page,
            "perPage": 50,  # Get more results to allow for random selection
            "yearMin": year_min,
            "yearMax": year_max
        }
        
        # Add genres if provided
        if genres and len(genres) > 0:
            variables["genres"] = genres
        
        # Make the API request using AniList API
        return await self.anilist._make_request(query, variables)

def setup(bot):
    bot.add_cog(AniListCog(bot))
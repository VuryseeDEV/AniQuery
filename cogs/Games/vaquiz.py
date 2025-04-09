import nextcord
from nextcord.ext import commands
import asyncio
import random
import aiohttp
from typing import List, Dict, Any

class VoiceActorSelect(nextcord.ui.Select):
    def __init__(self, correct_id, options, callback):
        self.correct_id = correct_id
        self.callback_func = callback
        
        super().__init__(
            placeholder="Select the voice actor for this character...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: nextcord.Interaction):
        selected_id = self.values[0]
        await self.callback_func(interaction, selected_id == self.correct_id, selected_id)

class VoiceActorGuessView(nextcord.ui.View):
    def __init__(self, correct_id, options, callback):
        super().__init__(timeout=60)
        self.add_item(VoiceActorSelect(correct_id, options, callback))

class VoiceActorGuess(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.game_cache = {}
        
        from utils.anilist import AniListAPI
        self.anilist = AniListAPI()
        self.session = None
    
    async def get_session(self):
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    @commands.Cog.listener()
    async def on_ready(self):
        print("VoiceActorGuess cog is ready!")
    
    async def fetch_character_with_voice_actor(self, language="JAPANESE"):
        """Fetch a character with voice actor info using a simpler approach"""
        try:
            
            anime_query = """
            query {
              Page(page: 1, perPage: 20) {
                media(type: ANIME, sort: POPULARITY_DESC) {
                  id
                  title {
                    romaji
                    english
                  }
                }
              }
            }
            """
            
            
            session = await self.get_session()
            anime_data = None
            
            async with session.post(
                'https://graphql.anilist.co',
                json={"query": anime_query},
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'}
            ) as response:
                if response.status == 200:
                    anime_data = await response.json()
            
            if not anime_data or 'data' not in anime_data or 'Page' not in anime_data['data']:
                print("Failed to get anime data")
                return None
                
            anime_list = anime_data['data']['Page']['media']
            if not anime_list:
                return None
                
            
            anime = random.choice(anime_list)
            
            
            character_query = """
            query ($mediaId: Int) {
              Media(id: $mediaId) {
                id
                title {
                  romaji
                  english
                }
                characters {
                  edges {
                    node {
                      id
                      name {
                        full
                      }
                      image {
                        large
                      }
                    }
                    voiceActors(language: %s) {
                      id
                      name {
                        full
                      }
                      image {
                        large
                      }
                    }
                  }
                }
              }
            }
            """ % language
            
            character_data = None
            async with session.post(
                'https://graphql.anilist.co',
                json={"query": character_query, "variables": {"mediaId": anime['id']}},
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'}
            ) as response:
                if response.status == 200:
                    character_data = await response.json()
                else:
                    error_text = await response.text()
                    print(f"Error getting characters: {response.status}")
                    print(f"Response: {error_text}")
                    return None
            
            if not character_data or 'data' not in character_data or 'Media' not in character_data['data']:
                print("Failed to get character data")
                return None
                
            media = character_data['data']['Media']
            if 'characters' not in media or 'edges' not in media['characters']:
                print("No character edges found")
                return None
                
            
            valid_char_edges = []
            for edge in media['characters']['edges']:
                if 'voiceActors' in edge and edge['voiceActors']:
                    valid_char_edges.append(edge)
            
            if not valid_char_edges:
                print(f"No characters with {language} voice actors found")
                return None
                
            
            char_edge = random.choice(valid_char_edges)
            
            
            character = {
                "id": char_edge['node']['id'],
                "name": char_edge['node']['name'],
                "image": char_edge['node']['image'],
                "anime": {
                    "id": media['id'],
                    "title": media['title']
                },
                "voiceActors": char_edge['voiceActors']
            }
            
            return character
            
        except Exception as e:
            print(f"Error in fetch_character_with_voice_actor: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def get_random_staff(self, count=3):
        """Get random voice actors/staff"""
        try:
            
            staff_query = """
            query {
              Page(page: %d, perPage: 20) {
                staff(sort: FAVOURITES_DESC) {
                  id
                  name {
                    full
                  }
                  image {
                    large
                  }
                }
              }
            }
            """ % random.randint(1, 10)  
            
            session = await self.get_session()
            staff_data = None
            
            async with session.post(
                'https://graphql.anilist.co',
                json={"query": staff_query},
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'}
            ) as response:
                if response.status == 200:
                    staff_data = await response.json()
                else:
                    error_text = await response.text()
                    print(f"Error getting staff: {response.status}")
                    print(f"Response: {error_text}")
                    return None
            
            if not staff_data or 'data' not in staff_data or 'Page' not in staff_data['data']:
                print("Failed to get staff data")
                return None
                
            staff_list = staff_data['data']['Page']['staff']
            if not staff_list or len(staff_list) < count:
                print("Not enough staff returned")
                return None
                
            
            return random.sample(staff_list, count)
            
        except Exception as e:
            print(f"Error in get_random_staff: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def guess_callback(self, interaction, is_correct, selected_id):
        message = interaction.message
        
        
        game_data = self.game_cache.get(message.id)
        if not game_data:
            await interaction.response.send_message("Sorry, the game data expired!", ephemeral=True)
            return
        
        character = game_data["character"]
        correct_va = game_data["voice_actor"]
        language = game_data["language"]
        
        
        if is_correct:
            embed = nextcord.Embed(
                title="✅ Correct!",
                description=f"**{correct_va['name']['full']}** is indeed the {language} voice actor for **{character['name']['full']}**!",
                color=0x57F287  
            )
            if correct_va["image"]["large"]:
                embed.set_thumbnail(url=correct_va["image"]["large"])
        else:
            
            selected_va_name = "Unknown"
            for option in interaction.message.components[0].children[0].options:
                if option.value == selected_id:
                    selected_va_name = option.label
                    break
                    
            embed = nextcord.Embed(
                title="❌ Incorrect!",
                description=f"You guessed **{selected_va_name}**, but **{correct_va['name']['full']}** is the {language} voice actor for **{character['name']['full']}**.",
                color=0xED4245  
            )
            embed.set_image(url=character["image"]["large"])
            if correct_va["image"]["large"]:
                embed.set_thumbnail(url=correct_va["image"]["large"])
        
        
        anime_title = character["anime"]["title"]["english"] or character["anime"]["title"]["romaji"]
        embed.add_field(name="Anime", value=anime_title, inline=False)
        
        
        await interaction.response.edit_message(embed=embed, view=None)
        
        
        if message.id in self.game_cache:
            del self.game_cache[message.id]
    
    @nextcord.slash_command(name="guess", description="Guess the voice actor for anime characters!")
    async def guess(self, interaction: nextcord.Interaction):
        """Command group for guessing games"""
        pass
    
    @guess.subcommand(name="sub", description="Guess the Japanese voice actor (seiyuu) for an anime character")
    async def guess_sub(self, interaction: nextcord.Interaction):
        """Guess the Japanese voice actor (seiyuu) for a random anime character"""
        await interaction.response.defer()
        
        max_attempts = 3
        character = None
        
        for attempt in range(max_attempts):
            
            character = await self.fetch_character_with_voice_actor(language="JAPANESE")
            
            if character and character.get("voiceActors") and len(character["voiceActors"]) > 0:
                break
                
            if attempt == max_attempts - 1:
                await interaction.followup.send("Sorry, I couldn't find a character with a Japanese voice actor after multiple attempts. Please try again later.")
                return
        
        if not character:
            await interaction.followup.send("Error: Failed to fetch character data. Please try again later.")
            return
            
        
        correct_va = character["voiceActors"][0]
        
        
        other_vas = await self.get_random_staff(count=3)
        
        if not other_vas:
            await interaction.followup.send("Sorry, I couldn't generate quiz options. Please try again later.")
            return
        
        
        other_vas = [va for va in other_vas if va["id"] != correct_va["id"]]
        
        if len(other_vas) < 3 and len(other_vas) > 0:
            other_vas = other_vas[:3]  
        
        
        all_vas = other_vas + [correct_va]
        random.shuffle(all_vas)
        
        
        select_options = []
        for va in all_vas:
            select_options.append(nextcord.SelectOption(
                label=va["name"]["full"],
                value=str(va["id"]),
                description="Select this voice actor"
            ))
        
        
        embed = nextcord.Embed(
            title="Guess the Japanese Voice Actor!",
            description=f"Who voices the character **{character['name']['full']}**?",
            color=0x00A8FF
        )
        
        
        if character["image"]["large"]:
            embed.set_image(url=character["image"]["large"])
        
        
        anime_title = character["anime"]["title"]["english"] or character["anime"]["title"]["romaji"]
        embed.add_field(name="Anime", value=anime_title, inline=False)
        
        
        view = VoiceActorGuessView(str(correct_va["id"]), select_options, self.guess_callback)
        
        
        response = await interaction.followup.send(embed=embed, view=view)
        
        
        if hasattr(response, "id"):
            self.game_cache[response.id] = {
                "character": character,
                "voice_actor": correct_va,
                "language": "Japanese"
            }
    
    @guess.subcommand(name="dub", description="Guess the English voice actor for an anime character")
    async def guess_dub(self, interaction: nextcord.Interaction):
        """Guess the English voice actor for a random anime character"""
        await interaction.response.defer()
        
        max_attempts = 3
        character = None
        
        for attempt in range(max_attempts):
            
            character = await self.fetch_character_with_voice_actor(language="ENGLISH")
            
            if character and character.get("voiceActors") and len(character["voiceActors"]) > 0:
                break
                
            if attempt == max_attempts - 1:
                await interaction.followup.send("Sorry, I couldn't find a character with an English voice actor after multiple attempts. Please try again later.")
                return
        
        if not character:
            await interaction.followup.send("Error: Failed to fetch character data. Please try again later.")
            return
            
        
        correct_va = character["voiceActors"][0]
        
        
        other_vas = await self.get_random_staff(count=3)
        
        if not other_vas:
            await interaction.followup.send("Sorry, I couldn't generate quiz options. Please try again later.")
            return
        
        
        other_vas = [va for va in other_vas if va["id"] != correct_va["id"]]
        
        if len(other_vas) < 3 and len(other_vas) > 0:
            other_vas = other_vas[:3]  
        
        
        all_vas = other_vas + [correct_va]
        random.shuffle(all_vas)
        
        
        select_options = []
        for va in all_vas:
            select_options.append(nextcord.SelectOption(
                label=va["name"]["full"],
                value=str(va["id"]),
                description="Select this voice actor"
            ))
        
        
        embed = nextcord.Embed(
            title="Guess the English Voice Actor!",
            description=f"Who voices the character **{character['name']['full']}**?",
            color=0x00A8FF
        )
        
        
        if character["image"]["large"]:
            embed.set_image(url=character["image"]["large"])
        
        
        anime_title = character["anime"]["title"]["english"] or character["anime"]["title"]["romaji"]
        embed.add_field(name="Anime", value=anime_title, inline=False)
        
        
        view = VoiceActorGuessView(str(correct_va["id"]), select_options, self.guess_callback)
        
        
        response = await interaction.followup.send(embed=embed, view=view)
        
        
        if hasattr(response, "id"):
            self.game_cache[response.id] = {
                "character": character,
                "voice_actor": correct_va,
                "language": "English"
            }
    
    def cog_unload(self):
        
        if self.session and not self.session.closed:
            asyncio.create_task(self.session.close())

def setup(bot):
    bot.add_cog(VoiceActorGuess(bot))
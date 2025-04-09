import aiohttp
import random
import json
from datetime import datetime
import asyncio

"""
    
    We used to have an Anime Gacha Game, but we decided to remove it.
    So some of this code is irrelevent now, but I'm too lazy to remove.
    
"""
class AniListAPI:
    
    def __init__(self):
        self.base_url = "https://graphql.anilist.co"
        self.session = None
        
    async def get_session(self):
        
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
        
    async def _make_request(self, query, variables=None):
        
        if variables is None:
            variables = {}
            
        session = await self.get_session()
        
        try:
            async with session.post(
                self.base_url,
                json={"query": query, "variables": variables},
                headers={"Content-Type": "application/json", "Accept": "application/json"}
            ) as response:
                if response.status == 429:  
                    
                    retry_after = int(response.headers.get('Retry-After', 60))
                    print(f"Rate limited by AniList API, retrying after {retry_after} seconds")
                    await asyncio.sleep(retry_after)
                    return await self._make_request(query, variables)
                    
                return await response.json()
        except Exception as e:
            print(f"Error querying AniList API: {e}")
            return {"errors": [{"message": str(e)}]}
    
    async def get_random_anime_character(self, start_year=2000):
        """Get a random anime character from anime released after the specified year"""
        
        current_year = datetime.now().year

        anime_query = """
        query ($page: Int, $perPage: Int, $startYear: FuzzyDateInt) {
          Page(page: $page, perPage: $perPage) {
            media(type: ANIME, format_in: [TV, MOVIE, OVA], startDate_greater: $startYear, sort: POPULARITY_DESC) {
              id
              title {
                romaji
                english
              }
              startDate {
                year
              }
              coverImage {
                large
              }
            }
          }
        }
        """

        
        page = random.randint(1, 10)

        anime_variables = {
            "page": page,
            "perPage": 50,
            "startYear": start_year * 10000  
        }

        anime_response = await self._make_request(anime_query, anime_variables)

        try:
            anime_list = anime_response["data"]["Page"]["media"]
            if not anime_list:
                return None

            selected_anime = random.choice(anime_list)
            anime_id = selected_anime["id"]
            anime_title = selected_anime["title"]["english"] or selected_anime["title"]["romaji"]

            
            character_query = """
            query ($mediaId: Int, $page: Int, $perPage: Int) {
              Media(id: $mediaId) {
                characters(page: $page, perPage: $perPage, sort: ROLE) {
                  nodes {
                    id
                    name {
                      full
                    }
                    gender
                    image {
                      large
                    }
                    description
                  }
                }
              }
            }
            """

            
            char_page = random.randint(1, 3)  

            character_variables = {
                "mediaId": anime_id,
                "page": char_page,
                "perPage": 25
            }

            character_response = await self._make_request(character_query, character_variables)

            character_list = character_response["data"]["Media"]["characters"]["nodes"]
            if not character_list:
                return await self.get_random_anime_character(start_year)  

            selected_character = random.choice(character_list)

            
            rarity, value = self._calculate_rarity_and_value()

            return {
                "id": selected_character["id"],
                "name": selected_character["name"]["full"],
                "anime": anime_title,
                "anime_id": anime_id,
                "gender": selected_character.get("gender"),
                "description": selected_character.get("description"),
                "image_url": selected_character["image"]["large"],
                "rarity": rarity,
                "value": value
            }

        except (KeyError, TypeError, IndexError) as e:
            print(f"Error fetching anime character: {e}")
            
            return await self.get_random_anime_character(start_year)
    
    def _calculate_rarity_and_value(self):
        """Calculate the rarity and value of a character based on probability"""
        roll = random.random()
        
        if roll < 0.01:  
            return "legendary", 1000
        elif roll < 0.05:  
            return "epic", 500
        elif roll < 0.15:  
            return "rare", 250
        elif roll < 0.40:  
            return "uncommon", 100
        else:  
            return "common", 50
            
    async def search_anime(self, query):
        """Search for anime by title"""
        search_query = """
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
        """
        
        result = await self._make_request(search_query, {'search': query})
        
        if 'errors' in result:
            return None
            
        anime_list = result['data']['Page']['media']
        return anime_list
        
    async def get_airing_anime(self, start_time, end_time):
        """Get anime scheduled to air between the given timestamps"""
        airing_query = """
        query ($start: Int, $end: Int) {
            Page(page: 1, perPage: 50) {
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
        """
        
        variables = {'start': start_time, 'end': end_time}
        result = await self._make_request(airing_query, variables)
        
        if 'errors' in result:
            return None
            
        return result['data']['Page']['airingSchedules']
        
    async def get_anime_details(self, anime_id):
        """Get detailed information about a specific anime"""
        anime_query = """
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
                bannerImage
                format
                episodes
                duration
                status
                seasonYear
                season
                startDate {
                    year
                    month
                    day
                }
                endDate {
                    year
                    month
                    day
                }
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
                tags {
                    name
                    rank
                }
                siteUrl
                averageScore
                popularity
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
        """
        
        result = await self._make_request(anime_query, {'id': anime_id})
        
        if 'errors' in result:
            return None
            
        return result['data']['Media']
        
    async def cleanup(self):
        
        if self.session and not self.session.closed:
            await self.session.close()
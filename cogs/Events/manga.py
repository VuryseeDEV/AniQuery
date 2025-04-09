import nextcord
from nextcord.ext import commands
from nextcord import SlashOption, Interaction
import aiohttp
from typing import List, Dict, Any, Optional


class MangaDex(commands.Cog):
    
    def __init__(self, bot):
        self.bot = bot
        self.base_url = "https://api.mangadex.org"
    
    @nextcord.slash_command(
        name="manga",
        description="MangaDex manga commands"
    )
    async def manga(self, interaction: Interaction):
        """Parent slash command for MangaDex commands"""
        pass
    
    @manga.subcommand(
        name="search",
        description="Search for manga on MangaDex"
    )
    async def manga_search(
        self, 
        interaction: Interaction, 
        name: str = SlashOption(description="You may need to be specific about the title")
    ):
        
        
        await interaction.response.defer()
        
        try:
            
            manga_results = await self.search_manga(name)
            
            if not manga_results:
                await interaction.followup.send("No manga found with that title. Try another search term.")
                return
            
            
            manga = manga_results[0]
            manga_id = manga["id"]
            
            
            manga_details = await self.get_manga_details(manga_id)
            
            
            embed = await self.create_manga_embed(manga_details)
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(f"Error searching for manga: {str(e)}")
    
    async def search_manga(self, title: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search for manga by title"""
        async with aiohttp.ClientSession() as session:
            params = {
                "title": title,
                "limit": limit,
                "order[relevance]": "desc"
            }
            
            async with session.get(f"{self.base_url}/manga", params=params) as response:
                if response.status != 200:
                    return []
                
                data = await response.json()
                return data.get("data", [])
    
    async def get_manga_details(self, manga_id: str) -> Dict[str, Any]:
        
        async with aiohttp.ClientSession() as session:
            
            params = {
                "includes[]": ["cover_art", "author", "artist"] 
            }
            
            async with session.get(f"{self.base_url}/manga/{manga_id}", params=params) as response:
                if response.status != 200:
                    return {}
                
                return await response.json()
    
    async def get_cover_filename(self, manga_id: str, relationships: List[Dict[str, Any]]) -> Optional[str]:
        """Extract the cover filename from relationships"""
        cover_filename = None
        
        for rel in relationships:
            if rel["type"] == "cover_art" and "attributes" in rel:
                cover_filename = rel["attributes"].get("fileName")
                break
        
        return cover_filename
    
    def get_authors_from_relationships(self, relationships: List[Dict[str, Any]]) -> List[str]:
        """Extract author and artist names from relationships"""
        authors = []
        
        for rel in relationships:
            if rel["type"] in ["author", "artist"] and "attributes" in rel:
                author_name = rel["attributes"].get("name")
                if author_name and author_name not in authors:
                    authors.append(author_name)
        
        return authors
    
    async def create_manga_embed(self, manga_data: Dict[str, Any]) -> nextcord.Embed:
    
        if not manga_data or "data" not in manga_data:
            return nextcord.Embed(title="Error", description="Could not create manga embed")
        
        manga = manga_data["data"]
        attributes = manga["attributes"]
        relationships = manga["relationships"]
        
        
        titles = attributes["title"]
        title = titles.get("en") or titles.get("ja") or next(iter(titles.values()))
        
        
        description = ""
        if "description" in attributes and attributes["description"]:
            descriptions = attributes["description"]
            description = descriptions.get("en") or descriptions.get("ja") or next(iter(descriptions.values()), "")
            
            if len(description) > 4000:
                description = description[:4000] + "..."
        
        
        status = attributes.get("status", "unknown")
        status = status.capitalize() if status else "Unknown"
        
        
        cover_filename = await self.get_cover_filename(manga["id"], relationships)
        thumbnail_url = None
        if cover_filename:
            thumbnail_url = f"https://uploads.mangadex.org/covers/{manga['id']}/{cover_filename}.256.jpg"
        
        
        authors = self.get_authors_from_relationships(relationships)
        authors_text = ", ".join(authors) if authors else "Unknown"
        
        
        embed = nextcord.Embed(
            title=title,
            url=f"https://mangadex.org/title/{manga['id']}",
            description=description,
            color=0xF05A28  
        )
        
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
        
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="Author/Artist", value=authors_text, inline=True)
        
        return embed


def setup(bot):
    bot.add_cog(MangaDex(bot))
import yaml
import discord
from pathlib import Path
from typing import Dict, Optional

class EmbedLoader:
    """Load and manage Discord embeds from YAML files"""
    
    def __init__(self, embeds_dir: str = "embeds", default_color: int = 0x00ff00):
        self.embeds_dir = Path(embeds_dir)
        self.default_color = default_color
        self._embeds_cache: Dict[str, discord.Embed] = {}
        self.load_all_embeds()
    
    def load_yaml_file(self, filepath: Path) -> dict:
        """Load a YAML file and return its contents"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
            return {}
    
    def create_embed_from_data(self, data: dict) -> discord.Embed:
        """Convert YAML data to a discord.Embed object"""
        # Get color - use default if None or 0
        color = data.get("color")
        if color is None or color == 0:
            color = self.default_color
        
        # Create embed
        embed = discord.Embed(
            title=data.get("title", ""),
            description=data.get("description", ""),
            color=color
        )
        
        # Add thumbnail
        if thumbnail := data.get("thumbnail"):
            embed.set_thumbnail(url=thumbnail)
        
        # Add image
        if image := data.get("image"):
            embed.set_image(url=image)
        
        # Add footer
        if footer := data.get("footer"):
            embed.set_footer(
                text=footer.get("text"),
                icon_url=footer.get("icon_url")
            )
        
        # Add author
        if author := data.get("author"):
            embed.set_author(
                name=author.get("name"),
                icon_url=author.get("icon_url"),
                url=author.get("url")
            )
        
        # Add fields
        if fields := data.get("fields"):
            for field in fields:
                embed.add_field(
                    name=field.get("name", ""),
                    value=field.get("value", ""),
                    inline=field.get("inline", False)
                )
        
        return embed
    
    def load_all_embeds(self):
        """Load all embeds from YAML files in the embeds directory"""
        if not self.embeds_dir.exists():
            print(f"Warning: Embeds directory '{self.embeds_dir}' does not exist")
            self.embeds_dir.mkdir(parents=True, exist_ok=True)
            return
        
        yaml_files = list(self.embeds_dir.glob("*.yaml")) + list(self.embeds_dir.glob("*.yml"))
        
        if not yaml_files:
            print(f"Warning: No YAML files found in '{self.embeds_dir}'")
            return
        
        for yaml_file in yaml_files:
            try:
                data = self.load_yaml_file(yaml_file)
                if data:
                    for key, embed_data in data.items():
                        self._embeds_cache[key] = self.create_embed_from_data(embed_data)
                    # Don't print here, let main.py handle logging
            except Exception as e:
                print(f"Error processing {yaml_file.name}: {e}")
    
    def get_embed(self, key: str) -> Optional[discord.Embed]:
        """Get an embed by its key"""
        embed = self._embeds_cache.get(key)
        # Return a copy to avoid modifying the cached version
        return embed.copy() if embed else None
    
    def get_all_keys(self) -> list:
        """Get all available embed keys"""
        return list(self._embeds_cache.keys())
    
    def get_keys_by_category(self) -> Dict[str, list]:
        """Organize keys by category based on YAML files"""
        categories = {}
        
        for yaml_file in self.embeds_dir.glob("*.yaml"):
            category_name = yaml_file.stem.capitalize()
            data = self.load_yaml_file(yaml_file)
            if data:
                categories[category_name] = list(data.keys())
        
        return categories
    
    def reload(self):
        """Reload all embeds from files"""
        self._embeds_cache.clear()
        self.load_all_embeds()
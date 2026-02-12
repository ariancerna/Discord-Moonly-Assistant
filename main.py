import discord
from discord.ext import commands
import yaml
from pathlib import Path
from utils.logger import logger
from utils.embed_loader import EmbedLoader

# Load configuration
with open('config/config.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

class MoonlyBot(commands.Bot):
    def __init__(self):
        # Setup intents
        intents = discord.Intents.all()
        
        # Activity setup
        activity_types = {
            "playing": discord.ActivityType.playing,
            "watching": discord.ActivityType.watching,
            "listening": discord.ActivityType.listening,
            "streaming": discord.ActivityType.streaming,
            "competing": discord.ActivityType.competing
        }
        
        activity_type = activity_types.get(
            config['bot']['status']['type'], 
            discord.ActivityType.playing
        )
        
        activity = discord.Activity(
            type=activity_type,
            name=config['bot']['status']['name'],
            url=config['bot']['status'].get('url')
        )
        
        super().__init__(
            command_prefix=config['bot']['prefix'],
            intents=intents,
            activity=activity
        )
        
        self.config = config
        self.embed_loader = None
        self.initial_extensions = [
            'cogs.moderation',
            'cogs.utility',
            'cogs.management',
            'cogs.embeds',
            'cogs.licenses',
            'cogs.reports',
            'cogs.sellauth',
            'cogs.panels'
        ]
        self.synced = False  # Flag to track if we've synced commands
    
    async def setup_hook(self):
        """This is called when the bot starts - loads cogs and syncs commands"""
        logger.info("=" * 60)
        logger.info("🔧 Starting bot setup...")
        logger.info("=" * 60)
        
        # Load embed loader
        try:
            self.embed_loader = EmbedLoader(
                embeds_dir="embeds",
                default_color=self.config['bot']['embed_color']
            )
            logger.info(f"✅ Loaded {len(self.embed_loader.get_all_keys())} embeds")
        except Exception as e:
            logger.error(f"❌ Failed to load embeds: {e}")
        
        # Load cogs
        logger.info("📦 Loading cogs...")
        for extension in self.initial_extensions:
            try:
                await self.load_extension(extension)
                logger.info(f"  ✅ {extension}")
            except Exception as e:
                logger.error(f"  ❌ {extension}: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        logger.info("=" * 60)
        logger.info("✅ Cogs loaded successfully")
        logger.info("=" * 60 + "\n")
    
    async def on_ready(self):
        """Called when bot is ready and connected"""
        if not self.synced:
            logger.info("=" * 60)
            logger.info("🔄 Syncing slash commands...")
            logger.info("=" * 60)
            
            try:
                # Sync globally
                synced = await self.tree.sync()
                logger.info(f"✅ Successfully synced {len(synced)} slash commands globally")
                
                logger.info("📋 Available commands:")
                for cmd in synced:
                    logger.info(f"  • /{cmd.name}")
                                
                self.synced = True
                
            except Exception as e:
                logger.error(f"❌ Failed to sync commands: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        logger.info("=" * 60)
        logger.info(f"🤖 Bot logged in as: {self.user}")
        logger.info(f"   ID: {self.user.id}")
        logger.info(f"🌍 Connected to {len(self.guilds)} server(s):")
        
        for guild in self.guilds:
            logger.info(f"   • {guild.name} (ID: {guild.id}, Members: {guild.member_count})")
        
        total_members = sum(guild.member_count for guild in self.guilds)
        logger.info(f"👥 Total members: {total_members}")
        logger.info(f"🎮 Status: {self.activity.type.name.capitalize()} {self.activity.name}")
        logger.info("=" * 60)
        logger.info("🎉 Bot is fully ready and operational!")
        logger.info("=" * 60 + "\n")

# Create bot instance
bot = MoonlyBot()

@bot.event
async def on_app_command_completion(interaction: discord.Interaction, command):
    logger.info(f"Command used: /{command.name} by {interaction.user} (ID: {interaction.user.id}) in {interaction.guild} (ID: {interaction.guild_id})")

@bot.event
async def on_command_error(ctx, error):
    """Handle errors for prefix commands"""
    if isinstance(error, commands.CommandNotFound):
        return
    logger.error(f"Command error: {error}")

# Run bot
if __name__ == "__main__":
    try:
        logger.info("🚀 Starting Moonly Discord Bot...")
        logger.info(f"📝 Python version: {__import__('sys').version}")
        logger.info(f"📚 Discord.py version: {discord.__version__}\n")
        bot.run(config['bot']['token'])
    except KeyboardInterrupt:
        logger.info("\n⚠️  Bot stopped by user (Ctrl+C)")
    except discord.LoginFailure:
        logger.error("❌ Invalid bot token! Check your config.yaml")
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}")
        import traceback
        logger.error(traceback.format_exc())
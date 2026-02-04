import discord
from discord import app_commands
from discord.ext import commands
from utils.permissions import check_moderator

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
    
    @app_commands.command(name="say", description="Send a message as the bot")
    @app_commands.describe(
        message="The message to send",
        channel="Channel to send the message (optional)",
        attachment="File to attach to the message (optional)"
    )
    async def say(
        self,
        interaction: discord.Interaction,
        message: str,
        channel: discord.TextChannel = None,
        attachment: discord.Attachment = None
    ):
        if not await check_moderator(interaction, self.config['roles']['moderator_role']):
            return
        
        target_channel = channel or interaction.channel
        await interaction.response.defer(ephemeral=True)
        
        try:
            # If there's an attachment, download and send it
            if attachment:
                file = await attachment.to_file()
                await target_channel.send(content=message, file=file)
            else:
                await target_channel.send(message)
            
            await interaction.followup.send(
                f"✅ Message sent successfully to {target_channel.mention}",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Could not send message: {str(e)}",
                ephemeral=True
            )
    
    @app_commands.command(name="nuke", description="Delete and recreate the current channel")
    async def nuke(self, interaction: discord.Interaction):
        if not await check_moderator(interaction, self.config['roles']['moderator_role']):
            return
        
        channel = interaction.channel
        category = channel.category
        position = channel.position
        overwrites = channel.overwrites
        
        try:
            # Delete channel
            await channel.delete()
            
            # Create new channel
            new_channel = await category.create_text_channel(
                name=channel.name,
                position=position
            )
            
            # Restore permissions
            for target, overwrite in overwrites.items():
                await new_channel.set_permissions(target, overwrite=overwrite)
            
            await new_channel.send(f'✅ Channel nuked by `{interaction.user.name}`')
            
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permissions to nuke channels.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )
    
    @app_commands.command(name="purge", description="Delete a specific amount of messages")
    @app_commands.describe(amount="Number of messages to delete (1-1000)")
    async def purge(self, interaction: discord.Interaction, amount: int):
        if not await check_moderator(interaction, self.config['roles']['moderator_role']):
            return
        
        if amount < 1 or amount > 1000:
            await interaction.response.send_message(
                "❌ Amount must be between 1 and 1000.",
                ephemeral=True
            )
            return
        
        try:
            await interaction.response.defer(ephemeral=True)
            
            deleted = await interaction.channel.purge(limit=amount)
            
            await interaction.followup.send(
                f"✅ Successfully deleted {len(deleted)} message(s).",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permissions to delete messages in this channel.",
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"❌ An error occurred while deleting messages: {e}",
                ephemeral=True
            )
    
    @app_commands.command(name="ghost-ping", description="Mention a user and delete it immediately")
    @app_commands.describe(user="User to ghost ping")
    async def ghost_ping(self, interaction: discord.Interaction, user: discord.Member):
        if not await check_moderator(interaction, self.config['roles']['moderator_role']):
            return
        
        await interaction.response.send_message(
            "✅ Ghost ping executed successfully.",
            ephemeral=True
        )
        
        # Send and immediately delete
        msg = await interaction.channel.send(user.mention)
        await msg.delete(delay=0.5)

async def setup(bot):
    await bot.add_cog(Moderation(bot))
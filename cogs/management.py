import discord
from discord import app_commands
from discord.ext import commands
from utils.permissions import has_role

class Management(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
    
    @app_commands.command(name="give-client-role", description="Give the client role to a user")
    @app_commands.describe(user="User to give the client role")
    async def give_client_role(self, interaction: discord.Interaction, user: discord.Member):
        # Check permissions
        support_role_id = self.config['roles']['support_role']
        if not has_role(interaction.user, support_role_id):
            await interaction.response.send_message(
                "❌ You don't have the necessary permissions to give client roles.",
                ephemeral=True
            )
            return
        
        role_id = self.config['roles']['client_role']
        role = interaction.guild.get_role(role_id)
        
        if role is None:
            await interaction.response.send_message(
                f"❌ The role with ID {role_id} doesn't exist on this server.",
                ephemeral=True
            )
            return
        
        if role in user.roles:
            await interaction.response.send_message(
                f"❌ User {user.mention} already has the {role.mention} role.",
                ephemeral=True
            )
            return
        
        try:
            await user.add_roles(role)
            await interaction.response.send_message(
                f"✅ Successfully gave {role.mention} to {user.mention}.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permissions to assign roles.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )
    
    @app_commands.command(name="move-category", description="Move a channel to a different category")
    @app_commands.describe(
        category="Category to move the channel to",
        channel="Channel to move (optional, defaults to current channel)"
    )
    async def move_category(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        channel: discord.TextChannel = None
    ):
        # Check if category is allowed
        if category.id not in self.config['allowed_categories']:
            await interaction.response.send_message(
                "❌ This category is not allowed for moving channels.",
                ephemeral=True
            )
            return
        
        # Check permissions
        support_role_id = self.config['roles']['support_role']
        if not has_role(interaction.user, support_role_id):
            await interaction.response.send_message(
                "❌ You don't have the necessary permissions to move channels.",
                ephemeral=True
            )
            return
        
        target_channel = channel or interaction.channel
        
        try:
            await target_channel.edit(category=category)
            await interaction.response.send_message(
                f"✅ Channel {target_channel.mention} has been moved to category **{category.name}**",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permissions to move channels.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Management(bot))
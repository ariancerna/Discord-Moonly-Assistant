import discord
from typing import Union

def has_role(member: discord.Member, role_id: int) -> bool:
    """Check if member has a specific role by ID"""
    return any(role.id == role_id for role in member.roles)

def has_permission(member: discord.Member, permission: str) -> bool:
    """Check if member has a specific permission"""
    return getattr(member.guild_permissions, permission, False)

def has_role_or_permission(member: discord.Member, role_id: int, permission: str) -> bool:
    """Check if member has either a specific role or permission"""
    return has_role(member, role_id) or has_permission(member, permission)

def is_owner(user_id: int, owner_ids: list) -> bool:
    """Check if user is an owner"""
    return user_id in owner_ids

async def check_moderator(interaction: discord.Interaction, moderator_role_id: int) -> bool:
    """Check if user is moderator and send error message if not"""
    if not has_role_or_permission(interaction.user, moderator_role_id, 'manage_messages'):
        await interaction.response.send_message(
            "❌ You don't have the necessary permissions to use this command.",
            ephemeral=True
        )
        return False
    return True

async def check_admin(interaction: discord.Interaction, admin_role_id: int) -> bool:
    """Check if user is admin and send error message if not"""
    if not has_role_or_permission(interaction.user, admin_role_id, 'manage_guild'):
        await interaction.response.send_message(
            "❌ You don't have administrator permissions to use this command.",
            ephemeral=True
        )
        return False
    return True
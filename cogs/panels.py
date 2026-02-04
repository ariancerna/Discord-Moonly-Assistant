import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import yaml
from pathlib import Path

with open('config/panels_config.yaml', 'r', encoding='utf-8') as f:
    panels_config = yaml.safe_load(f)

def save_config():
    with open('config/panels_config.yaml', 'w', encoding='utf-8') as f:
        yaml.safe_dump(panels_config, f, allow_unicode=True)

class ShowcaseDropdown(discord.ui.Select):
    def __init__(self):
        apps = panels_config['panels']['showcase']['apps']
        options = [
            discord.SelectOption(
                label=app,
                description=f"Haz clic para ver la vista previa de {app}"
            )
            for app in apps.keys()
        ]
        super().__init__(
            placeholder="Selecciona un producto 🎥",
            options=options,
            custom_id="showcase_dropdown"
        )
    
    async def callback(self, interaction: discord.Interaction):
        app = self.values[0]
        apps = panels_config['panels']['showcase']['apps']
        link = apps.get(app, "No link available.")
        await interaction.response.send_message(
            f"## `🍿` {app}\n{link}",
            ephemeral=True
        )

class ShowcaseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ShowcaseDropdown())

class LicenseModal(discord.ui.Modal, title="🔑 Reiniciar HWID"):
    def __init__(self, app_name, seller_key, user, bot):
        super().__init__()
        self.app_name = app_name
        self.seller_key = seller_key
        self.user = user
        self.bot = bot
        
        self.license = discord.ui.TextInput(
            label="Introduce tu licencia",
            placeholder="Ejemplo: ABCD-1234",
            required=True,
            max_length=64
        )
        self.add_item(self.license)
    
    async def on_submit(self, interaction: discord.Interaction):
        license_key = str(self.license.value)
        url = f"https://keyauth.win/api/seller/?sellerkey={self.seller_key}&type=resetuser&user={license_key}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                try:
                    result = await response.json()
                except:
                    result = {"success": False, "message": "Error connecting to KeyAuth"}
        
        if result.get("success"):
            await interaction.response.send_message(
                f"✅ HWID reiniciado correctamente en **{self.app_name}**.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ No se pudo reiniciar el HWID.\n**Motivo:** {result.get('message', 'Licencia inválida o error desconocido')}",
                ephemeral=True
            )
        
        log_channel_id = panels_config['panels']['hwid_reset']['log_channel_id']
        log_channel = self.bot.get_channel(log_channel_id)
        
        if log_channel:
            success = result.get("success")
            embed = discord.Embed(
                title="✅ Reinicio de HWID Exitoso" if success else "❌ Error en Reinicio de HWID",
                description="Un intento de reinicio de HWID ha sido procesado.",
                color=discord.Color.green() if success else discord.Color.red()
            )
            
            embed.add_field(
                name="👤 Usuario",
                value=f"{interaction.user.mention}\n`{interaction.user.id}`",
                inline=True
            )
            embed.add_field(
                name="📦 Aplicación",
                value=f"**{self.app_name}**",
                inline=True
            )
            embed.add_field(
                name="🔑 Licencia",
                value=f"`{license_key}`",
                inline=False
            )
            embed.add_field(
                name="📊 Resultado",
                value="✅ **HWID reiniciado con éxito**" if success else f"❌ **{result.get('message', 'Error desconocido')}**",
                inline=False
            )
            
            embed.set_thumbnail(url="https://i.imgur.com/p1BgaKk.png")
            embed.set_footer(
                text=f"Registro generado • {interaction.user}",
                icon_url=interaction.user.display_avatar.url
            )
            embed.timestamp = discord.utils.utcnow()
            
            await log_channel.send(embed=embed)

class HWIDDropdown(discord.ui.Select):
    def __init__(self, bot):
        self.bot = bot
        apps = panels_config['panels']['hwid_reset']['apps']
        options = [
            discord.SelectOption(
                label=app,
                description=f"Reiniciar HWID de {app}"
            )
            for app in apps.keys()
        ]
        super().__init__(
            placeholder="Selecciona una aplicación para reiniciar HWID 📂",
            options=options,
            custom_id="hwid_dropdown"
        )
    
    async def callback(self, interaction: discord.Interaction):
        app = self.values[0]
        apps = panels_config['panels']['hwid_reset']['apps']
        seller_key = apps[app]['seller_key']
        
        modal = LicenseModal(
            app_name=app,
            seller_key=seller_key,
            user=interaction.user,
            bot=self.bot
        )
        await interaction.response.send_modal(modal)

class HWIDView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.add_item(HWIDDropdown(bot))

class Panels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.loop.create_task(self._reconnect_panels())
    
    async def _reconnect_panels(self):
        await self.bot.wait_until_ready()
        
        showcase_data = panels_config['panels']['showcase']
        if showcase_data.get('channel_id') and showcase_data.get('message_id'):
            try:
                channel = self.bot.get_channel(showcase_data['channel_id'])
                if channel:
                    message = await channel.fetch_message(showcase_data['message_id'])
                    await message.edit(view=ShowcaseView())
            except Exception as e:
                print(f"⚠️ Could not reconnect Showcase panel: {e}")
        
        # Reconnect HWID Reset panel
        hwid_data = panels_config['panels']['hwid_reset']
        if hwid_data.get('channel_id') and hwid_data.get('message_id'):
            try:
                channel = self.bot.get_channel(hwid_data['channel_id'])
                if channel:
                    message = await channel.fetch_message(hwid_data['message_id'])
                    await message.edit(view=HWIDView(self.bot))
            except Exception as e:
                print(f"⚠️ Could not reconnect HWID Reset panel: {e}")
    
    @app_commands.command(name="create-panel", description="Create a panel (Showcase or HWID Reset)")
    @app_commands.describe(panel_type="Select the type of panel to create")
    @app_commands.choices(panel_type=[
        app_commands.Choice(name="📺 Showcase Panel", value="showcase"),
        app_commands.Choice(name="🔑 HWID Reset Panel", value="hwid_reset")
    ])
    async def create_panel(
        self,
        interaction: discord.Interaction,
        panel_type: app_commands.Choice[str]
    ):
        # Check permissions
        allowed_role_id = panels_config['permissions']['allowed_role_id']
        role = interaction.guild.get_role(allowed_role_id)
        
        if role not in interaction.user.roles:
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.",
                ephemeral=True
            )
            return
        
        if panel_type.value == "showcase":
            embed = discord.Embed(
                description=(
                    "# <:BrandColor:1409720412962820166> Panel de Showcase\n\n"
                    "```Usa el menú desplegable de abajo para elegir la herramienta de la que quieras obtener el video.```\n"
                    "# 🛒 ¿Cómo puedo comprar?\n"
                    "```Después de ver la vista previa del producto, podrías estar interesado en comprarlo. "
                    "Puedes comprar cualquier producto desde nuestro sitio web a continuación.```\n"
                    "[Website](https://moonlygg.com)"
                ),
                color=0x6c02ff
            )
            embed.set_thumbnail(url="https://i.imgur.com/p1BgaKk.png")
            
            msg = await interaction.channel.send(embed=embed, view=ShowcaseView())
            
            # Save panel info
            panels_config['panels']['showcase']['channel_id'] = interaction.channel.id
            panels_config['panels']['showcase']['message_id'] = msg.id
            save_config()
            
            await interaction.response.send_message("✅ Showcase panel created.", ephemeral=True)
        
        elif panel_type.value == "hwid_reset":
            embed = discord.Embed(
                description=(
                    "# <:BrandColor:1409720412962820166> Panel de Reinicio de HWID\n\n"
                    "```Usa el menú desplegable de abajo para elegir la herramienta en la que quieres reiniciar el HWID.```\n"
                    "# ℹ️ ¿Cómo reinicio mi HWID?\n"
                    "```Necesitarás ingresar tu clave de licencia. "
                    "La licencia es obligatoria y debe coincidir con nuestros registros.```"
                ),
                color=0x6c02ff
            )
            embed.set_thumbnail(url="https://i.imgur.com/p1BgaKk.png")
            
            msg = await interaction.channel.send(embed=embed, view=HWIDView(self.bot))
            
            panels_config['panels']['hwid_reset']['channel_id'] = interaction.channel.id
            panels_config['panels']['hwid_reset']['message_id'] = msg.id
            save_config()
            
            await interaction.response.send_message("✅ HWID Reset panel created.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Panels(bot))
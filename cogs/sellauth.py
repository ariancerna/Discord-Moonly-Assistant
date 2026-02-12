import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
from datetime import datetime

from utils.permissions import has_role


class SellAuth(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config

        self.base_url = "https://api.sellauth.com"
        self.api_key = self.config["sellauth"]["api_key"]
        self.shop_id = self.config["sellauth"]["shop_id"]

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }

        self.color_success = 0x2ecc71 
        self.color_error = 0xe74c3c  
        self.color_warning = 0xf39c12 
        self.color_info = 0x3498db 

    sellauth = app_commands.Group(
        name="sellauth",
        description="SellAuth store management"
    )

    process_group = app_commands.Group(
        name="process",
        description="Process actions",
        parent=sellauth
    )

    send_group = app_commands.Group(
        name="send",
        description="Send products or licenses",
        parent=sellauth
    )

    # =================================================
    # /sellauth process invoice
    # =================================================
    @process_group.command(name="invoice", description="Process an invoice manually")
    @app_commands.describe(invoice_unique_id="The unique ID of the invoice to process")
    async def process_invoice(
        self,
        interaction: discord.Interaction,
        invoice_unique_id: str
    ):
        await interaction.response.defer(ephemeral=True)

        # Check permissions
        admin_role_id = self.config["roles"]["admin_role"]
        if not has_role(interaction.user, admin_role_id):
            embed = discord.Embed(
                title="🔒 Access Denied",
                description="You don't have permission to use this command.",
                color=self.color_error
            )
            embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        try:
            async with aiohttp.ClientSession() as session:
                # Obtener información de la factura
                url_invoice = f"{self.base_url}/v1/shops/{self.shop_id}/invoices/{invoice_unique_id}"
                async with session.get(url_invoice, headers=self.headers) as resp:
                    if resp.status == 404:
                        embed = discord.Embed(
                            title="❌ Invoice Not Found",
                            description=f"No invoice found with ID: `{invoice_unique_id}`",
                            color=self.color_error
                        )
                        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
                        return await interaction.followup.send(embed=embed, ephemeral=True)
                    
                    if resp.status != 200:
                        error_text = await resp.text()
                        embed = discord.Embed(
                            title="⚠️ API Error",
                            description=f"Failed to fetch invoice. Status code: {resp.status}",
                            color=self.color_warning
                        )
                        embed.add_field(name="Error Details", value=f"```{error_text[:1000]}```", inline=False)
                        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
                        return await interaction.followup.send(embed=embed, ephemeral=True)

                    data = await resp.json()
                    invoice_id_numeric = data["id"]

                # Procesar la factura
                url_process = f"{self.base_url}/v1/shops/{self.shop_id}/invoices/{invoice_id_numeric}/process"
                async with session.get(url_process, headers=self.headers) as resp_process:
                    if resp_process.status != 200:
                        embed = discord.Embed(
                            title="⚠️ Processing Failed",
                            description="Failed to process the invoice.",
                            color=self.color_warning
                        )
                        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
                        return await interaction.followup.send(embed=embed, ephemeral=True)

            embed = discord.Embed(
                title="✅ Invoice Processed Successfully",
                description="The invoice has been processed and the buyer should receive their products.",
                color=self.color_success,
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(name="📧 Buyer Email", value=f"`{data.get('email', 'N/A')}`", inline=True)
            embed.add_field(name="🆔 Invoice ID", value=f"`{invoice_unique_id}`", inline=True)
            embed.add_field(name="💰 Total", value=f"${data.get('total', 0):.2f}", inline=True)
            
            if data.get('product_name'):
                embed.add_field(name="📦 Product", value=data.get('product_name'), inline=False)
            
            embed.set_footer(text=f"Processed by {interaction.user}", icon_url=interaction.user.display_avatar.url)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except aiohttp.ClientError as e:
            embed = discord.Embed(
                title="🌐 Connection Error",
                description="Failed to connect to SellAuth API.",
                color=self.color_error
            )
            embed.add_field(name="Error", value=f"```{str(e)[:1000]}```", inline=False)
            embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="⚠️ Unexpected Error",
                description="An unexpected error occurred while processing the invoice.",
                color=self.color_error
            )
            embed.add_field(name="Error", value=f"```{str(e)[:1000]}```", inline=False)
            embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            await interaction.followup.send(embed=embed, ephemeral=True)

    # =================================================
    # /sellauth send serials
    # =================================================
    @send_group.command(name="serials", description="Send serials/licenses to a user")
    @app_commands.describe(
        product_id="The ID of the product",
        variant_id="The variant/deliverable ID",
        user="The user to send the serials to",
        amount="Number of serials to send"
    )
    async def send_serials(
        self,
        interaction: discord.Interaction,
        product_id: int,
        variant_id: int,
        user: discord.Member,
        amount: int
    ):
        await interaction.response.defer(ephemeral=True)

        # Check permissions
        admin_role_id = self.config["roles"]["admin_role"]
        if not has_role(interaction.user, admin_role_id):
            embed = discord.Embed(
                title="🔒 Access Denied",
                description="You don't have permission to use this command.",
                color=self.color_error
            )
            embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        if amount <= 0:
            embed = discord.Embed(
                title="❌ Invalid Amount",
                description="Amount must be greater than 0.",
                color=self.color_error
            )
            embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        try:
            async with aiohttp.ClientSession() as session:
                # Obtener información del producto
                url_product = f"{self.base_url}/v1/shops/{self.shop_id}/products/{product_id}"
                async with session.get(url_product, headers=self.headers) as resp:
                    if resp.status != 200:
                        embed = discord.Embed(
                            title="❌ Product Not Found",
                            description=f"No product found with ID: `{product_id}`",
                            color=self.color_error
                        )
                        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
                        return await interaction.followup.send(embed=embed, ephemeral=True)
                    
                    product_info = await resp.json()

                product_name = product_info.get("name", "Unknown Product")

                # Obtener stock
                url_stock = f"{self.base_url}/v1/shops/{self.shop_id}/products/{product_id}/deliverables/{variant_id}"
                async with session.get(url_stock, headers=self.headers) as resp:
                    if resp.status != 200:
                        embed = discord.Embed(
                            title="❌ Variant Not Found",
                            description=f"No variant found with ID: `{variant_id}`",
                            color=self.color_error
                        )
                        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
                        return await interaction.followup.send(embed=embed, ephemeral=True)
                    
                    licenses = await resp.json()

                # Verificar stock disponible
                if len(licenses) < amount:
                    embed = discord.Embed(
                        title="⚠️ Insufficient Stock",
                        description=f"Not enough serials available.",
                        color=self.color_warning
                    )
                    embed.add_field(name="📦 Available", value=f"`{len(licenses)}`", inline=True)
                    embed.add_field(name="🎯 Requested", value=f"`{amount}`", inline=True)
                    embed.add_field(name="❌ Missing", value=f"`{amount - len(licenses)}`", inline=True)
                    embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
                    return await interaction.followup.send(embed=embed, ephemeral=True)

                to_send = licenses[:amount]
                remaining = licenses[amount:]

                serial_text = "\n".join(to_send)

                # Enviar DM al usuario PRIMERO (antes de actualizar stock)
                user_embed = discord.Embed(
                    title="🎟 Your Product Licenses",
                    description=f"You've received **{amount}** license(s) for **{product_name}**!",
                    color=self.color_success,
                    timestamp=datetime.utcnow()
                )
                user_embed.add_field(name="📋 Your Serials", value=f"```\n{serial_text}\n```", inline=False)
                user_embed.add_field(name="ℹ️ Important", value="Please keep these serials safe and do not share them with anyone.", inline=False)
                
                if interaction.guild and interaction.guild.icon:
                    user_embed.set_footer(text=f"Sent by {interaction.guild.name}", icon_url=interaction.guild.icon.url)
                else:
                    user_embed.set_footer(text=f"Sent from Discord")

                try:
                    await user.send(embed=user_embed)
                except discord.Forbidden:
                    embed = discord.Embed(
                        title="❌ DM Failed",
                        description=f"Cannot send DM to {user.mention}. They have DMs disabled or have blocked the bot.",
                        color=self.color_error
                    )
                    embed.add_field(name="⚠️ Action Required", value="The serials were **not** sent and stock was **not** updated.", inline=False)
                    embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
                    return await interaction.followup.send(embed=embed, ephemeral=True)

                # SOLO SI EL DM FUE EXITOSO, actualizar stock
                url_ow = f"{self.base_url}/v1/shops/{self.shop_id}/products/{product_id}/deliverables/overwrite/{variant_id}"
                async with session.put(url_ow, headers=self.headers, json={"deliverables": remaining}) as resp_update:
                    if resp_update.status != 200:
                        embed = discord.Embed(
                            title="⚠️ Stock Update Failed",
                            description="Serials were sent but failed to update stock. Please update manually!",
                            color=self.color_warning
                        )
                        embed.add_field(name="⚠️ Warning", value="The user received the serials but the stock count may be incorrect.", inline=False)
                        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
                        return await interaction.followup.send(embed=embed, ephemeral=True)

            # Embed de confirmación mejorado
            embed = discord.Embed(
                title="✅ Serials Delivered Successfully",
                description=f"Successfully sent **{amount}** serial(s) to {user.mention}",
                color=self.color_success,
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(name="📦 Product", value=f"`{product_name}`", inline=True)
            embed.add_field(name="🎯 Quantity", value=f"`{amount}`", inline=True)
            embed.add_field(name="👤 Recipient", value=user.mention, inline=True)
            embed.add_field(name="📊 Remaining Stock", value=f"`{len(remaining)}`", inline=True)
            embed.add_field(name="🆔 Product ID", value=f"`{product_id}`", inline=True)
            embed.add_field(name="🔖 Variant ID", value=f"`{variant_id}`", inline=True)
            
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(text=f"Sent by {interaction.user}", icon_url=interaction.user.display_avatar.url)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except aiohttp.ClientError as e:
            embed = discord.Embed(
                title="🌐 Connection Error",
                description="Failed to connect to SellAuth API.",
                color=self.color_error
            )
            embed.add_field(name="Error", value=f"```{str(e)[:1000]}```", inline=False)
            embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="⚠️ Unexpected Error",
                description="An unexpected error occurred while sending serials.",
                color=self.color_error
            )
            embed.add_field(name="Error", value=f"```{str(e)[:1000]}```", inline=False)
            embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(SellAuth(bot))
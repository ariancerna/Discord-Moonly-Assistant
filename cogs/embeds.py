from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
import copy
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

from utils.free_translation import FreeGoogleTranslationService, TranslationError


MAX_BUILDER_BUTTONS = 5
# Five keeps the full message below Discord's 40-component limit, including
# thumbnail, banner, five button sections, and the translation selector.
MAX_ANNOUNCEMENT_SECTIONS = 5
DEFAULT_BANNER_URL = "https://i.imgur.com/cg47TUW.png"
DEFAULT_THUMBNAIL_URL = "https://i.imgur.com/p1BgaKk.png"
DEFAULT_TICKET_BUTTON_URL = (
    "https://discord.com/channels/1159639252838129704/1159646450704203821"
)

TRANSLATION_LANGUAGES = (
    ("🇬🇧", "English", "en"),
    ("🇩🇪", "Deutsch", "de"),
    ("🇫🇷", "Français", "fr"),
    ("🇪🇸", "Español", "es"),
    ("🇧🇷", "Português", "pt"),
    ("🇷🇺", "Русский", "ru"),
    ("🇨🇳", "中文", "zh-CN"),
    ("🇸🇦", "العربية", "ar"),
    ("🇮🇹", "Italiano", "it"),
    ("🇳🇱", "Nederlands", "nl"),
    ("🇮🇳", "हिन्दी", "hi"),
    ("🇮🇩", "Bahasa Indonesia", "id"),
    ("🇯🇵", "日本語", "ja"),
    ("🇰🇷", "한국어", "ko"),
    ("🇻🇳", "Tiếng Việt", "vi"),
    ("🇹🇷", "Türkçe", "tr"),
    ("🇵🇱", "Polski", "pl"),
    ("🇺🇦", "Українська", "uk"),
    ("🇹🇭", "ไทย", "th"),
    ("🇸🇪", "Svenska", "sv"),
)


@dataclass
class EmbedButtonData:
    section_text: str
    label: str
    url: str
    emoji: Optional[str] = None


@dataclass
class EmbedDraft:
    channel: discord.abc.Messageable
    title: str = ""
    description: str = ""
    color: int = 0x6C02FF
    banner_url: Optional[str] = DEFAULT_BANNER_URL
    thumbnail_url: Optional[str] = DEFAULT_THUMBNAIL_URL
    mention_everyone: bool = False
    translation_enabled: bool = True
    sections: list[str] = field(default_factory=list)
    buttons: list[EmbedButtonData] = field(default_factory=list)
    target_message: Optional[discord.Message] = field(default=None, repr=False)


def parse_hex_color(value: str, default: int) -> int:
    """Parse #RRGGBB, RRGGBB or 0xRRGGBB into a Discord colour."""
    cleaned = value.strip().lower()
    if not cleaned:
        return default
    if cleaned.startswith("#"):
        cleaned = cleaned[1:]
    elif cleaned.startswith("0x"):
        cleaned = cleaned[2:]
    if len(cleaned) != 6 or any(char not in "0123456789abcdef" for char in cleaned):
        raise ValueError("El color debe tener el formato #RRGGBB, por ejemplo #00D4FF.")
    return int(cleaned, 16)


def validate_web_url(value: str, field_name: str) -> Optional[str]:
    """Return a normalised HTTP(S) URL or raise a user-facing validation error."""
    cleaned = value.strip()
    if not cleaned:
        return None
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} debe ser una URL completa que empiece por http:// o https://.")
    return cleaned


def build_components_v2(
    draft: EmbedDraft,
    translation_service: Optional[FreeGoogleTranslationService] = None,
    *,
    translation_disabled: bool = False,
) -> discord.ui.LayoutView:
    """Build a Components V2 message matching Discord's modern container layout."""
    view = discord.ui.LayoutView(timeout=None)
    items: list[discord.ui.Item] = []

    main_text = draft.description
    if draft.title:
        main_text = f"## {draft.title}\n{main_text}"

    if draft.thumbnail_url:
        items.append(
            discord.ui.Section(
                main_text,
                accessory=discord.ui.Thumbnail(draft.thumbnail_url),
            )
        )
    else:
        items.append(discord.ui.TextDisplay(main_text))

    for section in draft.sections:
        items.append(discord.ui.Separator())
        items.append(discord.ui.TextDisplay(section))

    for button in draft.buttons:
        items.append(discord.ui.Separator())
        items.append(
            discord.ui.Section(
                button.section_text,
                accessory=discord.ui.Button(
                    label=button.label,
                    url=button.url,
                    emoji=button.emoji or None,
                ),
            )
        )

    if draft.banner_url:
        items.append(discord.ui.Separator())
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=draft.banner_url)
        items.append(gallery)

    if translation_service is not None:
        items.append(discord.ui.Separator())
        items.append(
            discord.ui.ActionRow(
                TranslationSelect(translation_service, disabled=translation_disabled)
            )
        )

    if draft.mention_everyone:
        view.add_item(discord.ui.TextDisplay("||@everyone||"))
    view.add_item(discord.ui.Container(*items, accent_color=draft.color))
    if view.content_length() > 4000:
        raise ValueError(
            f"el texto visible usa {view.content_length()}/4000 caracteres; reduce el contenido"
        )
    return view


def draft_content_length(draft: EmbedDraft) -> int:
    """Count all visible text as Discord does for a LayoutView."""
    main_length = len(draft.description)
    if draft.title:
        main_length += len(draft.title) + 4  # "## " plus the newline.
    if draft.mention_everyone:
        main_length += 13  # Standalone "||@everyone||" text display.
    return (
        main_length
        + sum(len(section) for section in draft.sections)
        + sum(len(button.section_text) for button in draft.buttons)
    )


def has_primary_content(draft: EmbedDraft) -> bool:
    return bool(draft.title.strip() or draft.description.strip())


def publication_mentions(draft: EmbedDraft) -> discord.AllowedMentions:
    """Allow only the optional @everyone ping; never ping user or role mentions."""
    return discord.AllowedMentions(
        everyone=draft.mention_everyone,
        users=False,
        roles=False,
        replied_user=False,
    )


def draft_to_data(draft: EmbedDraft) -> dict:
    return {
        "channel_id": getattr(draft.channel, "id", None),
        "title": draft.title,
        "description": draft.description,
        "color": draft.color,
        "banner_url": draft.banner_url,
        "thumbnail_url": draft.thumbnail_url,
        "mention_everyone": draft.mention_everyone,
        "translation_enabled": draft.translation_enabled,
        "sections": list(draft.sections),
        "buttons": [
            {
                "section_text": button.section_text,
                "label": button.label,
                "url": button.url,
                "emoji": button.emoji,
            }
            for button in draft.buttons
        ],
    }


def draft_from_data(data: dict, channel: discord.abc.Messageable) -> EmbedDraft:
    return EmbedDraft(
        channel=channel,
        title=str(data.get("title", "")),
        description=str(data.get("description", "")),
        color=int(data.get("color", 0x6C02FF)),
        banner_url=data.get("banner_url"),
        thumbnail_url=data.get("thumbnail_url"),
        mention_everyone=bool(data.get("mention_everyone", False)),
        translation_enabled=bool(data.get("translation_enabled", True)),
        sections=[str(section) for section in data.get("sections", [])],
        buttons=[
            EmbedButtonData(
                section_text=str(button.get("section_text", "")),
                label=str(button.get("label", "")),
                url=str(button.get("url", "")),
                emoji=button.get("emoji"),
            )
            for button in data.get("buttons", [])
        ],
    )


async def translate_draft_data(
    data: dict,
    target_language: str,
    service: FreeGoogleTranslationService,
) -> dict:
    translated_data = copy.deepcopy(data)
    texts = [
        str(translated_data.get("title", "")),
        str(translated_data.get("description", "")),
    ]
    texts.extend(str(section) for section in translated_data.get("sections", []))
    for button in translated_data.get("buttons", []):
        texts.append(str(button.get("section_text", "")))
        texts.append(str(button.get("label", "")))

    translated = iter(await service.translate_many(texts, target_language))
    translated_data["title"] = next(translated)
    translated_data["description"] = next(translated)
    translated_data["sections"] = [
        next(translated) for _ in translated_data.get("sections", [])
    ]
    for button in translated_data.get("buttons", []):
        button["section_text"] = next(translated)
        button["label"] = next(translated)[:80]

    # A private translation must never repeat a mass notification.
    translated_data["mention_everyone"] = False
    return translated_data


class TranslationSelect(discord.ui.Select):
    def __init__(
        self,
        service: FreeGoogleTranslationService,
        *,
        disabled: bool = False,
    ):
        self.translation_service = service
        options = [
            discord.SelectOption(label=name, value=code, emoji=flag)
            for flag, name, code in TRANSLATION_LANGUAGES
        ]
        super().__init__(
            placeholder="🌐 Traducir este mensaje...",
            custom_id="professional_embed_translate:v1",
            options=options,
            min_values=1,
            max_values=1,
            disabled=disabled,
        )

    async def callback(self, interaction: discord.Interaction):
        language = self.values[0]
        await interaction.response.defer(ephemeral=True, thinking=True)
        if interaction.message is None or interaction.channel is None:
            await interaction.followup.send(
                "❌ No pude identificar la publicación original.",
                ephemeral=True,
            )
            return

        message_id = interaction.message.id
        try:
            translated_data = self.translation_service.store.get_translation(
                message_id, language
            )
            if (
                translated_data is not None
                and self.translation_service.contains_error_payload(translated_data)
            ):
                self.translation_service.store.delete_translation(message_id, language)
                translated_data = None
            if translated_data is None:
                retry_after = self.translation_service.translation_retry_after(
                    interaction.user.id
                )
                if retry_after > 0:
                    await interaction.followup.send(
                        f"⏳ Espera {retry_after:.0f} segundos antes de solicitar otra traducción nueva.",
                        ephemeral=True,
                    )
                    return
                source_data = self.translation_service.store.get_source(message_id)
                if source_data is None:
                    await interaction.followup.send(
                        "❌ Esta publicación es anterior al sistema de traducción. Vuelve a publicarla con `/crear-embed`.",
                        ephemeral=True,
                    )
                    return
                translated_data = await translate_draft_data(
                    source_data,
                    language,
                    self.translation_service,
                )

            translated_draft = draft_from_data(translated_data, interaction.channel)
            translated_view = build_components_v2(translated_draft)
            self.translation_service.store.save_translation(
                message_id,
                language,
                translated_data,
            )
        except TranslationError as error:
            await interaction.followup.send(f"❌ {error}", ephemeral=True)
            return
        except (TypeError, ValueError) as error:
            await interaction.followup.send(
                f"❌ La traducción superó un límite de Discord: {error}",
                ephemeral=True,
            )
            return
        except Exception:
            await interaction.followup.send(
                "❌ No se pudo traducir el mensaje en este momento. Inténtalo nuevamente más tarde.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            view=translated_view,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class PersistentTranslationView(discord.ui.LayoutView):
    def __init__(self, service: FreeGoogleTranslationService):
        super().__init__(timeout=None)
        self.add_item(discord.ui.ActionRow(TranslationSelect(service)))


def builder_status(draft: EmbedDraft) -> str:
    plural = "botón" if len(draft.buttons) == 1 else "botones"
    everyone_status = "🟢 Sí" if draft.mention_everyone else "⚫ No"
    translation_status = "🟢 Activo" if draft.translation_enabled else "⚫ Desactivado"
    action = "Editando publicación" if draft.target_message else "Creador de publicación profesional"
    target = f"Mensaje: **{draft.target_message.id}**\n" if draft.target_message else ""
    autosave = "" if draft.target_message else "\n💾 **Borrador guardado automáticamente.**\n"
    return (
        f"🧰 **{action}**\n"
        f"Destino: {draft.channel.mention}\n"
        f"{target}"
        f"Configurados: **{len(draft.buttons)}/{MAX_BUILDER_BUTTONS} {plural}**\n\n"
        f"Secciones separadas: **{len(draft.sections)}/{MAX_ANNOUNCEMENT_SECTIONS}**\n"
        f"Notificar a @everyone: **{everyone_status}**\n"
        f"Traductor: **{translation_status}**\n\n"
        f"{autosave}"
        "Puedes editar el contenido, agregar botones, revisar una vista previa privada "
        "y publicarlo cuando esté listo."
    )


class EmbedBasicsModal(discord.ui.Modal):
    def __init__(
        self,
        draft: EmbedDraft,
        translation_service: FreeGoogleTranslationService,
        controls: Optional["EmbedBuilderControls"] = None,
    ):
        modal_title = "Editar publicación" if draft.target_message else "Crear embed profesional"
        super().__init__(title=modal_title, timeout=600)
        self.draft = draft
        self.translation_service = translation_service
        self.controls = controls

        self.title_input = discord.ui.TextInput(
            label="Título",
            placeholder="Ejemplo: 🔐 Proyecto privado",
            default=draft.title or None,
            required=False,
            max_length=250,
        )
        self.description_input = discord.ui.TextInput(
            label="Contenido",
            placeholder="Admite Markdown, emojis y menciones de Discord.",
            default=draft.description or None,
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=3000,
        )
        self.color_input = discord.ui.TextInput(
            label="Color hexadecimal",
            placeholder="#00D4FF",
            default=f"#{draft.color:06X}",
            required=False,
            max_length=8,
        )
        self.banner_input = discord.ui.TextInput(
            label="URL del banner inferior",
            placeholder="Borra este campo para publicar sin banner",
            default=draft.banner_url,
            required=False,
            max_length=500,
        )
        self.thumbnail_input = discord.ui.TextInput(
            label="URL del thumbnail lateral",
            placeholder="Borra este campo para publicar sin thumbnail",
            default=draft.thumbnail_url,
            required=False,
            max_length=500,
        )
        for item in (
            self.title_input,
            self.description_input,
            self.color_input,
            self.banner_input,
            self.thumbnail_input,
        ):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            color = parse_hex_color(str(self.color_input), self.draft.color)
            banner_url = validate_web_url(str(self.banner_input), "El banner")
            thumbnail_url = validate_web_url(str(self.thumbnail_input), "El thumbnail")
        except ValueError as error:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return

        description = str(self.description_input).strip()

        previous = (
            self.draft.title,
            self.draft.description,
            self.draft.color,
            self.draft.banner_url,
            self.draft.thumbnail_url,
        )
        self.draft.title = str(self.title_input).strip()
        self.draft.description = description
        self.draft.color = color
        self.draft.banner_url = banner_url
        self.draft.thumbnail_url = thumbnail_url
        if draft_content_length(self.draft) > 4000:
            used = draft_content_length(self.draft)
            (
                self.draft.title,
                self.draft.description,
                self.draft.color,
                self.draft.banner_url,
                self.draft.thumbnail_url,
            ) = previous
            await interaction.response.send_message(
                f"❌ El texto visible usa {used}/4000 caracteres. Reduce el contenido e inténtalo de nuevo.",
                ephemeral=True,
            )
            return

        if self.controls is None:
            controls = EmbedBuilderControls(
                interaction.user.id,
                self.draft,
                self.translation_service,
            )
            controls.persist_draft()
            await interaction.response.send_message(
                builder_status(self.draft),
                view=controls,
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        else:
            self.controls.persist_draft()
            self.controls.refresh()
            await interaction.response.edit_message(
                content=builder_status(self.draft),
                view=self.controls,
                allowed_mentions=discord.AllowedMentions.none(),
            )


class AddEmbedButtonModal(discord.ui.Modal):
    def __init__(self, controls: "EmbedBuilderControls"):
        super().__init__(title="Agregar botón al embed", timeout=600)
        self.controls = controls

        self.section_text = discord.ui.TextInput(
            label="Texto junto al botón",
            placeholder="### 📩 ¿Te interesa?\n\nAbre un ticket para recibir más información.",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=300,
        )
        self.button_label = discord.ui.TextInput(
            label="Texto del botón",
            placeholder="Click aquí",
            required=True,
            max_length=80,
        )
        self.button_url = discord.ui.TextInput(
            label="URL del botón",
            placeholder="Puedes reemplazar el enlace de tickets",
            default=DEFAULT_TICKET_BUTTON_URL,
            required=True,
            max_length=500,
        )
        self.button_emoji = discord.ui.TextInput(
            label="Emoji del botón (opcional)",
            placeholder="✅ o <:nombre:123456789012345678>",
            required=False,
            max_length=100,
        )
        for item in (self.section_text, self.button_label, self.button_url, self.button_emoji):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        if len(self.controls.draft.buttons) >= MAX_BUILDER_BUTTONS:
            await interaction.response.send_message(
                f"❌ Solo se permiten {MAX_BUILDER_BUTTONS} botones por publicación.",
                ephemeral=True,
            )
            return

        try:
            url = validate_web_url(str(self.button_url), "El enlace del botón")
        except ValueError as error:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return

        section_text = str(self.section_text).strip()
        label = str(self.button_label).strip()
        if not section_text or not label:
            await interaction.response.send_message(
                "❌ El texto de la sección y la etiqueta del botón no pueden estar vacíos.",
                ephemeral=True,
            )
            return

        self.controls.draft.buttons.append(
            EmbedButtonData(
                section_text=section_text,
                label=label,
                url=url or "",
                emoji=str(self.button_emoji).strip() or None,
            )
        )
        if draft_content_length(self.controls.draft) > 4000:
            used = draft_content_length(self.controls.draft)
            self.controls.draft.buttons.pop()
            await interaction.response.send_message(
                f"❌ Este botón elevaría el texto a {used}/4000 caracteres. Acorta el texto de la sección.",
                ephemeral=True,
            )
            return
        self.controls.persist_draft()
        self.controls.refresh()
        await interaction.response.edit_message(
            content=builder_status(self.controls.draft),
            view=self.controls,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class AddAnnouncementSectionModal(discord.ui.Modal):
    def __init__(self, controls: "EmbedBuilderControls"):
        super().__init__(title="Agregar sección separada", timeout=600)
        self.controls = controls
        self.section_content = discord.ui.TextInput(
            label="Contenido de la nueva sección",
            placeholder="## 🤝 TU DECIDES\nEscribe aquí el siguiente anuncio...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=2000,
        )
        self.add_item(self.section_content)

    async def on_submit(self, interaction: discord.Interaction):
        draft = self.controls.draft
        if len(draft.sections) >= MAX_ANNOUNCEMENT_SECTIONS:
            await interaction.response.send_message(
                f"❌ Solo se permiten {MAX_ANNOUNCEMENT_SECTIONS} secciones separadas.",
                ephemeral=True,
            )
            return

        content = str(self.section_content).strip()
        if not content:
            await interaction.response.send_message(
                "❌ La sección no puede estar vacía.",
                ephemeral=True,
            )
            return

        draft.sections.append(content)
        if draft_content_length(draft) > 4000:
            used = draft_content_length(draft)
            draft.sections.pop()
            await interaction.response.send_message(
                f"❌ Esta sección elevaría el texto a {used}/4000 caracteres. Acórtala e inténtalo de nuevo.",
                ephemeral=True,
            )
            return

        self.controls.persist_draft()
        self.controls.refresh()
        await interaction.response.edit_message(
            content=builder_status(draft),
            view=self.controls,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class RemoveLastEmbedButton(discord.ui.Button):
    def __init__(self, controls: "EmbedBuilderControls"):
        self.controls = controls
        super().__init__(
            label="Quitar último botón",
            emoji="↩️",
            style=discord.ButtonStyle.danger,
            row=1,
            disabled=not controls.draft.buttons,
        )

    async def callback(self, interaction: discord.Interaction):
        if self.controls.draft.buttons:
            self.controls.draft.buttons.pop()
        self.controls.persist_draft()
        self.controls.refresh()
        await interaction.response.edit_message(
            content=builder_status(self.controls.draft),
            view=self.controls,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class ToggleEveryoneButton(discord.ui.Button):
    def __init__(self, controls: "EmbedBuilderControls"):
        self.controls = controls
        super().__init__(row=1)
        self.refresh()

    def refresh(self):
        enabled = self.controls.draft.mention_everyone
        self.label = "@everyone: Sí" if enabled else "@everyone: No"
        self.emoji = "📣" if enabled else "🔕"
        self.style = discord.ButtonStyle.success if enabled else discord.ButtonStyle.secondary

    async def callback(self, interaction: discord.Interaction):
        self.controls.draft.mention_everyone = not self.controls.draft.mention_everyone
        if draft_content_length(self.controls.draft) > 4000:
            self.controls.draft.mention_everyone = False
            await interaction.response.send_message(
                "❌ No se puede activar @everyone porque el texto ya alcanzó el límite de 4000 caracteres.",
                ephemeral=True,
            )
            return
        self.controls.persist_draft()
        self.controls.refresh()
        await interaction.response.edit_message(
            content=builder_status(self.controls.draft),
            view=self.controls,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class ToggleTranslationButton(discord.ui.Button):
    def __init__(self, controls: "EmbedBuilderControls"):
        self.controls = controls
        super().__init__(row=1)
        self.refresh()

    def refresh(self):
        enabled = self.controls.draft.translation_enabled
        self.label = "Traductor: Activo" if enabled else "Traductor: Desactivado"
        self.emoji = "🌐" if enabled else "🔕"
        self.style = discord.ButtonStyle.success if enabled else discord.ButtonStyle.secondary

    async def callback(self, interaction: discord.Interaction):
        self.controls.draft.translation_enabled = not self.controls.draft.translation_enabled
        self.controls.persist_draft()
        self.controls.refresh()
        await interaction.response.edit_message(
            content=builder_status(self.controls.draft),
            view=self.controls,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class AddAnnouncementSectionButton(discord.ui.Button):
    def __init__(self, controls: "EmbedBuilderControls"):
        self.controls = controls
        super().__init__(
            label="Agregar sección",
            emoji="➕",
            style=discord.ButtonStyle.primary,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AddAnnouncementSectionModal(self.controls))


class RemoveLastAnnouncementSectionButton(discord.ui.Button):
    def __init__(self, controls: "EmbedBuilderControls"):
        self.controls = controls
        super().__init__(
            label="Quitar sección",
            emoji="↩️",
            style=discord.ButtonStyle.danger,
            row=1,
            disabled=not controls.draft.sections,
        )

    async def callback(self, interaction: discord.Interaction):
        if self.controls.draft.sections:
            self.controls.draft.sections.pop()
        self.controls.persist_draft()
        self.controls.refresh()
        await interaction.response.edit_message(
            content=builder_status(self.controls.draft),
            view=self.controls,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class EmbedBuilderControls(discord.ui.View):
    def __init__(
        self,
        owner_id: int,
        draft: EmbedDraft,
        translation_service: FreeGoogleTranslationService,
    ):
        super().__init__(timeout=900)
        self.owner_id = owner_id
        self.draft = draft
        self.translation_service = translation_service
        self.remove_last = RemoveLastEmbedButton(self)
        self.toggle_everyone = ToggleEveryoneButton(self)
        self.toggle_translation = ToggleTranslationButton(self)
        self.add_section = AddAnnouncementSectionButton(self)
        self.remove_section = RemoveLastAnnouncementSectionButton(self)
        self.add_item(self.remove_last)
        self.add_item(self.toggle_everyone)
        self.add_item(self.toggle_translation)
        self.add_item(self.add_section)
        self.add_item(self.remove_section)
        if self.draft.target_message is not None:
            self.publish.label = "Guardar cambios"
            self.publish.emoji = "💾"
        self.refresh()

    def persist_draft(self) -> bool:
        """Persist creation progress; message edits already have their own saved source."""
        if self.draft.target_message is not None:
            return True
        guild = getattr(self.draft.channel, "guild", None)
        if guild is None:
            return False
        try:
            self.translation_service.store.save_builder_draft(
                guild.id,
                self.owner_id,
                draft_to_data(self.draft),
            )
        except Exception:
            return False
        return True

    def delete_persisted_draft(self) -> bool:
        if self.draft.target_message is not None:
            return True
        guild = getattr(self.draft.channel, "guild", None)
        if guild is None:
            return False
        try:
            self.translation_service.store.delete_builder_draft(guild.id, self.owner_id)
        except Exception:
            return False
        return True

    def refresh(self):
        self.add_button.disabled = len(self.draft.buttons) >= MAX_BUILDER_BUTTONS
        self.remove_last.disabled = not self.draft.buttons
        self.toggle_everyone.refresh()
        self.toggle_translation.refresh()
        self.add_section.disabled = len(self.draft.sections) >= MAX_ANNOUNCEMENT_SECTIONS
        self.remove_section.disabled = not self.draft.sections

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        is_owner = interaction.user.id == self.owner_id
        is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        if not is_owner or not is_admin:
            await interaction.response.send_message(
                "❌ Este creador solo puede usarlo el administrador que lo inició.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

    @discord.ui.button(label="Vista previa", emoji="👁️", style=discord.ButtonStyle.secondary, row=0)
    async def preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_primary_content(self.draft):
            await interaction.response.send_message(
                "❌ Añade un título o contenido principal antes de generar la vista previa.",
                ephemeral=True,
            )
            return
        try:
            preview = build_components_v2(
                self.draft,
                self.translation_service if self.draft.translation_enabled else None,
                translation_disabled=True,
            )
        except (TypeError, ValueError) as error:
            await interaction.response.send_message(
                f"❌ No se pudo generar la vista previa. Revisa los emojis y enlaces: {error}",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            view=preview,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @discord.ui.button(label="Editar", emoji="✏️", style=discord.ButtonStyle.secondary, row=0)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            EmbedBasicsModal(self.draft, self.translation_service, self)
        )

    @discord.ui.button(label="Agregar botón", emoji="🔗", style=discord.ButtonStyle.primary, row=0)
    async def add_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddEmbedButtonModal(self))

    @discord.ui.button(label="Publicar", emoji="✅", style=discord.ButtonStyle.success, row=0)
    async def publish(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_primary_content(self.draft):
            await interaction.response.send_message(
                "❌ Añade un título o contenido principal antes de publicar.",
                ephemeral=True,
            )
            return
        try:
            publication = build_components_v2(
                self.draft,
                self.translation_service if self.draft.translation_enabled else None,
            )
        except (TypeError, ValueError) as error:
            await interaction.response.send_message(
                f"❌ No se pudo generar la publicación. Revisa los emojis y enlaces: {error}",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        editing = self.draft.target_message is not None
        try:
            if editing:
                message = await self.draft.target_message.edit(
                    view=publication,
                    allowed_mentions=publication_mentions(self.draft),
                )
            else:
                message = await self.draft.channel.send(
                    view=publication,
                    allowed_mentions=publication_mentions(self.draft),
                )
        except discord.HTTPException as error:
            action = "los cambios" if editing else "la publicación"
            await interaction.followup.send(
                f"❌ Discord rechazó {action}: {error}",
                ephemeral=True,
            )
            return

        try:
            self.translation_service.store.save_source(
                message.id,
                draft_to_data(self.draft),
            )
            if editing:
                self.translation_service.store.clear_translations(message.id)
        except Exception:
            storage_action = "actualizó" if editing else "publicó"
            await interaction.followup.send(
                f"⚠️ El mensaje se {storage_action}, pero no pude guardar sus datos de edición y traducción.",
                ephemeral=True,
            )

        self.stop()
        if not editing:
            self.delete_persisted_draft()
        result = "✅ Cambios guardados correctamente." if editing else "✅ Publicación enviada correctamente."
        await interaction.edit_original_response(content=result, view=None)
        await interaction.followup.send(
            f"[Ir a la publicación]({message.jump_url})",
            ephemeral=True,
        )

    @discord.ui.button(label="Cancelar", emoji="✖️", style=discord.ButtonStyle.danger, row=0)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        self.delete_persisted_draft()
        action = "Edición" if self.draft.target_message else "Creación"
        await interaction.response.edit_message(content=f"🗑️ {action} cancelada.", view=None)


class Embeds(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.embed_loader = bot.embed_loader
        translation_config = self.config.get("translation", {})
        self.translation_service = FreeGoogleTranslationService(
            database_path=translation_config.get(
                "database_path",
                "data/embed_translations.db",
            )
        )
        self.bot.add_view(PersistentTranslationView(self.translation_service))

    async def _find_guild_message(
        self,
        guild: discord.Guild,
        current_channel: Optional[discord.abc.Messageable],
        message_id: int,
        stored_channel_id: Optional[int],
    ) -> Optional[discord.Message]:
        """Find a message by ID without requiring the administrator to provide a channel."""
        candidates: list[discord.abc.Messageable] = []
        seen: set[int] = set()

        def add_candidate(channel):
            channel_id = getattr(channel, "id", None)
            if channel_id is None or channel_id in seen or not hasattr(channel, "fetch_message"):
                return
            seen.add(channel_id)
            candidates.append(channel)

        add_candidate(current_channel)
        if stored_channel_id:
            add_candidate(guild.get_channel(stored_channel_id) or guild.get_thread(stored_channel_id))
        for channel in guild.text_channels:
            add_candidate(channel)
        for thread in guild.threads:
            add_candidate(thread)

        for channel in candidates:
            try:
                return await channel.fetch_message(message_id)
            except (discord.NotFound, discord.Forbidden):
                continue
            except discord.HTTPException:
                continue
        return None

    @app_commands.command(
        name="crear-embed",
        description="Crea una publicación profesional con botones usando un asistente privado",
    )
    @app_commands.describe(nuevo="Sí para descartar el borrador guardado y comenzar desde cero")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def create_custom_embed(self, interaction: discord.Interaction, nuevo: bool = False):
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Solo los administradores pueden usar este comando.",
                ephemeral=True,
            )
            return

        if not all(
            hasattr(discord.ui, component)
            for component in ("LayoutView", "Container", "Section", "TextDisplay", "MediaGallery")
        ):
            await interaction.response.send_message(
                "❌ Este comando requiere discord.py 2.6.4 o superior. Actualiza las dependencias y reinicia el bot.",
                ephemeral=True,
            )
            return

        if interaction.channel is None:
            await interaction.response.send_message(
                "❌ No pude identificar el canal de publicación.",
                ephemeral=True,
            )
            return

        try:
            if nuevo:
                self.translation_service.store.delete_builder_draft(
                    interaction.guild.id,
                    interaction.user.id,
                )
                saved_data = None
            else:
                saved_data = self.translation_service.store.get_builder_draft(
                    interaction.guild.id,
                    interaction.user.id,
                )
        except Exception:
            saved_data = None

        if saved_data:
            saved_channel_id = saved_data.get("channel_id")
            saved_channel = (
                interaction.guild.get_channel(saved_channel_id)
                or interaction.guild.get_thread(saved_channel_id)
                if saved_channel_id
                else None
            )
            draft = draft_from_data(saved_data, saved_channel or interaction.channel)
        else:
            draft = EmbedDraft(
                channel=interaction.channel,
                color=self.config["bot"]["embed_color"],
            )
        await interaction.response.send_modal(
            EmbedBasicsModal(draft, self.translation_service)
        )

    @app_commands.command(
        name="editar-embed",
        description="Edita una publicación del bot usando únicamente el ID del mensaje",
    )
    @app_commands.describe(message_id="ID del mensaje publicado por este bot")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def edit_custom_embed(self, interaction: discord.Interaction, message_id: str):
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Solo los administradores pueden usar este comando.",
                ephemeral=True,
            )
            return

        cleaned_id = message_id.strip()
        if not cleaned_id.isdigit():
            await interaction.response.send_message(
                "❌ El ID del mensaje debe contener únicamente números.",
                ephemeral=True,
            )
            return

        numeric_id = int(cleaned_id)
        try:
            source_data = self.translation_service.store.get_source(numeric_id)
        except Exception:
            await interaction.response.send_message(
                "❌ No pude consultar los datos guardados. Revisa el archivo de la base de datos e inténtalo nuevamente.",
                ephemeral=True,
            )
            return
        if source_data is None:
            await interaction.response.send_message(
                "❌ No encontré datos editables para ese mensaje. Solo pueden editarse publicaciones creadas con `/crear-embed` que conserven sus datos originales.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        message = await self._find_guild_message(
            interaction.guild,
            interaction.channel,
            numeric_id,
            source_data.get("channel_id"),
        )
        if message is None:
            await interaction.followup.send(
                "❌ No encontré ese mensaje en ningún canal visible de este servidor.",
                ephemeral=True,
            )
            return

        if self.bot.user is None or message.author.id != self.bot.user.id:
            await interaction.followup.send(
                "❌ El mensaje indicado no fue publicado por este bot.",
                ephemeral=True,
            )
            return

        draft = draft_from_data(source_data, message.channel)
        draft.target_message = message
        controls = EmbedBuilderControls(
            interaction.user.id,
            draft,
            self.translation_service,
        )
        await interaction.edit_original_response(
            content=builder_status(draft),
            view=controls,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    
    @app_commands.command(name="auto-response", description="Send an embed based on an option")
    @app_commands.describe(option="Choose an embed option")
    async def auto_response(self, interaction: discord.Interaction, option: str):
        if not self.embed_loader:
            await interaction.response.send_message(
                "❌ Embed system is not available.",
                ephemeral=True
            )
            return
        
        embed = self.embed_loader.get_embed(option)
        
        if embed:
            await interaction.response.defer(ephemeral=True)
            try:
                await interaction.channel.send(embed=embed)
                await interaction.followup.send(
                    "✅ Embed sent successfully.",
                    ephemeral=True
                )
            except Exception as e:
                await interaction.followup.send(
                    f"❌ Could not send embed: {str(e)}",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "❌ Invalid option. Please choose a valid option.",
                ephemeral=True
            )
    
    @auto_response.autocomplete("option")
    async def auto_response_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ):
        if not self.embed_loader:
            return []
        
        display_names = {

            "Binance": "Payments - Binance",
            "PayPal": "Payments - PayPal",
            "Criptomonedas": "Payments - Criptomonedas (LTC/BTC/USDT)",
            "GiftCards": "Payments - Gift Cards (Binance/PSN)",
            "Yape/Plin": "Payments - Transferencia Perú",
            "TransferenciaChile": "Payments - Transferencia Chile",
            "TransferenciaMéxico": "Payments - Transferencia México",
            "DepositoMéxico": "Payments - Depósito México (OXXO)",
            
            "CheteoConsola": "Services - Cheteo Consola",
            "CheteoPC": "Services - Cheteo PC",
            
            "TyCPC": "Terms and Conditions - PC",
            "TyCConsola": "Terms and Conditions - Consola"
        }
        
        options = []
        for key, display_name in display_names.items():
            if self.embed_loader.get_embed(key) and current.lower() in display_name.lower():
                options.append(
                    app_commands.Choice(
                        name=display_name,
                        value=key
                    )
                )
        
        return options[:25]
    
    @app_commands.command(name="warzone-loaders", description="Send a Warzone loader embed")
    @app_commands.describe(option="Choose a Warzone loader option")
    async def warzone_loaders(self, interaction: discord.Interaction, option: str):
        if not self.embed_loader:
            await interaction.response.send_message(
                "❌ Embed system is not available.",
                ephemeral=True
            )
            return
        
        embed = self.embed_loader.get_embed(option)
        
        if embed:
            await interaction.response.defer(ephemeral=True)
            try:
                await interaction.channel.send(embed=embed)
                await interaction.followup.send(
                    "✅ Warzone embed sent successfully.",
                    ephemeral=True
                )
            except Exception as e:
                await interaction.followup.send(
                    f"❌ Could not send embed: {str(e)}",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "❌ Invalid option. Please choose a valid option.",
                ephemeral=True
            )
    
    @warzone_loaders.autocomplete("option")
    async def warzone_loaders_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ):
        if not self.embed_loader:
            return []
        
        warzone_keys = {
            "AFKTool": "AFK Tool",
            "FecurityChair": "Fecurity Chair",
            "SetupPreparation": "Setup Preparation",
            "UnlockAll": "Unlock All"
        }
        
        options = []
        for key, display in warzone_keys.items():
            if self.embed_loader.get_embed(key) and current.lower() in display.lower():
                options.append(app_commands.Choice(name=display, value=key))
        
        return options
    
    @app_commands.command(name="order-completed", description="Send an order completed embed")
    @app_commands.describe(type="Select recommendation type")
    @app_commands.choices(type=[
        app_commands.Choice(name="PC", value="pc"),
        app_commands.Choice(name="Consola", value="console")
    ])
    async def order_completed(
        self,
        interaction: discord.Interaction,
        type: app_commands.Choice[str]
    ):
        user = interaction.user
        avatar_url = user.avatar.url if user.avatar else self.config['default_avatar']
        
        embed = discord.Embed(
            color=self.config['bot']['embed_color']
        )
        embed.set_thumbnail(url=avatar_url)
        
        if type.value == "pc":
            embed.description = (
                "## 🎮 **__Pedido Completado - PC__**\n\n"
                "> ¡Gracias por confiar en nosotros! Tu pedido ha sido procesado exitosamente. "
                "A continuación, te compartimos algunas recomendaciones importantes para mantener tu cuenta segura.\n\n"
                "**🌟 Déjanos tu opinión**\n"
                "> Te invitamos a dejar una reseña en <#1159643310252638268> usando el comando </vouch:1403090399777784010>.\n\n"
                "**📋 Recomendaciones Importantes**\n"
                "> - **💰 Control de gastos:** Mantén tus gastos diarios por debajo de los 30 millones.\n"
                "> - **🚨 Evita problemas:** No molestes a otros jugadores y previene reportes innecesarios.\n"
                "> - **⛔ Sin inyecciones:** No utilices ningún menú de mods durante los próximos días.\n"
                "> - **💼 Actividad regular:** Realiza trabajos y misiones para que tu cuenta parezca legítima.\n\n"
                "**⚠️ Nota Importante**\n"
                "> Estas recomendaciones son fundamentales para mantener tu cuenta protegida y evitar sanciones."
            )
        elif type.value == "console":
            embed.description = (
                "## 🎮 **__Pedido Completado - Consola__**\n\n"
                "> ¡Tu pedido ha sido procesado exitosamente! Para garantizar la seguridad de tu cuenta, "
                "es crucial que sigas estas recomendaciones al pie de la letra.\n\n"
                "**📋 Recomendaciones Obligatorias**\n\n"
                "**💰 Gestión de dinero**\n"
                "> - No gastes más de **5 millones diarios**\n"
                "> - Esto evita que el sistema detecte movimientos sospechosos\n\n"
                "**🎯 Actividades en el juego**\n"
                "> - Realiza misiones, trabajos y golpes regularmente\n"
                "> - Mezcla el dinero con ganancias \"legítimas\" del juego\n\n"
                "**🔒 Modo de juego**\n"
                "> - Juega únicamente en sesiones privadas o por invitación\n"
                "> - Evita sesiones públicas para prevenir reportes\n\n"
                "**👥 Comportamiento en línea**\n"
                "> - No molestes a otros jugadores ni llames la atención innecesariamente\n"
                "> - Cualquier reporte puede activar revisiones de Rockstar\n\n"
                "**🚗 Ventas de vehículos**\n"
                "> - Vende solo **1 Deluxo por día**\n"
                "> - Espera entre 18-24 horas entre ventas para mantener el 100% del valor\n\n"
                "**⚠️ Recuerda**\n"
                "> La precaución es la clave para mantener tu cuenta segura. Sigue estas indicaciones y disfruta responsablemente.\n"
            )
        
        await interaction.response.defer(ephemeral=True)
        try:
            await interaction.channel.send(embed=embed)
            await interaction.followup.send(
                "✅ Embed sent successfully.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Could not send embed: {str(e)}",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Embeds(bot))

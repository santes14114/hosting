import os
import re
import io
import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

# ============================================================
# AYARLAR
# ============================================================
BOT_TOKEN = os.getenv('BOT_TOKEN')

GELEN_GIDEN_CHANNEL_ID = 1514903388746154085
KURUCU_DESTEK_CHANNEL_ID = 1523315702520610937
TICKET_CATEGORY_ID = 1523318288086466792
KURUCU_ID = 359199132906422273

# Ticket kanallarını görebilecek ek rol ID'leri (yetkili rolü varsa buraya ekleyin).
# Not: "Administrator" yetkisine sahip roller zaten tüm kanalları görebilir,
# bu listeye eklemenize gerek yok.
STAFF_ROLE_IDS = []

SERVER_NAME = "SantesHub"
EMBED_COLOR = discord.Color.from_str("#B00000")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONT_BLACK = os.path.join(ASSETS_DIR, "Poppins-Black.ttf")
FONT_BOLD = os.path.join(ASSETS_DIR, "Poppins-Bold.ttf")
FONT_SEMIBOLD = os.path.join(ASSETS_DIR, "Poppins-SemiBold.ttf")
FONT_MEDIUM = os.path.join(ASSETS_DIR, "Poppins-Medium.ttf")
WELCOME_BG = os.path.join(ASSETS_DIR, "welcome_bg.png")
GOODBYE_BG = os.path.join(ASSETS_DIR, "goodbye_bg.png")

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
log = logging.getLogger("santeshub")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ticket_owners: kalıcılık için channel topic'ine yazılır, bu sadece hızlı erişim cache'i
ticket_owners_cache = {}


# ============================================================
# YARDIMCI FONKSİYONLAR
# ============================================================
def sanitize_channel_name(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[^a-z0-9ğüşıöç\-]", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    return name[:20] or "kullanici"


async def user_has_open_ticket(guild: discord.Guild, user_id: int):
    category = guild.get_channel(TICKET_CATEGORY_ID)
    if category is None:
        return None
    for ch in category.channels:
        if isinstance(ch, discord.TextChannel) and ch.topic and str(user_id) in ch.topic:
            return ch
    return None


def can_manage_ticket(member: discord.Member, channel: discord.TextChannel) -> bool:
    if member.guild_permissions.manage_channels or member.guild_permissions.administrator:
        return True
    if channel.topic and str(member.id) in channel.topic:
        return True
    return False


def circular_avatar(avatar_bytes: bytes, size: int = 132):
    im = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((size, size))
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


async def build_member_card(member: discord.Member, bg_path: str, headline_sub: str) -> discord.File:
    """Karşılama / uğurlama banner'ını üyenin avatarı ve adıyla birlikte oluşturur."""
    canvas = Image.open(bg_path).convert("RGBA")
    W, H = canvas.size

    try:
        avatar_bytes = await member.display_avatar.replace(size=256, format="png").read()
        avatar = circular_avatar(avatar_bytes, size=132)
        canvas.alpha_composite(avatar, (W // 2 - 66, 150 - 66))
    except Exception as e:
        log.warning(f"Avatar eklenemedi: {e}")

    draw = ImageDraw.Draw(canvas)
    name_font = ImageFont.truetype(FONT_SEMIBOLD, 30)
    name = member.display_name
    if len(name) > 22:
        name = name[:21] + "…"
    bbox = draw.textbbox((0, 0), name, font=name_font)
    tw = bbox[2] - bbox[0]
    draw.text((W // 2 - tw / 2, 335), name, font=name_font, fill=(230, 230, 230, 255))

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    buf.seek(0)
    return discord.File(buf, filename="card.png")


# ============================================================
# TICKET SİSTEMİ
# ============================================================
class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Talep Aç", emoji="🎟️", style=discord.ButtonStyle.success, custom_id="santeshub:open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        category = guild.get_channel(TICKET_CATEGORY_ID)
        if category is None:
            await interaction.response.send_message("Ticket kategorisi bulunamadı, bir yetkiliye bildir.", ephemeral=True)
            return

        existing = await user_has_open_ticket(guild, interaction.user.id)
        if existing:
            await interaction.response.send_message(f"Zaten açık bir talebin var: {existing.mention}", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        for role_id in STAFF_ROLE_IDS:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        channel_name = f"talep-{sanitize_channel_name(interaction.user.name)}"
        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Destek talebi | Sahip: {interaction.user.id}",
                reason=f"{interaction.user} destek talebi açtı",
            )
        except discord.Forbidden:
            await interaction.response.send_message("Kanal oluşturma yetkim yok, bir yetkiliye bildir.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎫 Destek Talebi",
            description=(
                f"Merhaba {interaction.user.mention}! Talebin oluşturuldu.\n\n"
                "**Lütfen:**\n"
                "• Sorununu net şekilde yaz\n"
                "• Görsel/video ekleyebilirsin\n"
                "• Yetkili gelene kadar sabırlı ol\n"
                "• Sorun çözülünce aşağıdaki 🔒 butonuyla talebi kapat"
            ),
            color=EMBED_COLOR,
        )
        embed.set_footer(text=f"{SERVER_NAME} • Destek Sistemi")
        await channel.send(content=interaction.user.mention, embed=embed, view=TicketControlView())
        await interaction.response.send_message(f"Talebin oluşturuldu: {channel.mention}", ephemeral=True)


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Talebi Kapat", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="santeshub:close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        if not can_manage_ticket(interaction.user, channel):
            await interaction.response.send_message("Bu talebi kapatma yetkin yok.", ephemeral=True)
            return
        await interaction.response.send_message("Bu talep 5 saniye içinde kapatılacak...")
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"{interaction.user} tarafından kapatıldı")
        except discord.NotFound:
            pass


# ============================================================
# KURUCU İLE İLETİŞİM
# ============================================================
class ContactModal(discord.ui.Modal, title="Kurucu ile İletişim"):
    mesaj = discord.ui.TextInput(
        label="Mesajınız",
        style=discord.TextStyle.paragraph,
        placeholder="İletmek istediğin mesajı buraya yaz...",
        max_length=1000,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        founder = bot.get_user(KURUCU_ID) or await bot.fetch_user(KURUCU_ID)

        embed = discord.Embed(
            title="📩 Yeni Mesaj — Kurucu İletişim",
            description=str(self.mesaj.value),
            color=EMBED_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=f"{interaction.user} ({interaction.user.id})", icon_url=interaction.user.display_avatar.url)
        embed.add_field(name="Sunucu", value=interaction.guild.name if interaction.guild else "DM", inline=True)
        embed.set_footer(text=f"{SERVER_NAME} • Kurucu İletişim Sistemi")

        try:
            await founder.send(embed=embed)
        except discord.Forbidden:
            log.warning(f"{founder} DM kapalı olduğu için mesaj iletilemedi.")

        await interaction.response.send_message("Mesajın kurucumuza iletildi! ✅", ephemeral=True)


class ContactFounderView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Mesaj Gönder", emoji="✉️", style=discord.ButtonStyle.primary, custom_id="santeshub:contact_founder")
    async def contact(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ContactModal())


# ============================================================
# OTOMATİK CEVAPLAR
# ============================================================
AUTO_REPLIES = [
    (r"\b(sa|selam|selamun aleykum|selamünaleyküm|selamünaleyküm)\b",
     "Aleyküm selam! 👋 {mention} SantesHub'a hoş geldin, yardımcı olabileceğim bir şey var mı?"),
    (r"\bnaber\b",
     "İyidir, senden naber {mention}? 😄 Bir konuda yardım lazımsa <#{contact}> ya da destek kanalından ticket açabilirsin."),
    (r"\b(yardım|yardim)\b",
     "Yardıma mı ihtiyacın var {mention}? 🎫 Destek kanalındaki **Talep Aç** butonuyla bize ulaşabilirsin, ekibimiz en kısa sürede döner!"),
]
AUTO_REPLY_COOLDOWN = 30  # saniye
_last_reply_at = {}


def get_auto_reply(content: str):
    lowered = content.lower()
    for pattern, reply in AUTO_REPLIES:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            return reply
    return None


# ============================================================
# EVENTS
# ============================================================
@bot.event
async def on_ready():
    bot.add_view(TicketPanelView())
    bot.add_view(TicketControlView())
    bot.add_view(ContactFounderView())
    try:
        synced = await bot.tree.sync()
        log.info(f"{len(synced)} slash komut senkronize edildi.")
    except Exception as e:
        log.error(f"Senkronizasyon hatası: {e}")
    log.info(f"{bot.user} olarak giriş yapıldı.")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        return

    reply = get_auto_reply(message.content)
    if reply:
        now = datetime.now(timezone.utc).timestamp()
        last = _last_reply_at.get(message.author.id, 0)
        if now - last >= AUTO_REPLY_COOLDOWN:
            _last_reply_at[message.author.id] = now
            text = reply.format(mention=message.author.mention, contact=KURUCU_DESTEK_CHANNEL_ID)
            await message.channel.send(text)

    await bot.process_commands(message)


@bot.event
async def on_member_join(member: discord.Member):
    channel = member.guild.get_channel(GELEN_GIDEN_CHANNEL_ID)
    if channel is None:
        return
    try:
        file = await build_member_card(member, WELCOME_BG, "")
        embed = discord.Embed(color=EMBED_COLOR)
        embed.set_image(url="attachment://card.png")
        embed.set_footer(text=f"Sunucumuz artık {member.guild.member_count} kişi! 🚀")
        await channel.send(content=f"{member.mention} Hoşgeldin! 🎉", embed=embed, file=file)
    except Exception as e:
        log.error(f"Karşılama kartı gönderilemedi: {e}")
        await channel.send(f"{member.mention} SantesHub'a hoşgeldin! 🎉 Şu an {member.guild.member_count} kişiyiz. 🚀")


@bot.event
async def on_member_remove(member: discord.Member):
    channel = member.guild.get_channel(GELEN_GIDEN_CHANNEL_ID)
    if channel is None:
        return
    try:
        file = await build_member_card(member, GOODBYE_BG, "")
        embed = discord.Embed(color=EMBED_COLOR)
        embed.set_image(url="attachment://card.png")
        embed.set_footer(text=f"Şu an {member.guild.member_count} kişi kaldık.")
        await channel.send(content=f"**{member}** aramızdan ayrıldı. 👋", embed=embed, file=file)
    except Exception as e:
        log.error(f"Uğurlama kartı gönderilemedi: {e}")
        await channel.send(f"**{member}** aramızdan ayrıldı. 👋")


# ============================================================
# SLASH KOMUTLARI (kurulum)
# ============================================================
@bot.tree.command(name="talep-paneli", description="Bu kanala destek/ticket panelini gönderir.")
@app_commands.default_permissions(administrator=True)
async def talep_paneli(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎫 Destek Talebi",
        description=(
            "Sorunun mu var, yardıma mı ihtiyacın var?\n\n"
            "Aşağıdaki **Talep Aç** butonuna tıkla, sana özel bir kanal açalım. "
            "Sadece sen ve yetkililerimiz görebilir.\n\n"
            "**Lütfen:**\n"
            "• Sorununu net şekilde yaz\n"
            "• Görsel/video ekleyebilirsin\n"
            "• Yetkili gelene kadar sabırlı ol\n"
            "• Sorun çözülünce 🔒 butonuyla talebi kapat"
        ),
        color=EMBED_COLOR,
    )
    embed.set_footer(text=f"{SERVER_NAME} • Destek Sistemi")
    await interaction.channel.send(embed=embed, view=TicketPanelView())
    await interaction.response.send_message("Panel gönderildi.", ephemeral=True)


@bot.tree.command(name="iletisim-paneli", description="Kurucu ile iletişim panelini kurucu-destek kanalına gönderir.")
@app_commands.default_permissions(administrator=True)
async def iletisim_paneli(interaction: discord.Interaction):
    channel = interaction.guild.get_channel(KURUCU_DESTEK_CHANNEL_ID)
    if channel is None:
        await interaction.response.send_message("Kurucu-destek kanalı bulunamadı.", ephemeral=True)
        return

    embed = discord.Embed(
        title="✉️ Kurucu ile İletişim",
        description=(
            "Kurucumuza iletmek istediğin bir mesaj mı var?\n\n"
            "Aşağıdaki **Mesaj Gönder** butonuna tıkla, açılan formu doldur ve gönder. "
            "Mesajın direkt kurucumuza iletilecek."
        ),
        color=EMBED_COLOR,
    )
    embed.set_footer(text=f"{SERVER_NAME} • Kurucu İletişim Sistemi")
    await channel.send(embed=embed, view=ContactFounderView())
    await interaction.response.send_message(f"Panel {channel.mention} kanalına gönderildi.", ephemeral=True)


if __name__ == "__main__":
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN ortam değişkeni ayarlanmamış. Railway > Variables kısmına BOT_TOKEN ekle.")
    bot.run(BOT_TOKEN)

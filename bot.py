import os
import re
import io
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

# ============================================================
# AYARLAR
# ============================================================
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Kanal ID'leri
GELEN_GIDEN_CHANNEL_ID = 1514903388746154085
KURUCU_DESTEK_CHANNEL_ID = 1523315702520610937
TICKET_CATEGORY_ID = 1523318288086466792
TICKET_CHANNEL_ID = 1525786470714183870
LOG_CHANNEL_ID = 1523965225605402704  # Log kanalı ID'si

KURUCU_ID = 359199132906422273
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
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix=".", intents=intents)

# Webhook cache
webhook_cache = {}


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
# WEBHOOK YÖNETİMİ
# ============================================================
async def get_or_create_webhook(channel: discord.TextChannel) -> Optional[discord.Webhook]:
    """Log kanalı için webhook oluşturur veya var olanı getirir."""
    if channel.id in webhook_cache:
        try:
            webhook = await bot.fetch_webhook(webhook_cache[channel.id])
            if webhook:
                return webhook
        except:
            pass
    
    try:
        # Mevcut webhook'ları kontrol et
        webhooks = await channel.webhooks()
        for wh in webhooks:
            if wh.name == "SantesHub Log":
                webhook_cache[channel.id] = wh.id
                return wh
        
        # Yoksa yeni webhook oluştur
        webhook = await channel.create_webhook(name="SantesHub Log", reason="SantesHub log sistemi için oluşturuldu.")
        webhook_cache[channel.id] = webhook.id
        return webhook
    except Exception as e:
        log.error(f"Webhook oluşturulamadı: {e}")
        return None


async def send_log(embed: discord.Embed, channel_id: int = LOG_CHANNEL_ID):
    """Webhook üzerinden log mesajı gönderir."""
    channel = bot.get_channel(channel_id)
    if not channel:
        log.warning(f"Log kanalı bulunamadı: {channel_id}")
        return
    
    webhook = await get_or_create_webhook(channel)
    if webhook:
        try:
            await webhook.send(embed=embed, username="SantesHub Log", avatar_url=bot.user.display_avatar.url)
        except Exception as e:
            log.error(f"Webhook ile mesaj gönderilemedi: {e}")
            # Webhook çalışmazsa normal mesaj olarak gönder
            await channel.send(embed=embed)


# ============================================================
# LOG FONKSİYONLARI
# ============================================================
async def log_member_join(member: discord.Member):
    embed = discord.Embed(
        title="👤 Üye Katıldı",
        description=f"{member.mention} ({member}) sunucuya katıldı.",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Hesap Oluşturma", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"Toplam Üye: {member.guild.member_count}")
    await send_log(embed)


async def log_member_remove(member: discord.Member):
    embed = discord.Embed(
        title="👤 Üye Ayrıldı",
        description=f"{member} ({member.mention}) sunucudan ayrıldı.",
        color=discord.Color.red(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"Toplam Üye: {member.guild.member_count}")
    await send_log(embed)


async def log_member_update(before: discord.Member, after: discord.Member):
    changes = []
    
    # İsim değişikliği
    if before.display_name != after.display_name:
        changes.append(f"**İsim Değişikliği:** {before.display_name} → {after.display_name}")
    
    # Rol değişiklikleri
    before_roles = set(before.roles)
    after_roles = set(after.roles)
    
    added_roles = after_roles - before_roles
    removed_roles = before_roles - after_roles
    
    if added_roles:
        roles = [r.mention for r in added_roles if r != after.guild.default_role]
        if roles:
            changes.append(f"**Rol Eklendi:** {', '.join(roles)}")
    
    if removed_roles:
        roles = [r.mention for r in removed_roles if r != before.guild.default_role]
        if roles:
            changes.append(f"**Rol Kaldırıldı:** {', '.join(roles)}")
    
    # Nickname değişikliği
    if before.nick != after.nick:
        old = before.nick or "Yok"
        new = after.nick or "Yok"
        changes.append(f"**Takma İsim:** {old} → {new}")
    
    if not changes:
        return
    
    embed = discord.Embed(
        title="🔄 Üye Güncellendi",
        description=f"{after.mention} ({after}) bilgileri güncellendi.",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Değişiklikler", value="\n".join(changes), inline=False)
    embed.set_thumbnail(url=after.display_avatar.url)
    await send_log(embed)


async def log_message_delete(message: discord.Message):
    if message.author.bot:
        return
    
    embed = discord.Embed(
        title="🗑️ Mesaj Silindi",
        description=f"{message.author.mention} tarafından gönderilen mesaj silindi.",
        color=discord.Color.orange(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Kanal", value=message.channel.mention, inline=True)
    embed.add_field(name="Yazar", value=message.author, inline=True)
    
    if message.content:
        content = message.content[:1000]
        embed.add_field(name="İçerik", value=content, inline=False)
    
    if message.attachments:
        embed.add_field(name="Ek Dosyalar", value=f"{len(message.attachments)} dosya", inline=False)
    
    embed.set_footer(text=f"ID: {message.id}")
    await send_log(embed)


async def log_message_edit(before: discord.Message, after: discord.Message):
    if before.author.bot:
        return
    
    if before.content == after.content:
        return
    
    embed = discord.Embed(
        title="✏️ Mesaj Düzenlendi",
        description=f"{before.author.mention} mesajını düzenledi.",
        color=discord.Color.gold(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Kanal", value=before.channel.mention, inline=True)
    embed.add_field(name="Yazar", value=before.author, inline=True)
    embed.add_field(name="Önceki", value=before.content[:1000] or "Boş", inline=False)
    embed.add_field(name="Sonraki", value=after.content[:1000] or "Boş", inline=False)
    embed.set_footer(text=f"ID: {before.id}")
    await send_log(embed)


async def log_voice_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    # Ses kanalına girdi
    if before.channel is None and after.channel is not None:
        embed = discord.Embed(
            title="🔊 Ses Kanalına Girdi",
            description=f"{member.mention} **{after.channel.name}** kanalına girdi.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await send_log(embed)
    
    # Ses kanalından çıktı
    elif before.channel is not None and after.channel is None:
        embed = discord.Embed(
            title="🔇 Ses Kanalından Çıktı",
            description=f"{member.mention} **{before.channel.name}** kanalından çıktı.",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await send_log(embed)
    
    # Ses kanalı değiştirdi
    elif before.channel is not None and after.channel is not None and before.channel != after.channel:
        embed = discord.Embed(
            title="🔀 Ses Kanalı Değiştirdi",
            description=f"{member.mention} **{before.channel.name}** → **{after.channel.name}**",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await send_log(embed)


# ============================================================
# KURUCUYA OTOMATIK BILDIRIM
# ============================================================
async def send_ticket_notification_to_founder(user: discord.User, channel: discord.TextChannel):
    founder = bot.get_user(KURUCU_ID)
    if founder is None:
        try:
            founder = await bot.fetch_user(KURUCU_ID)
        except:
            log.error("Kurucu bulunamadı!")
            return
    
    embed = discord.Embed(
        title="🎫 Yeni Destek Talebi Açıldı!",
        description=f"{user.mention} ({user}) adlı kullanıcı yeni bir destek talebi açtı.",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Kullanıcı ID", value=user.id, inline=True)
    embed.add_field(name="Kanal", value=channel.mention, inline=True)
    embed.add_field(name="Kanal ID", value=channel.id, inline=True)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text=f"{SERVER_NAME} • Ticket Sistemi")
    
    try:
        await founder.send(embed=embed)
        log.info(f"Kurucuya ticket bildirimi gönderildi: {channel.name}")
    except discord.Forbidden:
        log.warning(f"Kurucunun DM'i kapalı, ticket bildirimi gönderilemedi.")


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
        
        # Ticket açıldı log'u
        log_embed = discord.Embed(
            title="🎫 Yeni Ticket Açıldı",
            description=f"{interaction.user.mention} yeni bir destek talebi açtı.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.add_field(name="Kanal", value=channel.mention, inline=True)
        log_embed.add_field(name="Kullanıcı", value=interaction.user, inline=True)
        log_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await send_log(log_embed)
        
        # Kurucuya özel bildirim
        await send_ticket_notification_to_founder(interaction.user, channel)
        
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
        
        # Ticket kapatıldı log'u
        log_embed = discord.Embed(
            title="🔒 Ticket Kapatıldı",
            description=f"{interaction.user.mention} tarafından kapatıldı.",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.add_field(name="Kanal", value=channel.mention, inline=True)
        await send_log(log_embed)
        
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
        founder = bot.get_user(KURUCU_ID)
        if founder is None:
            try:
                founder = await bot.fetch_user(KURUCU_ID)
            except:
                await interaction.response.send_message("Kurucu bulunamadı! ❌", ephemeral=True)
                return

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
            await interaction.response.send_message("Mesajın kurucumuza iletildi! ✅", ephemeral=True)
        except discord.Forbidden:
            log.warning(f"{founder} DM kapalı olduğu için mesaj iletilemedi.")
            await interaction.response.send_message("Kurucuya mesaj gönderilemedi, DM'leri kapalı olabilir. ❌", ephemeral=True)


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
AUTO_REPLY_COOLDOWN = 30
_last_reply_at = {}


def get_auto_reply(content: str):
    lowered = content.lower()
    for pattern, reply in AUTO_REPLIES:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            return reply
    return None


# ============================================================
# EVENT'LER
# ============================================================
@bot.event
async def on_ready():
    await bot.wait_until_ready()
    
    # Panel'leri otomatik gönder
    await send_ticket_panel_automatically()
    await send_contact_panel_automatically()
    
    bot.add_view(TicketPanelView())
    bot.add_view(TicketControlView())
    bot.add_view(ContactFounderView())
    
    log.info(f"{bot.user} olarak giriş yapıldı!")
    log.info(f"Bot {len(bot.guilds)} sunucuda aktif.")


async def send_ticket_panel_automatically():
    """Ticket panelini otomatik gönder."""
    for guild in bot.guilds:
        channel = guild.get_channel(TICKET_CHANNEL_ID)
        if channel is None:
            continue
        
        # Kanalda zaten panel var mı kontrol et
        try:
            async for message in channel.history(limit=50):
                if message.author == bot.user and message.embeds:
                    for embed in message.embeds:
                        if embed.title and "Destek Talebi" in embed.title:
                            return
        except:
            pass
        
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
        
        try:
            await channel.send(embed=embed, view=TicketPanelView())
            log.info(f"Ticket paneli {channel.name} kanalına gönderildi.")
        except Exception as e:
            log.error(f"Ticket paneli gönderilemedi: {e}")


async def send_contact_panel_automatically():
    """İletişim panelini otomatik gönder."""
    for guild in bot.guilds:
        channel = guild.get_channel(KURUCU_DESTEK_CHANNEL_ID)
        if channel is None:
            continue
        
        # Kanalda zaten panel var mı kontrol et
        try:
            async for message in channel.history(limit=50):
                if message.author == bot.user and message.embeds:
                    for embed in message.embeds:
                        if embed.title and "Kurucu ile İletişim" in embed.title:
                            return
        except:
            pass
        
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
        
        try:
            await channel.send(embed=embed, view=ContactFounderView())
            log.info(f"İletişim paneli {channel.name} kanalına gönderildi.")
        except Exception as e:
            log.error(f"İletişim paneli gönderilemedi: {e}")


# ============================================================
# ÜYE EVENT'LERİ
# ============================================================
@bot.event
async def on_member_join(member: discord.Member):
    # Karşılama mesajı
    channel = member.guild.get_channel(GELEN_GIDEN_CHANNEL_ID)
    if channel:
        try:
            file = await build_member_card(member, WELCOME_BG, "")
            embed = discord.Embed(color=EMBED_COLOR)
            embed.set_image(url="attachment://card.png")
            embed.set_footer(text=f"Sunucumuz artık {member.guild.member_count} kişi! 🚀")
            await channel.send(content=f"{member.mention} Hoşgeldin! 🎉", embed=embed, file=file)
        except Exception as e:
            log.error(f"Karşılama kartı gönderilemedi: {e}")
            await channel.send(f"{member.mention} SantesHub'a hoşgeldin! 🎉 Şu an {member.guild.member_count} kişiyiz. 🚀")
    
    # Log
    await log_member_join(member)


@bot.event
async def on_member_remove(member: discord.Member):
    # Uğurlama mesajı
    channel = member.guild.get_channel(GELEN_GIDEN_CHANNEL_ID)
    if channel:
        try:
            file = await build_member_card(member, GOODBYE_BG, "")
            embed = discord.Embed(color=EMBED_COLOR)
            embed.set_image(url="attachment://card.png")
            embed.set_footer(text=f"Şu an {member.guild.member_count} kişi kaldık.")
            await channel.send(content=f"**{member}** aramızdan ayrıldı. 👋", embed=embed, file=file)
        except Exception as e:
            log.error(f"Uğurlama kartı gönderilemedi: {e}")
            await channel.send(f"**{member}** aramızdan ayrıldı. 👋")
    
    # Log
    await log_member_remove(member)


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    await log_member_update(before, after)


# ============================================================
# MESAJ EVENT'LERİ
# ============================================================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        return

    # Otomatik cevaplar
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
async def on_message_delete(message: discord.Message):
    await log_message_delete(message)


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    await log_message_edit(before, after)


# ============================================================
# SES EVENT'LERİ
# ============================================================
@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    await log_voice_update(member, before, after)


# ============================================================
# KOMUTLAR (. ile başlayan)
# ============================================================
@bot.command(name="panel")
@commands.has_permissions(administrator=True)
async def panel_command(ctx):
    """Ticket panelini manuel gönderir."""
    await send_ticket_panel_automatically()
    await ctx.send("✅ Ticket paneli gönderildi!", delete_after=5)


@bot.command(name="iletisim")
@commands.has_permissions(administrator=True)
async def iletisim_command(ctx):
    """İletişim panelini manuel gönderir."""
    await send_contact_panel_automatically()
    await ctx.send("✅ İletişim paneli gönderildi!", delete_after=5)


@bot.command(name="temizle")
@commands.has_permissions(manage_messages=True)
async def temizle_command(ctx, miktar: int):
    """Belirtilen sayıda mesajı siler."""
    if miktar < 1 or miktar > 100:
        await ctx.send("❌ 1-100 arası bir sayı girin!", delete_after=5)
        return
    
    await ctx.channel.purge(limit=miktar + 1)
    msg = await ctx.send(f"✅ {miktar} mesaj silindi!")
    await asyncio.sleep(3)
    await msg.delete()


@bot.command(name="ping")
async def ping_command(ctx):
    """Bot gecikmesini gösterir."""
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! {latency}ms")


if __name__ == "__main__":
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN ortam değişkeni ayarlanmamış!")
    bot.run(BOT_TOKEN)

import os
import re
import io
import asyncio
import logging
import time
import aiohttp
import socket
import json
import base64
import struct
import random
import string
import subprocess
import platform
import ssl
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands, tasks
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# DNS ve WHOIS için try-except
try:
    import dns.resolver
    DNS_AVAILABLE = True
except ImportError:
    DNS_AVAILABLE = False
    print("⚠️ dnspython modülü yüklü değil! DNS sorguları çalışmayacak.")

try:
    import whois
    WHOIS_AVAILABLE = True
except ImportError:
    WHOIS_AVAILABLE = False
    print("⚠️ python-whois modülü yüklü değil! WHOIS sorguları çalışmayacak.")

# ============================================================
# AYARLAR
# ============================================================
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Kanal ID'leri
GELEN_GIDEN_CHANNEL_ID = 1514903388746154085
KURUCU_DESTEK_CHANNEL_ID = 1523315702520610937
TICKET_CATEGORY_ID = 1523318288086466792
TICKET_CHANNEL_ID = 1525786470714183870
LOG_CHANNEL_ID = 1523965225605402704
KEY_LOG_CHANNEL_ID = 1523965225605402704

KURUCU_ID = 359199132906422273
KURUCU_ADI = "Santess"

# Yetkili Rolleri
YETKILI_ROLLER = [
    1514893588125716633,
    1514893665393315871
]

SERVER_NAME = "SantesHub"
EMBED_COLOR = discord.Color.from_str("#B00000")

# Dosya yolları
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FAVICON_PATH = os.path.join(BASE_DIR, "favicon.png")

FONT_PATHS = {
    "black": os.path.join(BASE_DIR, "Poppins-Black.ttf"),
    "bold": os.path.join(BASE_DIR, "Poppins-Bold.ttf"),
    "semibold": os.path.join(BASE_DIR, "Poppins-SemiBold.ttf"),
    "medium": os.path.join(BASE_DIR, "Poppins-Medium.ttf"),
}

WELCOME_BG = os.path.join(BASE_DIR, "welcome_bg.png")
GOODBYE_BG = os.path.join(BASE_DIR, "goodbye_bg.png")

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
log = logging.getLogger("santeshub")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
intents.voice_states = True
intents.moderation = True

bot = commands.Bot(command_prefix=".", intents=intents)

webhook_cache = {}
bot_start_time = datetime.now(timezone.utc)

# Key veritabanı
key_database = {}
pending_keys = {}


# ============================================================
# YETKİLİ KONTROL FONKSİYONLARI
# ============================================================
def yetkili_mi(ctx):
    if ctx.author.guild_permissions.administrator:
        return True
    for role_id in YETKILI_ROLLER:
        role = ctx.guild.get_role(role_id)
        if role and role in ctx.author.roles:
            return True
    return False


def yetkili_kontrol(ctx):
    if not yetkili_mi(ctx):
        raise commands.MissingPermissions(["Yeterli yetkiniz yok!"])
    return True


# ============================================================
# YARDIMCI FONKSİYONLAR
# ============================================================
def get_font(font_type="semibold", size=30):
    font_path = FONT_PATHS.get(font_type, FONT_PATHS["semibold"])
    try:
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
        return ImageFont.load_default()
    except:
        return ImageFont.load_default()


def create_default_background(width=800, height=400, color=(30, 30, 40)):
    img = Image.new('RGBA', (width, height), color)
    draw = ImageDraw.Draw(img)
    for i in range(height):
        alpha = int(255 * (1 - i / height))
        draw.rectangle([(0, i), (width, i+1)], fill=(60, 60, 80, alpha // 2))
    draw.rectangle([(5, 5), (width-5, height-5)], outline=(100, 100, 120), width=2)
    return img


def get_background(bg_path, default_color=(30, 30, 40)):
    if os.path.exists(bg_path):
        try:
            return Image.open(bg_path).convert("RGBA")
        except:
            pass
    return create_default_background(color=default_color)


def get_uptime():
    now = datetime.now(timezone.utc)
    delta = now - bot_start_time
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if days > 0:
        return f"{days}g {hours}s {minutes}d"
    elif hours > 0:
        return f"{hours}s {minutes}d"
    else:
        return f"{minutes}d {seconds}s"


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
    try:
        im = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((size, size))
    except:
        im = Image.new('RGBA', (size, size), (100, 100, 150, 255))
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


async def build_member_card(member: discord.Member, bg_path: str, is_welcome: bool = True) -> discord.File:
    try:
        if is_welcome:
            canvas = get_background(bg_path, default_color=(20, 30, 50))
            text_color = (255, 255, 255, 255)
            title = "HOŞ GELDİN!"
            title_color = (0, 255, 100, 255)
        else:
            canvas = get_background(bg_path, default_color=(40, 20, 30))
            text_color = (255, 255, 255, 255)
            title = "GÜLE GÜLE!"
            title_color = (255, 100, 100, 255)
        
        W, H = canvas.size
        
        try:
            avatar_bytes = await member.display_avatar.replace(size=256, format="png").read()
            avatar = circular_avatar(avatar_bytes, size=130)
            canvas.alpha_composite(avatar, (W // 2 - 65, H // 2 - 100))
        except:
            pass
        
        draw = ImageDraw.Draw(canvas)
        
        try:
            title_font = get_font("bold", 40)
            bbox = draw.textbbox((0, 0), title, font=title_font)
            tw = bbox[2] - bbox[0]
            draw.text((W // 2 - tw // 2, 30), title, font=title_font, fill=title_color)
        except:
            pass
        
        try:
            name_font = get_font("semibold", 28)
            name = member.display_name
            if len(name) > 20:
                name = name[:19] + "…"
            bbox = draw.textbbox((0, 0), name, font=name_font)
            tw = bbox[2] - bbox[0]
            draw.text((W // 2 - tw // 2, H // 2 + 60), name, font=name_font, fill=text_color)
        except:
            pass
        
        try:
            info_font = get_font("medium", 16)
            info_text = f"ID: {member.id}"
            bbox = draw.textbbox((0, 0), info_text, font=info_font)
            tw = bbox[2] - bbox[0]
            draw.text((W // 2 - tw // 2, H - 40), info_text, font=info_font, fill=(200, 200, 200, 200))
        except:
            pass
        
        try:
            footer_font = get_font("medium", 14)
            footer_text = f"✦ {SERVER_NAME} ✦"
            bbox = draw.textbbox((0, 0), footer_text, font=footer_font)
            tw = bbox[2] - bbox[0]
            draw.text((W // 2 - tw // 2, H - 15), footer_text, font=footer_font, fill=(150, 150, 200, 180))
        except:
            pass
        
        buf = io.BytesIO()
        canvas.save(buf, format="PNG", quality=95)
        buf.seek(0)
        return discord.File(buf, filename="card.png")
    except Exception as e:
        log.error(f"Kart oluşturma hatası: {e}")
        return await create_simple_card(member)


async def create_simple_card(member: discord.Member) -> discord.File:
    img = Image.new('RGBA', (600, 300), (30, 30, 50))
    draw = ImageDraw.Draw(img)
    try:
        avatar_bytes = await member.display_avatar.replace(size=128, format="png").read()
        avatar = circular_avatar(avatar_bytes, size=80)
        img.alpha_composite(avatar, (260, 30))
    except:
        pass
    try:
        font = get_font("semibold", 24)
        name = member.display_name[:20]
        bbox = draw.textbbox((0, 0), name, font=font)
        tw = bbox[2] - bbox[0]
        draw.text((300 - tw // 2, 140), name, font=font, fill=(255, 255, 255))
    except:
        pass
    try:
        font = get_font("medium", 14)
        text = f"{SERVER_NAME}"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        draw.text((300 - tw // 2, 180), text, font=font, fill=(150, 150, 200))
    except:
        pass
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return discord.File(buf, filename="card.png")


# ============================================================
# KEY FONKSİYONLARI
# ============================================================
def generate_key(length: int = 16) -> str:
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choices(characters, k=length))


def format_key(key: str) -> str:
    if len(key) == 16:
        return f"{key[:4]}-{key[4:8]}-{key[8:12]}-{key[12:16]}"
    return key


def get_key_duration(key_type: str) -> timedelta:
    durations = {
        "1gun": timedelta(days=1),
        "1hafta": timedelta(days=7),
        "1ay": timedelta(days=30)
    }
    return durations.get(key_type, timedelta(days=1))


def get_key_price(key_type: str) -> int:
    prices = {
        "1gun": 150,
        "1hafta": 300,
        "1ay": 500
    }
    return prices.get(key_type, 150)


def get_key_name(key_type: str) -> str:
    names = {
        "1gun": "1 Günlük",
        "1hafta": "1 Haftalık",
        "1ay": "1 Aylık"
    }
    return names.get(key_type, "Bilinmiyor")


# ============================================================
# TOKEN ANALİZ FONKSİYONU
# ============================================================
def analyze_token(token: str) -> dict:
    result = {
        "valid_format": False,
        "token_type": "Bilinmiyor",
        "parts": [],
        "bot_id": None,
        "bot_id_snowflake": None,
        "created_at": None,
        "timestamp": None,
        "signature": None,
        "base64_encoded": False,
        "length": len(token),
        "starts_with": token[:10] if len(token) > 10 else token,
        "contains_dots": "." in token,
        "dot_count": token.count("."),
        "has_letters": any(c.isalpha() for c in token),
        "has_digits": any(c.isdigit() for c in token),
        "has_special": any(not c.isalnum() and c != "." for c in token),
    }
    
    if "." in token:
        parts = token.split(".")
        result["parts"] = parts
        result["dot_count"] = len(parts) - 1
        result["contains_dots"] = True
        
        if len(parts) >= 3:
            result["valid_format"] = True
            result["token_type"] = "Discord Bot Token (3 Parçalı)"
            
            try:
                first_part = parts[0]
                padding = 4 - (len(first_part) % 4)
                if padding != 4:
                    first_part += "=" * padding
                
                decoded = base64.b64decode(first_part)
                result["base64_encoded"] = True
                
                if len(decoded) >= 8:
                    bot_id = int.from_bytes(decoded[:8], 'big')
                    result["bot_id"] = bot_id
                    result["bot_id_snowflake"] = bot_id
                    
                    timestamp_ms = ((bot_id >> 22) + 1420070400000)
                    created_at = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
                    result["created_at"] = created_at
                    result["timestamp"] = timestamp_ms
            except Exception as e:
                result["decode_error"] = str(e)
            
            if len(parts) >= 2:
                result["signature"] = parts[1][:20] + "..." if len(parts[1]) > 20 else parts[1]
    
    elif len(token) == 24 and token.isalnum():
        result["valid_format"] = True
        result["token_type"] = "Discord User Token (24 karakter)"
    
    elif len(token) == 32 and token.isalnum():
        result["valid_format"] = True
        result["token_type"] = "OAuth2 Token (32 karakter)"
    
    elif "/" in token:
        result["valid_format"] = True
        result["token_type"] = "Webhook URL Token"
    
    return result


def analyze_snowflake(snowflake: int) -> dict:
    result = {
        "id": snowflake,
        "is_valid": False,
        "created_at": None,
        "timestamp": None,
        "internal_worker_id": None,
        "internal_process_id": None,
        "increment": None,
    }
    
    try:
        timestamp_ms = ((snowflake >> 22) + 1420070400000)
        created_at = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        
        result["created_at"] = created_at
        result["timestamp"] = timestamp_ms
        result["internal_worker_id"] = (snowflake >> 17) & 0x1F
        result["internal_process_id"] = (snowflake >> 12) & 0x1F
        result["increment"] = snowflake & 0xFFF
        result["is_valid"] = True
        
        if created_at.year < 2015:
            result["is_valid"] = False
            result["error"] = "ID çok eski (2015 öncesi)"
            
    except Exception as e:
        result["error"] = str(e)
    
    return result


# ============================================================
# WEBHOOK YÖNETİMİ
# ============================================================
async def get_or_create_webhook(channel: discord.TextChannel) -> Optional[discord.Webhook]:
    if channel.id in webhook_cache:
        try:
            webhook = await bot.fetch_webhook(webhook_cache[channel.id])
            if webhook:
                return webhook
        except:
            pass
    try:
        webhooks = await channel.webhooks()
        for wh in webhooks:
            if wh.name == "SantesHub Log":
                webhook_cache[channel.id] = wh.id
                return wh
        webhook = await channel.create_webhook(name="SantesHub Log")
        webhook_cache[channel.id] = webhook.id
        return webhook
    except:
        return None


async def send_log(embed: discord.Embed, channel_id: int = LOG_CHANNEL_ID):
    channel = bot.get_channel(channel_id)
    if not channel:
        return
    webhook = await get_or_create_webhook(channel)
    if webhook:
        try:
            await webhook.send(embed=embed, username="SantesHub Log", avatar_url=bot.user.display_avatar.url)
        except:
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


# ============================================================
# TICKET SİSTEMİ
# ============================================================
class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📩 Talep Aç", style=discord.ButtonStyle.success, custom_id="santeshub:open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        category = guild.get_channel(TICKET_CATEGORY_ID)
        if category is None:
            await interaction.response.send_message("❌ Ticket kategorisi bulunamadı!", ephemeral=True)
            return

        existing = await user_has_open_ticket(guild, interaction.user.id)
        if existing:
            await interaction.response.send_message(f"❌ Zaten açık talebin var: {existing.mention}", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }

        channel_name = f"talep-{sanitize_channel_name(interaction.user.name)}"
        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Destek talebi | Sahip: {interaction.user.id}",
            )
        except:
            await interaction.response.send_message("❌ Kanal oluşturulamadı!", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎫 Destek Talebi",
            description=(
                f"Merhaba {interaction.user.mention}! Talebin oluşturuldu.\n\n"
                "**📌 Lütfen:**\n"
                "• Sorununu net şekilde yaz\n"
                "• Görsel/video ekleyebilirsin\n"
                "• Yetkili gelene kadar sabırlı ol\n"
                "• Sorun çözülünce 🔒 butonuyla talebi kapat"
            ),
            color=EMBED_COLOR,
        )
        embed.set_footer(text=f"{SERVER_NAME} • Destek Sistemi")
        await channel.send(content=interaction.user.mention, embed=embed, view=TicketControlView())
        
        log_embed = discord.Embed(
            title="🎫 Yeni Ticket Açıldı",
            description=f"{interaction.user.mention} yeni bir destek talebi açtı.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.add_field(name="Kanal", value=channel.mention, inline=True)
        await send_log(log_embed)
        
        await interaction.response.send_message(f"✅ Talebin oluşturuldu: {channel.mention}", ephemeral=True)


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Talebi Kapat", style=discord.ButtonStyle.danger, custom_id="santeshub:close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        if not can_manage_ticket(interaction.user, channel):
            await interaction.response.send_message("❌ Bu talebi kapatma yetkin yok.", ephemeral=True)
            return
        
        await interaction.response.send_message("⏳ Talep 5 saniye içinde kapatılacak...")
        await asyncio.sleep(5)
        try:
            await channel.delete()
        except:
            pass


# ============================================================
# KURUCU İLETİŞİM
# ============================================================
class ContactModal(discord.ui.Modal, title="📩 Kurucu ile İletişim"):
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
                await interaction.response.send_message("❌ Kurucu bulunamadı!", ephemeral=True)
                return

        embed = discord.Embed(
            title="📩 Yeni Mesaj",
            description=str(self.mesaj.value),
            color=EMBED_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=f"{interaction.user}", icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f"{SERVER_NAME} • Kurucu İletişim")

        try:
            await founder.send(embed=embed)
            await interaction.response.send_message("✅ Mesajın kurucumuza iletildi!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ Kurucuya mesaj gönderilemedi, DM'leri kapalı olabilir.", ephemeral=True)


class ContactFounderView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✉️ Mesaj Gönder", style=discord.ButtonStyle.primary, custom_id="santeshub:contact_founder")
    async def contact(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ContactModal())


# ============================================================
# KEY PANELİ
# ============================================================
class KeySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="1 Günlük Key",
                description="150 TL - 1 gün geçerli",
                value="1gun",
                emoji="📅"
            ),
            discord.SelectOption(
                label="1 Haftalık Key",
                description="300 TL - 1 hafta geçerli",
                value="1hafta",
                emoji="📆"
            ),
            discord.SelectOption(
                label="1 Aylık Key",
                description="500 TL - 1 ay geçerli",
                value="1ay",
                emoji="📊"
            ),
        ]
        super().__init__(
            placeholder="📋 Key süresi seçiniz...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="santeshub:key_select"
        )

    async def callback(self, interaction: discord.Interaction):
        key_type = self.values[0]
        key_name = get_key_name(key_type)
        key_price = get_key_price(key_type)
        
        request_id = f"KEY-{random.randint(10000, 99999)}"
        temp_key = generate_key(16)
        
        pending_keys[request_id] = {
            "user_id": interaction.user.id,
            "user_name": str(interaction.user),
            "user_mention": interaction.user.mention,
            "key_type": key_type,
            "key_name": key_name,
            "price": key_price,
            "temp_key": temp_key,
            "created_at": datetime.now(timezone.utc),
            "status": "pending"
        }
        
        embed = discord.Embed(
            title="✅ Key Talebi Oluşturuldu!",
            description=(
                f"**Talep ID:** `{request_id}`\n"
                f"**Key Tipi:** {key_name}\n"
                f"**Fiyat:** {key_price} TL\n\n"
                f"📌 **Ödeme yapıldıktan sonra kurucu tarafından onaylanacaktır.**\n"
                f"⏳ Lütfen bekleyin, kurucu sizinle iletişime geçecek."
            ),
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"{SERVER_NAME} • Key Sistemi")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        founder = bot.get_user(KURUCU_ID)
        if founder:
            try:
                user = interaction.user
                
                founder_embed = discord.Embed(
                    title="🔑 Yeni Key Talebi!",
                    description=f"**{user.mention}** yeni bir key talebi oluşturdu.",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                founder_embed.set_thumbnail(url=user.display_avatar.url)
                founder_embed.add_field(name="📋 Talep ID", value=f"`{request_id}`", inline=True)
                founder_embed.add_field(name="👤 Kullanıcı", value=f"{user} ({user.mention})", inline=True)
                founder_embed.add_field(name="🆔 Kullanıcı ID", value=user.id, inline=True)
                founder_embed.add_field(name="📅 Key Tipi", value=key_name, inline=True)
                founder_embed.add_field(name="💰 Fiyat", value=f"{key_price} TL", inline=True)
                founder_embed.add_field(name="🔑 Geçici Key", value=f"`{format_key(temp_key)}`", inline=True)
                founder_embed.add_field(
                    name="📌 İşlem", 
                    value=(
                        "**Key'i onaylamak için:**\n"
                        f"`.keyonay {request_id}`\n\n"
                        "**Key'i reddetmek için:**\n"
                        f"`.keyred {request_id}`"
                    ),
                    inline=False
                )
                founder_embed.set_footer(text=f"{SERVER_NAME} • Key Yönetim Sistemi")
                
                await founder.send(embed=founder_embed)
                
                log_channel = bot.get_channel(KEY_LOG_CHANNEL_ID)
                if log_channel:
                    log_embed = discord.Embed(
                        title="🔑 Yeni Key Talebi",
                        description=f"{user.mention} yeni key talebi oluşturdu.",
                        color=discord.Color.blue(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    log_embed.add_field(name="Talep ID", value=request_id, inline=True)
                    log_embed.add_field(name="Key Tipi", value=key_name, inline=True)
                    log_embed.add_field(name="Fiyat", value=f"{key_price} TL", inline=True)
                    await log_channel.send(embed=log_embed)
                    
            except Exception as e:
                log.error(f"Kurucuya mesaj gönderilemedi: {e}")


class KeyPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(KeySelect())


# ============================================================
# SORGU PANELİ
# ============================================================
class SorguSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="🤖 Bot Token",
                description="Detaylı token analizi ve doğrulama",
                value="token_check",
                emoji="🤖"
            ),
            discord.SelectOption(
                label="🆔 Discord ID",
                description="Detaylı ID analizi ve kullanıcı bilgileri",
                value="discord_id",
                emoji="🆔"
            ),
            discord.SelectOption(
                label="🌐 Domain WHOIS",
                description="Domain kayıt bilgileri ve sahiplik",
                value="domain_whois",
                emoji="🌐"
            ),
            discord.SelectOption(
                label="🔍 Domain DNS",
                description="DNS kayıtları ve MX sorgulama",
                value="domain_dns",
                emoji="🔍"
            ),
            discord.SelectOption(
                label="🌍 IP Konum",
                description="IP adresi coğrafi konum ve ISP",
                value="ip_location",
                emoji="🌍"
            ),
            discord.SelectOption(
                label="🔒 SSL Kontrol",
                description="SSL sertifikası doğrulama",
                value="ssl_check",
                emoji="🔒"
            ),
            discord.SelectOption(
                label="🔓 Port Tarama",
                description="Açık port kontrolü",
                value="port_scan",
                emoji="🔓"
            ),
            discord.SelectOption(
                label="🔗 URL Güvenlik",
                description="URL güvenlik kontrolü",
                value="url_safety",
                emoji="🔗"
            ),
            discord.SelectOption(
                label="🏓 Ping Test",
                description="Sunucu ping ve gecikme testi",
                value="ping_test",
                emoji="🏓"
            ),
        ]
        super().__init__(
            placeholder="📋 Sorgu seçiniz...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="santeshub:sorgu_select"
        )

    async def callback(self, interaction: discord.Interaction):
        secim = self.values[0]
        
        if secim == "token_check":
            await interaction.response.send_modal(TokenCheckModal())
        elif secim == "discord_id":
            await interaction.response.send_modal(DiscordIDModal())
        elif secim == "domain_whois":
            await interaction.response.send_modal(DomainWhoisModal())
        elif secim == "domain_dns":
            await interaction.response.send_modal(DomainDNSModal())
        elif secim == "ip_location":
            await interaction.response.send_modal(IPLocationModal())
        elif secim == "ssl_check":
            await interaction.response.send_modal(SSLModal())
        elif secim == "port_scan":
            await interaction.response.send_modal(PortScanModal())
        elif secim == "url_safety":
            await interaction.response.send_modal(URLSafetyModal())
        elif secim == "ping_test":
            await interaction.response.send_modal(PingModal())


class SorguPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(SorguSelect())


# ============================================================
# TOKEN VE ID SORGU MODALLARI
# ============================================================
class TokenCheckModal(discord.ui.Modal, title="🤖 Detaylı Token Sorgu"):
    token = discord.ui.TextInput(
        label="Token",
        placeholder="Bot token, user token veya webhook URL girin...",
        required=True,
        style=discord.TextStyle.paragraph
    )

    async def on_submit(self, interaction: discord.Interaction):
        token_text = self.token.value.strip()
        analysis = analyze_token(token_text)
        
        embed = discord.Embed(
            title="🤖 Detaylı Token Analizi",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(name="📏 Uzunluk", value=f"{analysis['length']} karakter", inline=True)
        embed.add_field(name="📌 Format", value="✅ Geçerli" if analysis['valid_format'] else "❌ Geçersiz", inline=True)
        embed.add_field(name="🏷️ Token Türü", value=analysis['token_type'], inline=True)
        
        if analysis['contains_dots']:
            embed.add_field(name="🔹 Parça Sayısı", value=analysis['dot_count'] + 1, inline=True)
            if analysis['parts']:
                for i, part in enumerate(analysis['parts'][:3]):
                    embed.add_field(
                        name=f"📦 Parça {i+1}", 
                        value=f"`{part[:20]}{'...' if len(part) > 20 else ''}`", 
                        inline=True
                    )
        
        if analysis.get('bot_id'):
            embed.add_field(name="🤖 Bot ID", value=str(analysis['bot_id']), inline=True)
            
            snowflake_info = analyze_snowflake(analysis['bot_id'])
            if snowflake_info['is_valid']:
                embed.add_field(
                    name="📅 Hesap Oluşturma", 
                    value=f"<t:{int(snowflake_info['created_at'].timestamp())}:D>\n<t:{int(snowflake_info['created_at'].timestamp())}:R>",
                    inline=False
                )
                embed.add_field(name="🆔 Worker ID", value=str(snowflake_info['internal_worker_id']), inline=True)
                embed.add_field(name="🔄 Process ID", value=str(snowflake_info['internal_process_id']), inline=True)
                embed.add_field(name="📈 Increment", value=str(snowflake_info['increment']), inline=True)
        
        embed.add_field(name="🔐 Base64", value="Evet ✅" if analysis.get('base64_encoded') else "Hayır ❌", inline=True)
        
        if analysis.get('signature'):
            embed.add_field(name="✍️ İmza", value=f"`{analysis['signature']}`", inline=True)
        
        char_info = []
        if analysis['has_letters']:
            char_info.append("✅ Harf")
        if analysis['has_digits']:
            char_info.append("✅ Rakam")
        if analysis['has_special']:
            char_info.append("⚠️ Özel Karakter")
        embed.add_field(name="📝 Karakter Analizi", value="\n".join(char_info), inline=True)
        
        embed.add_field(
            name="🔍 Örnek", 
            value=f"`{analysis['starts_with']}...`" if len(token_text) > 20 else f"`{token_text}`",
            inline=False
        )
        
        if analysis.get('decode_error'):
            embed.add_field(name="⚠️ Hata", value=analysis['decode_error'], inline=False)
        
        embed.set_footer(text="✦ SANTESHUB - Detaylı Token Sorgu Toolu ✦")
        
        try:
            await interaction.user.send(embed=embed)
            await interaction.response.send_message("✅ Token analizi DM'ine gönderildi!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ DM'ine mesaj gönderemedim! DM'lerini aç.", ephemeral=True)


class DiscordIDModal(discord.ui.Modal, title="🆔 Detaylı ID Sorgu"):
    user_id = discord.ui.TextInput(
        label="Discord ID",
        placeholder="Kullanıcı ID'sini girin...",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(self.user_id.value)
            snowflake_info = analyze_snowflake(user_id)
            
            embed = discord.Embed(
                title="🆔 Detaylı ID Analizi",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            embed.add_field(name="🆔 ID", value=user_id, inline=True)
            embed.add_field(name="✅ Geçerli", value="Evet" if snowflake_info['is_valid'] else "Hayır", inline=True)
            
            if snowflake_info['is_valid']:
                embed.add_field(
                    name="📅 Oluşturulma",
                    value=f"<t:{int(snowflake_info['created_at'].timestamp())}:D>\n<t:{int(snowflake_info['created_at'].timestamp())}:R>",
                    inline=False
                )
                embed.add_field(name="🔄 Worker ID", value=snowflake_info['internal_worker_id'], inline=True)
                embed.add_field(name="🔄 Process ID", value=snowflake_info['internal_process_id'], inline=True)
                embed.add_field(name="📈 Increment", value=snowflake_info['increment'], inline=True)
                embed.add_field(name="⏰ Timestamp", value=f"<t:{int(snowflake_info['timestamp']/1000)}:T>", inline=True)
            else:
                if snowflake_info.get('error'):
                    embed.add_field(name="⚠️ Hata", value=snowflake_info['error'], inline=False)
            
            try:
                user = await bot.fetch_user(user_id)
                
                embed.add_field(name="👤 Kullanıcı", value=user.mention, inline=True)
                embed.add_field(name="📛 Ad", value=f"{user.name}#{user.discriminator}" if user.discriminator != "0" else user.name, inline=True)
                embed.add_field(name="🤖 Bot", value="Evet ✅" if user.bot else "Hayır ❌", inline=True)
                embed.add_field(name="🖼️ Avatar", value=f"[Link]({user.display_avatar.url})", inline=True)
                embed.set_thumbnail(url=user.display_avatar.url)
                
                if user.banner:
                    embed.add_field(name="🎨 Banner", value=f"[Link]({user.banner.url})", inline=True)
                
            except discord.NotFound:
                embed.add_field(name="⚠️ Bilgi", value="Bu ID'ye sahip kullanıcı bulunamadı (API)", inline=False)
            except Exception as e:
                embed.add_field(name="⚠️ API Hatası", value=str(e)[:100], inline=False)
            
            if snowflake_info['is_valid']:
                created = snowflake_info['created_at']
                now = datetime.now(timezone.utc)
                age = (now - created).days
                
                if age < 1:
                    id_type = "Yeni oluşturulmuş hesap"
                elif age < 30:
                    id_type = "Yeni hesap (1 ay)"
                elif age < 365:
                    id_type = "Normal hesap (1 yıl)"
                elif age < 1095:
                    id_type = "Eski hesap (1-3 yıl)"
                else:
                    id_type = "Çok eski hesap (3+ yıl)"
                
                embed.add_field(name="📊 Hesap Yaşı", value=f"{age} gün ({id_type})", inline=True)
            
            embed.set_footer(text="✦ SANTESHUB - Detaylı ID Sorgu Toolu ✦")
            
            try:
                await interaction.user.send(embed=embed)
                await interaction.response.send_message("✅ ID analizi DM'ine gönderildi!", ephemeral=True)
            except:
                await interaction.response.send_message("❌ DM'ine mesaj gönderemedim! DM'lerini aç.", ephemeral=True)
                
        except ValueError:
            await interaction.response.send_message("❌ Geçersiz ID formatı! Sadece sayı gir.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Hata: {e}", ephemeral=True)


# ============================================================
# DOMAIN, IP, SSL, PORT, URL, PING MODALLARI
# ============================================================
class DomainWhoisModal(discord.ui.Modal, title="🌐 Domain WHOIS Sorgu"):
    domain = discord.ui.TextInput(
        label="Domain Adı",
        placeholder="ornek.com veya ornek.com.tr",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        domain = self.domain.value.strip().lower()
        
        embed = discord.Embed(
            title="🌐 Domain WHOIS Sorgu Sonucu",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Domain", value=domain, inline=True)
        
        if WHOIS_AVAILABLE:
            try:
                w = whois.whois(domain)
                
                if w.domain_name:
                    embed.add_field(name="✅ Durum", value="Domain kayıtlı", inline=True)
                    embed.add_field(name="👤 Kayıt Sahibi", value=str(w.name or "Bilinmiyor"), inline=True)
                    embed.add_field(name="📧 Email", value=str(w.emails or "Bilinmiyor"), inline=True)
                    embed.add_field(name="📅 Kayıt Tarihi", value=str(w.creation_date or "Bilinmiyor"), inline=True)
                    embed.add_field(name="⏰ Bitiş Tarihi", value=str(w.expiration_date or "Bilinmiyor"), inline=True)
                    embed.add_field(name="🔄 Son Güncelleme", value=str(w.updated_date or "Bilinmiyor"), inline=True)
                    embed.add_field(name="🌐 Nameserver", value=str(w.name_servers or "Bilinmiyor"), inline=True)
                else:
                    embed.add_field(name="❌ Durum", value="Domain kayıtlı değil veya bulunamadı", inline=True)
                    
            except Exception as e:
                embed.add_field(name="❌ Hata", value=f"Domain sorgulanamadı: {str(e)[:100]}", inline=True)
        else:
            embed.add_field(name="⚠️ Uyarı", value="WHOIS modülü yüklü değil!", inline=True)
        
        embed.set_footer(text="✦ SANTESHUB - Ücretsiz Sorgu Toolu ✦")
        
        try:
            await interaction.user.send(embed=embed)
            await interaction.response.send_message("✅ Sorgu sonucu DM'ine gönderildi!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ DM'ine mesaj gönderemedim! DM'lerini aç.", ephemeral=True)


class DomainDNSModal(discord.ui.Modal, title="🔍 Domain DNS Sorgu"):
    domain = discord.ui.TextInput(
        label="Domain Adı",
        placeholder="ornek.com",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        domain = self.domain.value.strip().lower()
        
        embed = discord.Embed(
            title="🔍 Domain DNS Sorgu Sonucu",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Domain", value=domain, inline=True)
        
        if DNS_AVAILABLE:
            try:
                try:
                    answers = dns.resolver.resolve(domain, 'A')
                    ip_list = [str(r) for r in answers]
                    embed.add_field(name="🌐 A Kaydı (IPv4)", value="\n".join(ip_list[:5]), inline=True)
                except:
                    embed.add_field(name="🌐 A Kaydı", value="Bulunamadı", inline=True)
                
                try:
                    answers = dns.resolver.resolve(domain, 'MX')
                    mx_list = [f"{r.exchange} ({r.preference})" for r in answers]
                    embed.add_field(name="📧 MX Kaydı", value="\n".join(mx_list[:3]), inline=True)
                except:
                    embed.add_field(name="📧 MX Kaydı", value="Bulunamadı", inline=True)
                
                try:
                    answers = dns.resolver.resolve(domain, 'NS')
                    ns_list = [str(r) for r in answers]
                    embed.add_field(name="🔄 NS Kaydı", value="\n".join(ns_list[:3]), inline=True)
                except:
                    embed.add_field(name="🔄 NS Kaydı", value="Bulunamadı", inline=True)
                
                try:
                    answers = dns.resolver.resolve(domain, 'TXT')
                    txt_list = [str(r)[:50] + "..." for r in answers[:2]]
                    embed.add_field(name="📝 TXT Kaydı", value="\n".join(txt_list) if txt_list else "Bulunamadı", inline=True)
                except:
                    pass
                    
            except Exception as e:
                embed.add_field(name="❌ Hata", value=f"DNS sorgulanamadı: {str(e)[:100]}", inline=True)
        else:
            embed.add_field(name="⚠️ Uyarı", value="DNS modülü yüklü değil!", inline=True)
        
        embed.set_footer(text="✦ SANTESHUB - Ücretsiz Sorgu Toolu ✦")
        
        try:
            await interaction.user.send(embed=embed)
            await interaction.response.send_message("✅ Sorgu sonucu DM'ine gönderildi!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ DM'ine mesaj gönderemedim! DM'lerini aç.", ephemeral=True)


class IPLocationModal(discord.ui.Modal, title="🌍 IP Konum Sorgu"):
    ip = discord.ui.TextInput(
        label="IP Adresi",
        placeholder="8.8.8.8",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        ip = self.ip.value.strip()
        
        embed = discord.Embed(
            title="🌍 IP Konum Sorgu Sonucu",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="IP Adresi", value=ip, inline=True)
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://ip-api.com/json/{ip}") as resp:
                    data = await resp.json()
                    
                    if data.get('status') == 'success':
                        embed.add_field(name="📍 Ülke", value=data.get('country', 'Bilinmiyor'), inline=True)
                        embed.add_field(name="🏙️ Şehir", value=data.get('city', 'Bilinmiyor'), inline=True)
                        embed.add_field(name="📌 Bölge", value=data.get('regionName', 'Bilinmiyor'), inline=True)
                        embed.add_field(name="📮 Posta Kodu", value=data.get('zip', 'Bilinmiyor'), inline=True)
                        embed.add_field(name="🌐 ISP", value=data.get('isp', 'Bilinmiyor'), inline=True)
                        embed.add_field(name="📡 Organizasyon", value=data.get('org', 'Bilinmiyor'), inline=True)
                        embed.add_field(name="📱 Zaman Dilimi", value=data.get('timezone', 'Bilinmiyor'), inline=True)
                        embed.add_field(name="🗺️ Koordinatlar", value=f"{data.get('lat', '?')}, {data.get('lon', '?')}", inline=True)
                    else:
                        embed.add_field(name="❌ Durum", value="IP bulunamadı veya geçersiz", inline=True)
                        
        except Exception as e:
            embed.add_field(name="❌ Hata", value=f"IP sorgulanamadı: {str(e)[:100]}", inline=True)
        
        embed.set_footer(text="✦ SANTESHUB - Ücretsiz Sorgu Toolu ✦")
        
        try:
            await interaction.user.send(embed=embed)
            await interaction.response.send_message("✅ Sorgu sonucu DM'ine gönderildi!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ DM'ine mesaj gönderemedim! DM'lerini aç.", ephemeral=True)


class SSLModal(discord.ui.Modal, title="🔒 SSL Kontrol"):
    domain = discord.ui.TextInput(
        label="Domain Adı",
        placeholder="ornek.com",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        domain = self.domain.value.strip().lower()
        
        embed = discord.Embed(
            title="🔒 SSL Sertifika Kontrolü",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Domain", value=domain, inline=True)
        
        try:
            context = ssl.create_default_context()
            with socket.create_connection((domain, 443), timeout=5) as sock:
                with context.wrap_socket(sock, server_hostname=domain) as ssock:
                    cert = ssock.getpeercert()
                    
                    embed.add_field(name="✅ Durum", value="SSL sertifikası aktif", inline=True)
                    embed.add_field(name="🏷️ Yayınlayan", value=cert.get('issuer', {}).get('organizationName', ['Bilinmiyor'])[0], inline=True)
                    embed.add_field(name="🔑 Konu", value=cert.get('subject', {}).get('commonName', ['Bilinmiyor'])[0], inline=True)
                    
                    not_before = datetime.strptime(cert['notBefore'], '%b %d %H:%M:%S %Y %Z')
                    not_after = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
                    
                    embed.add_field(name="📅 Başlangıç", value=f"<t:{int(not_before.timestamp())}:D>", inline=True)
                    embed.add_field(name="📅 Bitiş", value=f"<t:{int(not_after.timestamp())}:D>", inline=True)
                    
                    remaining = (not_after - datetime.now()).days
                    if remaining > 30:
                        embed.add_field(name="✅ Geçerlilik", value=f"{remaining} gün kaldı", inline=True)
                    elif remaining > 0:
                        embed.add_field(name="⚠️ Geçerlilik", value=f"{remaining} gün kaldı (Yakında bitiyor!)", inline=True)
                    else:
                        embed.add_field(name="❌ Geçerlilik", value="Sertifika süresi dolmuş!", inline=True)
                        
        except socket.timeout:
            embed.add_field(name="❌ Hata", value="Bağlantı zaman aşımı (443 portu kapalı olabilir)", inline=True)
        except ConnectionRefusedError:
            embed.add_field(name="❌ Hata", value="Bağlantı reddedildi (HTTPS aktif değil)", inline=True)
        except Exception as e:
            embed.add_field(name="❌ Hata", value=f"SSL kontrol edilemedi: {str(e)[:100]}", inline=True)
        
        embed.set_footer(text="✦ SANTESHUB - Ücretsiz Sorgu Toolu ✦")
        
        try:
            await interaction.user.send(embed=embed)
            await interaction.response.send_message("✅ SSL bilgileri DM'ine gönderildi!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ DM'ine mesaj gönderemedim! DM'lerini aç.", ephemeral=True)


class PortScanModal(discord.ui.Modal, title="🔓 Port Tarama"):
    ip = discord.ui.TextInput(
        label="IP veya Domain",
        placeholder="8.8.8.8 veya ornek.com",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        target = self.ip.value.strip()
        
        embed = discord.Embed(
            title="🔓 Port Tarama Sonucu",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Hedef", value=target, inline=True)
        
        common_ports = {
            21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP",
            53: "DNS", 80: "HTTP", 110: "POP3", 143: "IMAP",
            443: "HTTPS", 3306: "MySQL", 3389: "RDP",
            5432: "PostgreSQL", 6379: "Redis", 27017: "MongoDB"
        }
        
        open_ports = []
        try:
            ip = socket.gethostbyname(target)
            
            for port, service in common_ports.items():
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2)
                    result = sock.connect_ex((ip, port))
                    sock.close()
                    
                    if result == 0:
                        open_ports.append(f"**{port}** ({service}) ✅")
                except:
                    pass
            
            if open_ports:
                embed.add_field(name="✅ Açık Portlar", value="\n".join(open_ports), inline=True)
            else:
                embed.add_field(name="ℹ️ Bilgi", value="Yaygın portlarda açık bulunamadı", inline=True)
                
            embed.add_field(name="🔄 Çözümlenen IP", value=ip, inline=True)
            
        except Exception as e:
            embed.add_field(name="❌ Hata", value=f"Tarama yapılamadı: {str(e)[:100]}", inline=True)
        
        embed.set_footer(text="✦ SANTESHUB - Ücretsiz Sorgu Toolu ✦")
        
        try:
            await interaction.user.send(embed=embed)
            await interaction.response.send_message("✅ Port tarama sonucu DM'ine gönderildi!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ DM'ine mesaj gönderemedim! DM'lerini aç.", ephemeral=True)


class URLSafetyModal(discord.ui.Modal, title="🔗 URL Güvenlik Kontrol"):
    url = discord.ui.TextInput(
        label="URL",
        placeholder="https://ornek.com",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        url_text = self.url.value.strip()
        
        if not url_text.startswith(("http://", "https://")):
            url_text = "https://" + url_text
        
        embed = discord.Embed(
            title="🔗 URL Güvenlik Kontrolü",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="URL", value=url_text, inline=False)
        
        try:
            parsed = urlparse(url_text)
            embed.add_field(name="🌐 Domain", value=parsed.netloc, inline=True)
            embed.add_field(name="🔒 Protocol", value=parsed.scheme.upper(), inline=True)
            
            try:
                context = ssl.create_default_context()
                with socket.create_connection((parsed.netloc, 443), timeout=3) as sock:
                    with context.wrap_socket(sock, server_hostname=parsed.netloc) as ssock:
                        embed.add_field(name="🔒 SSL", value="Aktif ✅", inline=True)
            except:
                embed.add_field(name="🔒 SSL", value="Yok veya HTTPS değil ⚠️", inline=True)
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url_text, timeout=5, allow_redirects=True) as resp:
                        status = resp.status
                        if 200 <= status < 300:
                            embed.add_field(name="📡 HTTP Durum", value=f"{status} ✅ (Başarılı)", inline=True)
                        elif 300 <= status < 400:
                            embed.add_field(name="📡 HTTP Durum", value=f"{status} 🔄 (Yönlendirme)", inline=True)
                        elif 400 <= status < 500:
                            embed.add_field(name="📡 HTTP Durum", value=f"{status} ❌ (Hata)", inline=True)
                        else:
                            embed.add_field(name="📡 HTTP Durum", value=f"{status} ⚠️ (Sunucu Hatası)", inline=True)
            except:
                embed.add_field(name="📡 HTTP Durum", value="Bağlantı kurulamadı ⚠️", inline=True)
            
            embed.add_field(name="✅ Güvenlik Durumu", value="URL erişilebilir", inline=False)
            
        except Exception as e:
            embed.add_field(name="❌ Hata", value=f"URL kontrol edilemedi: {str(e)[:100]}", inline=True)
        
        embed.set_footer(text="✦ SANTESHUB - Ücretsiz Sorgu Toolu ✦")
        
        try:
            await interaction.user.send(embed=embed)
            await interaction.response.send_message("✅ URL güvenlik bilgileri DM'ine gönderildi!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ DM'ine mesaj gönderemedim! DM'lerini aç.", ephemeral=True)


class PingModal(discord.ui.Modal, title="🏓 Ping Test"):
    hedef = discord.ui.TextInput(
        label="Hedef IP veya Domain",
        placeholder="8.8.8.8 veya google.com",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        hedef = self.hedef.value.strip()
        
        embed = discord.Embed(
            title="🏓 Ping Test Sonucu",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Hedef", value=hedef, inline=True)
        
        try:
            param = '-n' if platform.system().lower() == 'windows' else '-c'
            command = ['ping', param, '4', hedef]
            
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                embed.add_field(name="✅ Durum", value="Erişilebilir", inline=True)
                
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'time=' in line or 'time<' in line:
                        if 'time=' in line:
                            time_ms = line.split('time=')[1].split(' ')[0]
                            embed.add_field(name="⏱️ Gecikme", value=f"{time_ms} ms", inline=True)
                            break
                        elif 'time<' in line:
                            time_ms = line.split('time<')[1].split('ms')[0]
                            embed.add_field(name="⏱️ Gecikme", value=f"{time_ms} ms", inline=True)
                            break
                else:
                    embed.add_field(name="⏱️ Gecikme", value="Bağlantı başarılı", inline=True)
            else:
                embed.add_field(name="❌ Durum", value="Erişilemiyor veya zaman aşımı", inline=True)
                
        except subprocess.TimeoutExpired:
            embed.add_field(name="❌ Durum", value="Zaman aşımı (10 saniye)", inline=True)
        except Exception as e:
            embed.add_field(name="❌ Hata", value=f"Ping yapılamadı: {str(e)[:100]}", inline=True)
        
        embed.set_footer(text="✦ SANTESHUB - Ücretsiz Sorgu Toolu ✦")
        
        try:
            await interaction.user.send(embed=embed)
            await interaction.response.send_message("✅ Ping test sonucu DM'ine gönderildi!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ DM'ine mesaj gönderemedim! DM'lerini aç.", ephemeral=True)


# ============================================================
# DUYURU SİSTEMİ
# ============================================================
class DuyuruModal(discord.ui.Modal, title="📢 Duyuru Oluştur"):
    mesaj = discord.ui.TextInput(
        label="Duyuru Mesajı",
        style=discord.TextStyle.paragraph,
        placeholder="Duyuru metnini buraya yaz...",
        max_length=4000,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        channel = interaction.channel
        
        try:
            webhooks = await channel.webhooks()
            webhook = None
            
            for wh in webhooks:
                if wh.name == "SantesHub Duyuru":
                    webhook = wh
                    break
            
            if webhook is None:
                webhook = await channel.create_webhook(name="SantesHub Duyuru")
            
            await webhook.send(
                content=f"# {self.mesaj.value}",
                username="SantesHub Duyuru",
                avatar_url=bot.user.display_avatar.url
            )
            
            embed = discord.Embed(
                title="✅ Duyuru Gönderildi!",
                description=f"Duyuru başarıyla {channel.mention} kanalına webhook ile gönderildi.",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="📢 Mesaj", value=f"```\n{self.mesaj.value[:500]}\n```", inline=False)
            embed.add_field(name="👤 Gönderen", value=interaction.user.mention, inline=True)
            embed.add_field(name="🪝 Webhook", value="SantesHub Duyuru", inline=True)
            embed.set_footer(text=f"{SERVER_NAME} • Duyuru Sistemi")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            log_embed = discord.Embed(
                title="📢 Duyuru Gönderildi",
                description=f"{interaction.user} tarafından {channel.mention} kanalına duyuru gönderildi.",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            log_embed.add_field(name="Mesaj", value=self.mesaj.value[:1000], inline=False)
            await send_log(log_embed)
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ Webhook oluşturma veya mesaj gönderme iznim yok!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Duyuru gönderilemedi: {e}", ephemeral=True)


class DuyuruButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
    
    @discord.ui.button(label="📢 Duyuru Oluştur", style=discord.ButtonStyle.primary, custom_id="santeshub:duyuru_olustur")
    async def duyuru_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DuyuruModal())


# ============================================================
# BOT DURUMU
# ============================================================
@tasks.loop(minutes=1)
async def update_presence():
    await bot.wait_until_ready()
    guild = bot.guilds[0] if bot.guilds else None
    
    if guild:
        member_count = guild.member_count
        uptime = get_uptime()
        
        activity = discord.Activity(
            type=discord.ActivityType.streaming,
            name=f"📡 SantesHub • 👥 {member_count} Üye • ⏱️ {uptime}",
            url="https://www.twitch.tv/santeshub"
        )
        
        await bot.change_presence(
            activity=activity,
            status=discord.Status.online
        )


# ============================================================
# PANEL OTOMATİK GÖNDERİM
# ============================================================
async def send_ticket_panel_automatically():
    for guild in bot.guilds:
        channel = guild.get_channel(TICKET_CHANNEL_ID)
        if channel is None:
            continue
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
                "Aşağıdaki **📩 Talep Aç** butonuna tıkla, sana özel bir kanal açalım.\n\n"
                "**📌 Lütfen:**\n"
                "• Sorununu net şekilde yaz\n"
                "• Görsel/video ekleyebilirsin\n"
                "• Sorun çözülünce 🔒 butonuyla talebi kapat"
            ),
            color=EMBED_COLOR,
        )
        embed.set_footer(text=f"{SERVER_NAME} • Destek Sistemi")
        try:
            await channel.send(embed=embed, view=TicketPanelView())
            log.info(f"✅ Ticket paneli {channel.name} kanalına gönderildi.")
        except:
            pass


async def send_contact_panel_automatically():
    for guild in bot.guilds:
        channel = guild.get_channel(KURUCU_DESTEK_CHANNEL_ID)
        if channel is None:
            continue
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
                "Aşağıdaki **✉️ Mesaj Gönder** butonuna tıkla, açılan formu doldur ve gönder.\n"
                "Mesajın direkt kurucumuza iletilecek."
            ),
            color=EMBED_COLOR,
        )
        embed.set_footer(text=f"{SERVER_NAME} • Kurucu İletişim Sistemi")
        try:
            await channel.send(embed=embed, view=ContactFounderView())
            log.info(f"✅ İletişim paneli {channel.name} kanalına gönderildi.")
        except:
            pass


# ============================================================
# EVENT'LER
# ============================================================
@bot.event
async def on_ready():
    await bot.wait_until_ready()
    
    update_presence.start()
    
    await send_ticket_panel_automatically()
    await send_contact_panel_automatically()
    
    # Persistent View'ları ekle
    bot.add_view(TicketPanelView())
    bot.add_view(TicketControlView())
    bot.add_view(ContactFounderView())
    bot.add_view(KeyPanelView())
    
    log.info(f"✅ {bot.user} olarak giriş yapıldı!")
    log.info(f"📊 {len(bot.guilds)} sunucuda aktif.")


@bot.event
async def on_member_join(member: discord.Member):
    channel = member.guild.get_channel(GELEN_GIDEN_CHANNEL_ID)
    if channel:
        try:
            file = await build_member_card(member, WELCOME_BG, is_welcome=True)
            embed = discord.Embed(color=EMBED_COLOR)
            embed.set_image(url="attachment://card.png")
            embed.set_footer(text=f"Sunucumuz artık {member.guild.member_count} kişi! 🚀")
            await channel.send(content=f"{member.mention} Hoşgeldin! 🎉", embed=embed, file=file)
            log.info(f"✅ {member} için karşılama kartı gönderildi!")
        except Exception as e:
            log.error(f"Karşılama kartı hatası: {e}")
            await channel.send(f"{member.mention} SantesHub'a hoşgeldin! 🎉")
    await log_member_join(member)


@bot.event
async def on_member_remove(member: discord.Member):
    channel = member.guild.get_channel(GELEN_GIDEN_CHANNEL_ID)
    if channel:
        try:
            file = await build_member_card(member, GOODBYE_BG, is_welcome=False)
            embed = discord.Embed(color=EMBED_COLOR)
            embed.set_image(url="attachment://card.png")
            embed.set_footer(text=f"Şu an {member.guild.member_count} kişi kaldık.")
            await channel.send(content=f"**{member}** aramızdan ayrıldı. 👋", embed=embed, file=file)
            log.info(f"✅ {member} için uğurlama kartı gönderildi!")
        except Exception as e:
            log.error(f"Uğurlama kartı hatası: {e}")
            await channel.send(f"**{member}** aramızdan ayrıldı. 👋")
    await log_member_remove(member)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        return

    AUTO_REPLIES = [
        (r"\b(sa|selam|selamun aleykum)\b", "Aleyküm selam! 👋 {mention} SantesHub'a hoş geldin!"),
        (r"\bnaber\b", "İyidir, senden naber {mention}? 😄"),
        (r"\b(yardım|yardim)\b", "Yardıma mı ihtiyacın var {mention}? 🎫 Ticket açabilirsin!"),
    ]
    AUTO_REPLY_COOLDOWN = 30
    _last_reply_at = getattr(bot, '_last_reply_at', {})
    
    reply = None
    for pattern, response in AUTO_REPLIES:
        if re.search(pattern, message.content.lower()):
            reply = response
            break
    
    if reply:
        now = datetime.now(timezone.utc).timestamp()
        last = _last_reply_at.get(message.author.id, 0)
        if now - last >= AUTO_REPLY_COOLDOWN:
            _last_reply_at[message.author.id] = now
            bot._last_reply_at = _last_reply_at
            try:
                await message.channel.send(reply.format(mention=message.author.mention))
            except:
                pass

    await bot.process_commands(message)


# ============================================================
# KOMUTLAR
# ============================================================
@bot.command(name="keypanel")
async def keypanel_command(ctx):
    embed = discord.Embed(
        title="🔑 SantesHub Key Sistemi",
        description=(
            "Aşağıdaki menüden satın almak istediğiniz key süresini seçin.\n\n"
            "**📌 Fiyat Listesi:**\n"
            "• 🟢 1 Günlük Executor Keyi - **150 TL**\n"
            "• 🟡 1 Haftalık Executor Keyi - **300 TL**\n"
            "• 🔴 1 Aylık Executor Keyi - **500 TL**\n\n"
            "✅ Talebiniz oluşturulduktan sonra kurucu sizinle iletişime geçecektir."
        ),
        color=EMBED_COLOR,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_image(url="https://i.ibb.co/nMZC2N0q/mark.png")
    embed.set_footer(text=f"{SERVER_NAME} • Key Sistemi")
    
    await ctx.send(embed=embed, view=KeyPanelView())
    try:
        await ctx.message.delete()
    except:
        pass


@bot.command(name="keyonay")
@commands.check(yetkili_kontrol)
async def keyonay_command(ctx, request_id: str):
    if request_id not in pending_keys:
        await ctx.send("❌ Bu talep ID'si bulunamadı veya zaten işlem görmüş!")
        return
    
    data = pending_keys[request_id]
    user_id = data["user_id"]
    key_type = data["key_type"]
    key_name = data["key_name"]
    temp_key = data["temp_key"]
    
    key_database[temp_key] = {
        "user_id": user_id,
        "key_type": key_type,
        "key_name": key_name,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + get_key_duration(key_type),
        "used": False,
        "activated_by": str(ctx.author)
    }
    
    user = bot.get_user(user_id)
    if user is None:
        try:
            user = await bot.fetch_user(user_id)
        except:
            pass
    
    if user:
        try:
            key_embed = discord.Embed(
                title="🔑 Key'iniz Hazır!",
                description=(
                    f"**Key Tipi:** {key_name}\n"
                    f"**Key:** `{format_key(temp_key)}`\n\n"
                    f"**📅 Geçerlilik Süresi:** {get_key_duration(key_type).days} gün\n"
                    f"**⏰ Bitiş Tarihi:** <t:{int((datetime.now(timezone.utc) + get_key_duration(key_type)).timestamp())}:D>\n\n"
                    "⚠️ Key'inizi kimseyle paylaşmayın!"
                ),
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            key_embed.set_footer(text=f"{SERVER_NAME} • Key Sistemi")
            
            await user.send(embed=key_embed)
            
            del pending_keys[request_id]
            
            embed = discord.Embed(
                title="✅ Key Onaylandı!",
                description=f"**{user.mention}** adlı kullanıcıya key gönderildi.",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Talep ID", value=request_id, inline=True)
            embed.add_field(name="Key Tipi", value=key_name, inline=True)
            embed.add_field(name="Key", value=f"`{format_key(temp_key)}`", inline=True)
            embed.set_footer(text=f"{SERVER_NAME} • Key Yönetim Sistemi")
            await ctx.send(embed=embed)
            
            log_channel = bot.get_channel(KEY_LOG_CHANNEL_ID)
            if log_channel:
                log_embed = discord.Embed(
                    title="✅ Key Onaylandı",
                    description=f"{user.mention} için key onaylandı.",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                log_embed.add_field(name="Talep ID", value=request_id, inline=True)
                log_embed.add_field(name="Key Tipi", value=key_name, inline=True)
                log_embed.add_field(name="Key", value=f"`{format_key(temp_key)}`", inline=True)
                log_embed.add_field(name="Onaylayan", value=ctx.author.mention, inline=True)
                await log_channel.send(embed=log_embed)
                
        except Exception as e:
            await ctx.send(f"❌ Kullanıcıya mesaj gönderilemedi! Hata: {e}")
    else:
        await ctx.send("❌ Kullanıcı bulunamadı!")


@bot.command(name="keyred")
@commands.check(yetkili_kontrol)
async def keyred_command(ctx, request_id: str):
    if request_id not in pending_keys:
        await ctx.send("❌ Bu talep ID'si bulunamadı veya zaten işlem görmüş!")
        return
    
    data = pending_keys[request_id]
    user_id = data["user_id"]
    key_name = data["key_name"]
    
    user = bot.get_user(user_id)
    if user is None:
        try:
            user = await bot.fetch_user(user_id)
        except:
            pass
    
    if user:
        try:
            red_embed = discord.Embed(
                title="❌ Key Talebiniz Reddedildi",
                description=(
                    f"**Key Tipi:** {key_name}\n\n"
                    "📌 Talebiniz kurucu tarafından reddedildi.\n"
                    "Detaylı bilgi için kurucu ile iletişime geçin."
                ),
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            red_embed.set_footer(text=f"{SERVER_NAME} • Key Sistemi")
            
            await user.send(embed=red_embed)
        except:
            pass
    
    del pending_keys[request_id]
    
    embed = discord.Embed(
        title="❌ Key Reddedildi",
        description=f"**{user.mention if user else 'Kullanıcı'}** adlı kullanıcının talebi reddedildi.",
        color=discord.Color.red(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Talep ID", value=request_id, inline=True)
    embed.add_field(name="Key Tipi", value=key_name, inline=True)
    embed.add_field(name="Reddeden", value=ctx.author.mention, inline=True)
    embed.set_footer(text=f"{SERVER_NAME} • Key Yönetim Sistemi")
    await ctx.send(embed=embed)
    
    log_channel = bot.get_channel(KEY_LOG_CHANNEL_ID)
    if log_channel:
        log_embed = discord.Embed(
            title="❌ Key Reddedildi",
            description=f"{user.mention if user else 'Bilinmeyen kullanıcı'} talebi reddedildi.",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.add_field(name="Talep ID", value=request_id, inline=True)
        log_embed.add_field(name="Key Tipi", value=key_name, inline=True)
        log_embed.add_field(name="Reddeden", value=ctx.author.mention, inline=True)
        await log_channel.send(embed=log_embed)


@bot.command(name="keylist")
@commands.check(yetkili_kontrol)
async def keylist_command(ctx):
    if not key_database:
        await ctx.send("📭 Hiç aktif key bulunmuyor.")
        return
    
    embed = discord.Embed(
        title="🔑 Aktif Key Listesi",
        color=EMBED_COLOR,
        timestamp=datetime.now(timezone.utc)
    )
    
    active_keys = []
    expired_keys = []
    
    for key, data in key_database.items():
        expires_at = data["expires_at"]
        now = datetime.now(timezone.utc)
        
        if expires_at > now:
            active_keys.append(f"`{format_key(key)}` - {data['key_name']} - <t:{int(expires_at.timestamp())}:R>")
        else:
            expired_keys.append(f"`{format_key(key)}` - {data['key_name']} - Süresi doldu")
    
    if active_keys:
        embed.add_field(
            name=f"✅ Aktif Keyler ({len(active_keys)})",
            value="\n".join(active_keys[:10]) + (f"\nve {len(active_keys)-10} daha..." if len(active_keys) > 10 else ""),
            inline=False
        )
    else:
        embed.add_field(name="✅ Aktif Keyler", value="Hiç aktif key yok", inline=False)
    
    if expired_keys:
        embed.add_field(
            name=f"⏰ Süresi Dolan Keyler ({len(expired_keys)})",
            value="\n".join(expired_keys[:5]) + (f"\nve {len(expired_keys)-5} daha..." if len(expired_keys) > 5 else ""),
            inline=False
        )
    
    embed.set_footer(text=f"{SERVER_NAME} • Key Yönetim Sistemi")
    await ctx.send(embed=embed)


@bot.command(name="keykontrol")
async def keykontrol_command(ctx, key: str):
    clean_key = key.replace("-", "").upper()
    
    if clean_key in key_database:
        data = key_database[clean_key]
        expires_at = data["expires_at"]
        now = datetime.now(timezone.utc)
        
        if expires_at > now:
            embed = discord.Embed(
                title="✅ Geçerli Key",
                description=f"**Key:** `{format_key(clean_key)}`\n**Tip:** {data['key_name']}\n**Bitiş:** <t:{int(expires_at.timestamp())}:D> (<t:{int(expires_at.timestamp())}:R>)",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_footer(text=f"{SERVER_NAME} • Key Kontrol")
        else:
            embed = discord.Embed(
                title="❌ Key Süresi Dolmuş",
                description=f"**Key:** `{format_key(clean_key)}`\n**Tip:** {data['key_name']}\n**Bitiş:** <t:{int(expires_at.timestamp())}:D> (Süresi doldu)",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_footer(text=f"{SERVER_NAME} • Key Kontrol")
    else:
        embed = discord.Embed(
            title="❌ Geçersiz Key",
            description=f"**Key:** `{format_key(clean_key)}`\nBu key sistemde bulunamadı!",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"{SERVER_NAME} • Key Kontrol")
    
    await ctx.send(embed=embed)


@bot.command(name="sorgupanel")
@commands.check(yetkili_kontrol)
async def sorgupanel_command(ctx):
    embed = discord.Embed(
        title="✦ SANTESHUB - Ücretsiz Sorgu Toolu ✦",
        description=(
            "Aşağıdaki menüden yapmak istediğiniz ücretsiz sorguyu seçin.\n"
            "Sonuçlar doğrudan özel mesaj (DM) kutunuza gönderilecektir.\n\n"
            "**› Bot Token**\n"
            "Detaylı token analizi ve doğrulama\n"
            "**› Discord ID**\n"
            "Detaylı ID analizi ve kullanıcı bilgileri\n"
            "**› Domain WHOIS**\n"
            "Domain kayıt bilgileri ve sahiplik\n"
            "**› Domain DNS**\n"
            "DNS kayıtları ve MX sorgulama\n"
            "**› IP Konum**\n"
            "IP adresi coğrafi konum ve ISP\n"
            "**› SSL Kontrol**\n"
            "SSL sertifikası doğrulama\n"
            "**› Port Tarama**\n"
            "Açık port kontrolü\n"
            "**› URL Güvenlik**\n"
            "URL güvenlik kontrolü\n"
            "**› Ping Test**\n"
            "Sunucu ping ve gecikme testi"
        ),
        color=EMBED_COLOR
    )
    embed.set_image(url="https://i.ibb.co/nMZC2N0q/mark.png")
    embed.set_footer(text="✦ SANTESHUB - Ücretsiz Sorgu Sistemi ✦")
    
    await ctx.send(embed=embed, view=SorguPanelView())
    await ctx.message.delete()


@bot.command(name="mesaj")
@commands.check(yetkili_kontrol)
async def mesaj_command(ctx):
    await ctx.send("📢 Duyuru oluşturmak için aşağıdaki butona tıkla!", view=DuyuruButtonView(), delete_after=30)
    try:
        await ctx.message.delete()
    except:
        pass


@bot.command(name="ping")
async def ping_command(ctx):
    latency = round(bot.latency * 1000)
    uptime = get_uptime()
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"**Gecikme:** {latency}ms\n**Çalışma Süresi:** {uptime}",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)


@bot.command(name="sunucu")
async def sunucu_command(ctx):
    guild = ctx.guild
    embed = discord.Embed(
        title=f"🏰 {guild.name}",
        color=EMBED_COLOR,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    embed.add_field(name="👑 Sahip", value=guild.owner.mention, inline=True)
    embed.add_field(name="👥 Üye Sayısı", value=guild.member_count, inline=True)
    embed.add_field(name="📅 Kuruluş", value=f"<t:{int(guild.created_at.timestamp())}:D>", inline=True)
    embed.add_field(name="📢 Kanal Sayısı", value=len(guild.channels), inline=True)
    embed.add_field(name="🎭 Rol Sayısı", value=len(guild.roles), inline=True)
    embed.add_field(name="💬 Boost", value=guild.premium_subscription_count or 0, inline=True)
    embed.set_footer(text=f"{SERVER_NAME} • Sunucu Bilgileri")
    await ctx.send(embed=embed)


@bot.command(name="yardim")
async def yardim_command(ctx):
    embed = discord.Embed(
        title=f"📚 {SERVER_NAME} Bot Komutları",
        description="**Prefix:** `.`",
        color=EMBED_COLOR
    )
    
    embed.add_field(
        name="🔑 Key Sistemi",
        value=(
            "`.keypanel` - Key satın alma panelini açar\n"
            "`.keyonay <talep_id>` - Key talebini onaylar (Yetkili)\n"
            "`.keyred <talep_id>` - Key talebini reddeder (Yetkili)\n"
            "`.keylist` - Aktif key'leri listeler (Yetkili)\n"
            "`.keykontrol <key>` - Key geçerliliğini kontrol eder"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🔍 Sorgu Sistemi",
        value=(
            "`.sorgupanel` - Sorgu panelini açar (Yetkili)\n"
            "• Token analizi, ID sorgu, Domain WHOIS/DNS\n"
            "• IP Konum, SSL Kontrol, Port Tarama\n"
            "• URL Güvenlik, Ping Test"
        ),
        inline=False
    )
    
    embed.add_field(
        name="👑 Yetkili Komutları",
        value=(
            "`.ban @kişi <sebep>` - Üyeyi banlar\n"
            "`.kick @kişi <sebep>` - Üyeyi kickler\n"
            "`.mute @kişi <süre> <sebep>` - Üyeyi susturur\n"
            "`.unmute @kişi` - Susturmayı kaldırır\n"
            "`.temizle <sayı>` - Mesajları siler (1-1000)\n"
            "`.ticketpanel` - Ticket panelini gönderir\n"
            "`.kurucupanel` - Kurucu panelini gönderir\n"
            "`.mesaj` - Duyuru gönderir (Modal açar)\n"
            "`.lock` - Kanaldaki yazma iznini kapatır\n"
            "`.unlock` - Kanaldaki yazma iznini açar\n"
            "`.nuke` - Kanalı silip yeniden oluşturur"
        ),
        inline=False
    )
    
    embed.add_field(
        name="📋 Genel Komutlar",
        value=(
            "`.ping` - Bot gecikmesini gösterir\n"
            "`.sunucu` - Sunucu bilgilerini gösterir\n"
            "`.yardim` - Bu menüyü gösterir"
        ),
        inline=False
    )
    
    embed.set_footer(text=f"{SERVER_NAME} • Yardım Menüsü")
    await ctx.send(embed=embed)


# ============================================================
# YETKİLİ KOMUTLARI
# ============================================================
@bot.command(name="ban")
@commands.check(yetkili_kontrol)
async def ban_command(ctx, member: discord.Member, *, reason: str = "Belirtilmedi"):
    try:
        await member.ban(reason=reason)
        embed = discord.Embed(
            title="🔨 Üye Banlandı",
            description=f"{member.mention} banlandı!",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Sebep", value=reason, inline=False)
        embed.add_field(name="Yetkili", value=ctx.author.mention, inline=True)
        await ctx.send(embed=embed)
        
        log_embed = discord.Embed(
            title="🔨 Ban",
            description=f"{member} banlandı",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.add_field(name="Yetkili", value=ctx.author, inline=True)
        log_embed.add_field(name="Sebep", value=reason, inline=True)
        await send_log(log_embed)
    except Exception as e:
        await ctx.send(f"❌ Ban işlemi başarısız: {e}")


@bot.command(name="kick")
@commands.check(yetkili_kontrol)
async def kick_command(ctx, member: discord.Member, *, reason: str = "Belirtilmedi"):
    try:
        await member.kick(reason=reason)
        embed = discord.Embed(
            title="👢 Üye Kicklendi",
            description=f"{member.mention} kicklendi!",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Sebep", value=reason, inline=False)
        embed.add_field(name="Yetkili", value=ctx.author.mention, inline=True)
        await ctx.send(embed=embed)
        
        log_embed = discord.Embed(
            title="👢 Kick",
            description=f"{member} kicklendi",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.add_field(name="Yetkili", value=ctx.author, inline=True)
        log_embed.add_field(name="Sebep", value=reason, inline=True)
        await send_log(log_embed)
    except Exception as e:
        await ctx.send(f"❌ Kick işlemi başarısız: {e}")


@bot.command(name="mute")
@commands.check(yetkili_kontrol)
async def mute_command(ctx, member: discord.Member, sure: int = 60, *, sebep: str = "Belirtilmedi"):
    try:
        duration = timedelta(minutes=sure)
        await member.timeout(duration, reason=sebep)
        embed = discord.Embed(
            title="🔇 Üye Susturuldu",
            description=f"{member.mention} {sure} dakika susturuldu!",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Sebep", value=sebep, inline=False)
        embed.add_field(name="Yetkili", value=ctx.author.mention, inline=True)
        await ctx.send(embed=embed)
        
        log_embed = discord.Embed(
            title="🔇 Mute",
            description=f"{member} susturuldu",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.add_field(name="Süre", value=f"{sure} dakika", inline=True)
        log_embed.add_field(name="Sebep", value=sebep, inline=True)
        await send_log(log_embed)
    except Exception as e:
        await ctx.send(f"❌ Mute işlemi başarısız: {e}")


@bot.command(name="unmute")
@commands.check(yetkili_kontrol)
async def unmute_command(ctx, member: discord.Member):
    try:
        await member.timeout(None)
        embed = discord.Embed(
            title="🔊 Susturma Kaldırıldı",
            description=f"{member.mention} susturması kaldırıldı!",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Yetkili", value=ctx.author.mention, inline=True)
        await ctx.send(embed=embed)
        
        log_embed = discord.Embed(
            title="🔊 Unmute",
            description=f"{member} susturması kaldırıldı",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.add_field(name="Yetkili", value=ctx.author, inline=True)
        await send_log(log_embed)
    except Exception as e:
        await ctx.send(f"❌ Unmute işlemi başarısız: {e}")


@bot.command(name="temizle")
@commands.check(yetkili_kontrol)
async def temizle_command(ctx, miktar: int):
    if miktar < 1 or miktar > 1000:
        await ctx.send("❌ 1-1000 arası bir sayı girin!")
        return
    
    try:
        deleted = await ctx.channel.purge(limit=miktar + 1, bulk=True)
        msg = await ctx.send(f"✅ {len(deleted) - 1} mesaj silindi!", delete_after=2)
        await asyncio.sleep(2)
        await msg.delete()
    except Exception as e:
        await ctx.send(f"❌ Mesajlar silinemedi: {e}")


@bot.command(name="ticketpanel")
@commands.check(yetkili_kontrol)
async def ticketpanel_command(ctx):
    await send_ticket_panel_automatically()
    await ctx.send("✅ Ticket paneli gönderildi!", delete_after=3)


@bot.command(name="kurucupanel")
@commands.check(yetkili_kontrol)
async def kurucupanel_command(ctx):
    await send_contact_panel_automatically()
    await ctx.send("✅ Kurucu iletişim paneli gönderildi!", delete_after=3)


@bot.command(name="lock")
@commands.check(yetkili_kontrol)
async def lock_command(ctx):
    try:
        everyone = ctx.guild.default_role
        perms = ctx.channel.overwrites_for(everyone)
        perms.send_messages = False
        perms.add_reactions = False
        
        await ctx.channel.set_permissions(everyone, overwrite=perms)
        
        embed = discord.Embed(
            title="🔒 Kanal Kilitlendi",
            description=f"{ctx.channel.mention} kanalı kilitlendi! Sadece yetkililer yazabilir.",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Yetkili", value=ctx.author.mention, inline=True)
        embed.set_footer(text=f"{SERVER_NAME} • Kanal Yönetimi")
        await ctx.send(embed=embed)
        
        log_embed = discord.Embed(
            title="🔒 Kanal Kilitlendi",
            description=f"{ctx.channel.mention} kanalı {ctx.author} tarafından kilitlendi.",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        await send_log(log_embed)
    except Exception as e:
        await ctx.send(f"❌ Kanal kilitlenemedi: {e}")


@bot.command(name="unlock")
@commands.check(yetkili_kontrol)
async def unlock_command(ctx):
    try:
        everyone = ctx.guild.default_role
        perms = ctx.channel.overwrites_for(everyone)
        perms.send_messages = None
        perms.add_reactions = None
        
        await ctx.channel.set_permissions(everyone, overwrite=perms)
        
        embed = discord.Embed(
            title="🔓 Kanal Açıldı",
            description=f"{ctx.channel.mention} kanalının kilidi açıldı! Herkes yazabilir.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Yetkili", value=ctx.author.mention, inline=True)
        embed.set_footer(text=f"{SERVER_NAME} • Kanal Yönetimi")
        await ctx.send(embed=embed)
        
        log_embed = discord.Embed(
            title="🔓 Kanal Açıldı",
            description=f"{ctx.channel.mention} kanalının kilidi {ctx.author} tarafından açıldı.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        await send_log(log_embed)
    except Exception as e:
        await ctx.send(f"❌ Kanal açılamadı: {e}")


@bot.command(name="nuke")
@commands.check(yetkili_kontrol)
async def nuke_command(ctx):
    try:
        channel = ctx.channel
        
        channel_name = channel.name
        channel_category = channel.category
        channel_position = channel.position
        channel_topic = channel.topic
        channel_slowmode = channel.slowmode_delay
        channel_nsfw = channel.is_nsfw()
        
        channel_overwrites = {}
        for target, overwrite in channel.overwrites.items():
            channel_overwrites[target] = overwrite
        
        await channel.delete(reason=f"{ctx.author} tarafından nuke işlemi")
        
        new_channel = await ctx.guild.create_text_channel(
            name=channel_name,
            category=channel_category,
            position=channel_position,
            topic=channel_topic,
            slowmode_delay=channel_slowmode,
            nsfw=channel_nsfw,
            overwrites=channel_overwrites,
            reason=f"{ctx.author} tarafından nuke işlemi"
        )
        
        embed = discord.Embed(
            title="💥 Kanal Nuke İşlemi Tamamlandı!",
            description=f"{new_channel.mention} kanalı başarıyla yeniden oluşturuldu!",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Eski Kanal", value=f"#{channel_name}", inline=True)
        embed.add_field(name="Yeni Kanal", value=new_channel.mention, inline=True)
        embed.add_field(name="Yetkili", value=ctx.author.mention, inline=True)
        embed.set_footer(text=f"{SERVER_NAME} • Nuke Sistemi")
        await new_channel.send(embed=embed)
        
        log_embed = discord.Embed(
            title="💥 Nuke İşlemi",
            description=f"{new_channel.mention} kanalı {ctx.author} tarafından nuke işlemine uğradı.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.add_field(name="Eski Kanal", value=f"#{channel_name}", inline=True)
        await send_log(log_embed)
    except Exception as e:
        await ctx.send(f"❌ Nuke işlemi başarısız: {e}")


if __name__ == "__main__":
    if not BOT_TOKEN:
        raise SystemExit("❌ BOT_TOKEN ortam değişkeni ayarlanmamış!")
    bot.run(BOT_TOKEN)

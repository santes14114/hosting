import os
import re
import io
import asyncio
import logging
import time
import aiohttp
import socket
import dns.resolver
import whois
import requests
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands, tasks
from PIL import Image, ImageDraw, ImageFont, ImageFilter

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

KURUCU_ID = 359199132906422273
KURUCU_ADI = "Santess"

# Yetkili Rolleri
YETKILI_ROLLER = [
    1514893588125716633,
    1514893665393315871
]

SERVER_NAME = "SantesHub"
EMBED_COLOR = discord.Color.from_str("#B00000")

# Discord Uygulama ID (Rich Presence için)
DISCORD_CLIENT_ID = "1357163103920320633"

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


# ============================================================
# YARDIMCI FONKSİYONLAR
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
# BOT DURUMU - YAYINDA (STREAMING)
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
# SORGU PANELİ (SELECT MENU İLE)
# ============================================================
class SorguSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Domain WHOIS",
                description="Domain kayıt bilgileri ve sahiplik",
                value="domain_whois",
                emoji="🌐"
            ),
            discord.SelectOption(
                label="Domain DNS",
                description="DNS kayıtları ve MX sorgulama",
                value="domain_dns",
                emoji="🔍"
            ),
            discord.SelectOption(
                label="IP Konum",
                description="IP adresi coğrafi konum ve ISP",
                value="ip_location",
                emoji="🌍"
            ),
            discord.SelectOption(
                label="SSL Kontrol",
                description="SSL sertifikası doğrulama",
                value="ssl_check",
                emoji="🔒"
            ),
            discord.SelectOption(
                label="Port Tarama",
                description="Açık port kontrolü",
                value="port_scan",
                emoji="🔓"
            ),
            discord.SelectOption(
                label="Discord ID",
                description="Discord kullanıcı profili sorgula",
                value="discord_id",
                emoji="🆔"
            ),
            discord.SelectOption(
                label="URL Güvenlik",
                description="URL güvenlik kontrolü",
                value="url_safety",
                emoji="🔗"
            ),
            discord.SelectOption(
                label="Bot Token",
                description="Bot token doğrulama",
                value="token_check",
                emoji="🤖"
            ),
            discord.SelectOption(
                label="Ping",
                description="Sunucu ping ve gecikme testi",
                value="ping_test",
                emoji="🏓"
            ),
        ]
        super().__init__(
            placeholder="📋 Sorgu seçiniz...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        secim = self.values[0]
        
        if secim == "domain_whois":
            await interaction.response.send_modal(DomainWhoisModal())
        elif secim == "domain_dns":
            await interaction.response.send_modal(DomainDNSModal())
        elif secim == "ip_location":
            await interaction.response.send_modal(IPLocationModal())
        elif secim == "ssl_check":
            await interaction.response.send_modal(SSLModal())
        elif secim == "port_scan":
            await interaction.response.send_modal(PortScanModal())
        elif secim == "discord_id":
            await interaction.response.send_modal(DiscordIDModal())
        elif secim == "url_safety":
            await interaction.response.send_modal(URLSafetyModal())
        elif secim == "token_check":
            await interaction.response.send_modal(TokenCheckModal())
        elif secim == "ping_test":
            await interaction.response.send_modal(PingModal())


class SorguPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(SorguSelect())


# ============================================================
# SORGU MODALLARI (LEGAL VE ÇALIŞAN ARAÇLAR)
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
        
        try:
            # A kaydı
            try:
                answers = dns.resolver.resolve(domain, 'A')
                ip_list = [str(r) for r in answers]
                embed.add_field(name="🌐 A Kaydı (IPv4)", value="\n".join(ip_list[:5]), inline=True)
            except:
                embed.add_field(name="🌐 A Kaydı", value="Bulunamadı", inline=True)
            
            # MX kaydı
            try:
                answers = dns.resolver.resolve(domain, 'MX')
                mx_list = [f"{r.exchange} ({r.preference})" for r in answers]
                embed.add_field(name="📧 MX Kaydı", value="\n".join(mx_list[:3]), inline=True)
            except:
                embed.add_field(name="📧 MX Kaydı", value="Bulunamadı", inline=True)
            
            # NS kaydı
            try:
                answers = dns.resolver.resolve(domain, 'NS')
                ns_list = [str(r) for r in answers]
                embed.add_field(name="🔄 NS Kaydı", value="\n".join(ns_list[:3]), inline=True)
            except:
                embed.add_field(name="🔄 NS Kaydı", value="Bulunamadı", inline=True)
            
            # TXT kaydı
            try:
                answers = dns.resolver.resolve(domain, 'TXT')
                txt_list = [str(r)[:50] + "..." for r in answers[:2]]
                embed.add_field(name="📝 TXT Kaydı", value="\n".join(txt_list) if txt_list else "Bulunamadı", inline=True)
            except:
                pass
                
        except Exception as e:
            embed.add_field(name="❌ Hata", value=f"DNS sorgulanamadı: {str(e)[:100]}", inline=True)
        
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
            # ip-api.com API (ücretsiz, limitsiz)
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
            import ssl
            import socket
            from datetime import datetime
            
            context = ssl.create_default_context()
            with socket.create_connection((domain, 443), timeout=5) as sock:
                with context.wrap_socket(sock, server_hostname=domain) as ssock:
                    cert = ssock.getpeercert()
                    
                    embed.add_field(name="✅ Durum", value="SSL sertifikası aktif", inline=True)
                    embed.add_field(name="🏷️ Yayınlayan", value=cert.get('issuer', {}).get('organizationName', ['Bilinmiyor'])[0], inline=True)
                    embed.add_field(name="🔑 Konu", value=cert.get('subject', {}).get('commonName', ['Bilinmiyor'])[0], inline=True)
                    
                    # Başlangıç ve bitiş tarihleri
                    not_before = datetime.strptime(cert['notBefore'], '%b %d %H:%M:%S %Y %Z')
                    not_after = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
                    
                    embed.add_field(name="📅 Başlangıç", value=f"<t:{int(not_before.timestamp())}:D>", inline=True)
                    embed.add_field(name="📅 Bitiş", value=f"<t:{int(not_after.timestamp())}:D>", inline=True)
                    
                    # Kalan gün
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
        
        # Yaygın portlar
        common_ports = {
            21: "FTP",
            22: "SSH",
            23: "Telnet",
            25: "SMTP",
            53: "DNS",
            80: "HTTP",
            110: "POP3",
            143: "IMAP",
            443: "HTTPS",
            3306: "MySQL",
            3389: "RDP",
            5432: "PostgreSQL",
            6379: "Redis",
            27017: "MongoDB"
        }
        
        open_ports = []
        try:
            # Hostname çözümleme
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


class DiscordIDModal(discord.ui.Modal, title="🆔 Discord ID Sorgu"):
    user_id = discord.ui.TextInput(
        label="Discord ID",
        placeholder="Kullanıcı ID'sini girin...",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(self.user_id.value)
            user = await bot.fetch_user(user_id)
            
            embed = discord.Embed(
                title="🆔 Discord Kullanıcı Bilgileri",
                color=user.color if user.color else discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.add_field(name="👤 Kullanıcı Adı", value=f"{user.name}#{user.discriminator}", inline=True)
            embed.add_field(name="🆔 ID", value=user.id, inline=True)
            embed.add_field(name="🤖 Bot mu?", value="Evet ✅" if user.bot else "Hayır ❌", inline=True)
            embed.add_field(name="📅 Hesap Oluşturma", value=f"<t:{int(user.created_at.timestamp())}:D>\n<t:{int(user.created_at.timestamp())}:R>", inline=False)
            embed.set_footer(text="✦ SANTESHUB - Ücretsiz Sorgu Toolu ✦")
            
            try:
                await interaction.user.send(embed=embed)
                await interaction.response.send_message("✅ Kullanıcı bilgileri DM'ine gönderildi!", ephemeral=True)
            except:
                await interaction.response.send_message("❌ DM'ine mesaj gönderemedim! DM'lerini aç.", ephemeral=True)
                
        except ValueError:
            await interaction.response.send_message("❌ Geçersiz ID formatı!", ephemeral=True)
        except discord.NotFound:
            await interaction.response.send_message("❌ Bu ID'ye sahip bir kullanıcı bulunamadı!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Hata: {e}", ephemeral=True)


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
            
            # SSL kontrolü
            try:
                import ssl
                import socket
                context = ssl.create_default_context()
                with socket.create_connection((parsed.netloc, 443), timeout=3) as sock:
                    with context.wrap_socket(sock, server_hostname=parsed.netloc) as ssock:
                        cert = ssock.getpeercert()
                        embed.add_field(name="🔒 SSL", value="Aktif ✅", inline=True)
            except:
                embed.add_field(name="🔒 SSL", value="Yok veya HTTPS değil ⚠️", inline=True)
            
            # HTTP durum kodu kontrolü
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


class TokenCheckModal(discord.ui.Modal, title="🤖 Bot Token Kontrol"):
    token = discord.ui.TextInput(
        label="Bot Token",
        placeholder="Bot token'ını girin...",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        token_text = self.token.value.strip()
        
        embed = discord.Embed(
            title="🤖 Bot Token Kontrol Sonucu",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        # Token format kontrolü
        if len(token_text) > 30 and "." in token_text:
            embed.add_field(name="✅ Format", value="Geçerli token formatı", inline=True)
            
            parts = token_text.split(".")
            if len(parts) == 3:
                embed.add_field(name="📝 Yapı", value="Bot Token (3 parçalı)", inline=True)
            else:
                embed.add_field(name="📝 Yapı", value="Bilinmeyen format", inline=True)
            
            embed.add_field(name="📏 Uzunluk", value=f"{len(token_text)} karakter", inline=True)
            
            # Bot ID çıkarma (ilk kısım base64 decode)
            try:
                import base64
                first_part = parts[0]
                padding = 4 - (len(first_part) % 4)
                if padding != 4:
                    first_part += "=" * padding
                
                decoded = base64.b64decode(first_part)
                if len(decoded) >= 8:
                    bot_id = int.from_bytes(decoded[:8], 'big')
                    embed.add_field(name="🤖 Bot ID", value=str(bot_id), inline=True)
            except:
                pass
            
            # Token doğrulama (gerçek API çağrısı yok, sadece format)
            embed.add_field(name="✅ Durum", value="Token formatı geçerli (API kontrolü yapılmadı)", inline=False)
        else:
            embed.add_field(name="❌ Durum", value="Geçersiz token formatı!", inline=False)
        
        embed.set_footer(text="✦ SANTESHUB - Ücretsiz Sorgu Toolu ✦")
        
        try:
            await interaction.user.send(embed=embed)
            await interaction.response.send_message("✅ Token bilgileri DM'ine gönderildi!", ephemeral=True)
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
            import subprocess
            import platform
            
            # Ping işlemi
            param = '-n' if platform.system().lower() == 'windows' else '-c'
            command = ['ping', param, '4', hedef]
            
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                embed.add_field(name="✅ Durum", value="Erişilebilir", inline=True)
                
                # Ping sürelerini çıkart
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'time=' in line or 'time<' in line:
                        # Linux/Unix
                        if 'time=' in line:
                            time_ms = line.split('time=')[1].split(' ')[0]
                            embed.add_field(name="⏱️ Gecikme", value=f"{time_ms} ms", inline=True)
                            break
                        # Windows
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
# DUYURU / MESAJ KOMUTU (Modal ile Webhook)
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
# SORGU PANEL KOMUTU
# ============================================================
@bot.command(name="sorgupanel")
@commands.check(yetkili_kontrol)
async def sorgupanel_command(ctx):
    """Sorgu panelini gönderir"""
    embed = discord.Embed(
        title="✦ SANTESHUB - Ücretsiz Sorgu Toolu ✦",
        description=(
            "Aşağıdaki menüden yapmak istediğiniz ücretsiz sorguyu seçin.\n"
            "Sonuçlar doğrudan özel mesaj (DM) kutunuza gönderilecektir.\n\n"
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
            "**› Discord ID**\n"
            "Discord kullanıcı profili sorgula\n"
            "**› URL Güvenlik**\n"
            "URL güvenlik kontrolü\n"
            "**› Bot Token**\n"
            "Bot token doğrulama\n"
            "**› Ping Test**\n"
            "Sunucu ping ve gecikme testi"
        ),
        color=EMBED_COLOR
    )
    embed.set_image(url="https://i.ibb.co/nMZC2N0q/mark.png")
    embed.set_footer(text="✦ SANTESHUB - Ücretsiz Sorgu Sistemi ✦")
    
    await ctx.send(embed=embed, view=SorguPanelView())
    await ctx.message.delete()


# ============================================================
# OTOMATİK CEVAPLAR
# ============================================================
AUTO_REPLIES = [
    (r"\b(sa|selam|selamun aleykum)\b", "Aleyküm selam! 👋 {mention} SantesHub'a hoş geldin!"),
    (r"\bnaber\b", "İyidir, senden naber {mention}? 😄"),
    (r"\b(yardım|yardim)\b", "Yardıma mı ihtiyacın var {mention}? 🎫 Ticket açabilirsin!"),
]
AUTO_REPLY_COOLDOWN = 30
_last_reply_at = {}


# ============================================================
# EVENT'LER
# ============================================================
@bot.event
async def on_ready():
    await bot.wait_until_ready()
    
    update_presence.start()
    
    await send_ticket_panel_automatically()
    await send_contact_panel_automatically()
    
    bot.add_view(TicketPanelView())
    bot.add_view(TicketControlView())
    bot.add_view(ContactFounderView())
    
    log.info(f"✅ {bot.user} olarak giriş yapıldı!")
    log.info(f"📊 {len(bot.guilds)} sunucuda aktif.")


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
            try:
                await message.channel.send(reply.format(mention=message.author.mention))
            except:
                pass

    await bot.process_commands(message)


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


@bot.command(name="sescek")
@commands.check(yetkili_kontrol)
async def sescek_command(ctx, channel_id: int):
    try:
        channel = bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.VoiceChannel):
            await ctx.send("❌ Geçersiz ses kanalı ID'si!")
            return
        
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
            await ctx.send(f"✅ **{channel.name}** kanalına bağlanıldı!")
        else:
            await ctx.send("❌ Önce bir ses kanalında olmalısın!")
    except Exception as e:
        await ctx.send(f"❌ Ses kanalına bağlanılamadı: {e}")


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


@bot.command(name="webhookekle")
@commands.check(yetkili_kontrol)
async def webhookekle_command(ctx, channel_id: int):
    try:
        channel = bot.get_channel(channel_id)
        if not channel:
            await ctx.send("❌ Geçersiz kanal ID'si!")
            return
        
        await channel.create_webhook(name="SantesHub Webhook")
        
        embed = discord.Embed(
            title="✅ Webhook Eklendi",
            description=f"Webhook başarıyla {channel.mention} kanalına eklendi!",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        await ctx.send(embed=embed)
        
        log_embed = discord.Embed(
            title="📨 Webhook Eklendi",
            description=f"{channel.mention} kanalına webhook eklendi",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.add_field(name="Yetkili", value=ctx.author, inline=True)
        await send_log(log_embed)
    except Exception as e:
        await ctx.send(f"❌ Webhook eklenemedi: {e}")


@bot.command(name="rolver")
@commands.check(yetkili_kontrol)
async def rolver_command(ctx, member: discord.Member, role: discord.Role):
    try:
        await member.add_roles(role)
        embed = discord.Embed(
            title="✅ Rol Verildi",
            description=f"{member.mention} kişisine **{role.name}** rolü verildi!",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Yetkili", value=ctx.author.mention, inline=True)
        await ctx.send(embed=embed)
        
        log_embed = discord.Embed(
            title="✅ Rol Verildi",
            description=f"{member} kişisine {role.name} rolü verildi",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.add_field(name="Yetkili", value=ctx.author, inline=True)
        await send_log(log_embed)
    except Exception as e:
        await ctx.send(f"❌ Rol verilemedi: {e}")


@bot.command(name="rolal")
@commands.check(yetkili_kontrol)
async def rolal_command(ctx, member: discord.Member, role: discord.Role):
    try:
        await member.remove_roles(role)
        embed = discord.Embed(
            title="✅ Rol Alındı",
            description=f"{member.mention} kişisinden **{role.name}** rolü alındı!",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Yetkili", value=ctx.author.mention, inline=True)
        await ctx.send(embed=embed)
        
        log_embed = discord.Embed(
            title="✅ Rol Alındı",
            description=f"{member} kişisinden {role.name} rolü alındı",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.add_field(name="Yetkili", value=ctx.author, inline=True)
        await send_log(log_embed)
    except Exception as e:
        await ctx.send(f"❌ Rol alınamadı: {e}")


@bot.command(name="lookup")
@commands.check(yetkili_kontrol)
async def lookup_command(ctx, member: discord.Member):
    embed = discord.Embed(
        title=f"🔍 Kullanıcı Bilgileri",
        description=f"**{member.display_name}** kullanıcısının bilgileri",
        color=member.color if member.color != discord.Color.default() else EMBED_COLOR,
        timestamp=datetime.now(timezone.utc)
    )
    
    embed.set_thumbnail(url=member.display_avatar.url)
    
    embed.add_field(name="👤 Kullanıcı Adı", value=member.name, inline=True)
    embed.add_field(name="📛 Takma Adı", value=member.nick if member.nick else "Yok", inline=True)
    embed.add_field(name="🆔 ID", value=member.id, inline=True)
    
    embed.add_field(
        name="📅 Hesap Oluşturma",
        value=f"<t:{int(member.created_at.timestamp())}:D>\n<t:{int(member.created_at.timestamp())}:R>",
        inline=True
    )
    
    embed.add_field(
        name="📥 Katılım Tarihi",
        value=f"<t:{int(member.joined_at.timestamp())}:D>\n<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "Bilinmiyor",
        inline=True
    )
    
    embed.add_field(name="🟢 Durum", value=str(member.status).title(), inline=True)
    
    aktivite = "Yok"
    if member.activity:
        if member.activity.type == discord.ActivityType.playing:
            aktivite = f"🎮 {member.activity.name}"
        elif member.activity.type == discord.ActivityType.listening:
            aktivite = f"🎵 {member.activity.name}"
        elif member.activity.type == discord.ActivityType.watching:
            aktivite = f"📺 {member.activity.name}"
        elif member.activity.type == discord.ActivityType.streaming:
            aktivite = f"📡 {member.activity.name}"
        else:
            aktivite = member.activity.name
    
    embed.add_field(name="🎯 Aktivite", value=aktivite, inline=True)
    
    roller = [f"{role.mention}" for role in member.roles if role != ctx.guild.default_role]
    if roller:
        embed.add_field(
            name=f"🎭 Roller ({len(roller)})",
            value=" ".join(roller) if len(" ".join(roller)) < 1024 else f"{len(roller)} rol mevcut",
            inline=False
        )
    else:
        embed.add_field(name="🎭 Roller", value="Hiç rolü yok", inline=False)
    
    yetkiler = []
    if member.guild_permissions.administrator:
        yetkiler.append("👑 Yönetici")
    if member.guild_permissions.manage_guild:
        yetkiler.append("⚙️ Sunucu Yönetimi")
    if member.guild_permissions.manage_channels:
        yetkiler.append("📢 Kanal Yönetimi")
    if member.guild_permissions.manage_roles:
        yetkiler.append("🎭 Rol Yönetimi")
    if member.guild_permissions.manage_messages:
        yetkiler.append("💬 Mesaj Yönetimi")
    if member.guild_permissions.kick_members:
        yetkiler.append("👢 Kick")
    if member.guild_permissions.ban_members:
        yetkiler.append("🔨 Ban")
    if member.guild_permissions.mute_members:
        yetkiler.append("🔇 Mute")
    if member.guild_permissions.deafen_members:
        yetkiler.append("🔊 Sağırlaştırma")
    if member.guild_permissions.move_members:
        yetkiler.append("🔀 Üye Taşıma")
    if member.guild_permissions.manage_nicknames:
        yetkiler.append("📛 Takma İsim Yönetimi")
    if member.guild_permissions.manage_webhooks:
        yetkiler.append("🪝 Webhook Yönetimi")
    
    if yetkiler:
        embed.add_field(name="🛡️ Yetkiler", value="\n".join(yetkiler), inline=False)
    else:
        embed.add_field(name="🛡️ Yetkiler", value="Özel bir yetkisi yok", inline=False)
    
    embed.add_field(name="🤖 Bot mu?", value="Evet ✅" if member.bot else "Hayır ❌", inline=True)
    
    if member.premium_since:
        embed.add_field(
            name="💎 Boost Süresi",
            value=f"<t:{int(member.premium_since.timestamp())}:R>",
            inline=True
        )
    
    embed.set_footer(text=f"{SERVER_NAME} • Sadece Yetkililer Görebilir")
    
    await ctx.author.send(embed=embed)
    await ctx.send("✅ Bilgiler DM'ine gönderildi!", delete_after=3)


@bot.command(name="dm")
@commands.check(yetkili_kontrol)
async def dm_command(ctx, hedef: str, *, mesaj: str):
    """Belirtilen kişiye DM gönderir. (ID veya @etiket kullanabilirsin)"""
    try:
        member = None
        
        if hedef.isdigit():
            member = ctx.guild.get_member(int(hedef))
            if not member:
                try:
                    member = await bot.fetch_user(int(hedef))
                except:
                    pass
        
        if not member:
            if hedef.startswith('<@') and hedef.endswith('>'):
                user_id = int(re.sub(r'[<@!>]', '', hedef))
                member = ctx.guild.get_member(user_id)
                if not member:
                    try:
                        member = await bot.fetch_user(user_id)
                    except:
                        pass
            
            if not member:
                for m in ctx.guild.members:
                    if m.name.lower() == hedef.lower() or (m.nick and m.nick.lower() == hedef.lower()):
                        member = m
                        break
        
        if not member:
            await ctx.send("❌ Kullanıcı bulunamadı! Lütfen geçerli bir ID veya @etiket girin.")
            return
        
        await member.send(f"# {mesaj}")
        
        embed = discord.Embed(
            title="✅ DM Gönderildi",
            description=f"{member.mention} ({member.id}) kişisine mesaj gönderildi!",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Mesaj", value=f"```\n{mesaj}\n```", inline=False)
        embed.add_field(name="Gönderen", value=ctx.author.mention, inline=True)
        embed.add_field(name="Hedef ID", value=member.id, inline=True)
        embed.set_footer(text=f"{SERVER_NAME} • DM Sistemi")
        await ctx.send(embed=embed)
        
        log_embed = discord.Embed(
            title="📨 DM Gönderildi",
            description=f"{ctx.author} → {member} ({member.id})",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.add_field(name="Mesaj", value=mesaj[:1000], inline=False)
        await send_log(log_embed)
        
    except discord.Forbidden:
        await ctx.send("❌ Bu kişi DM'lerini kapatmış veya beni engellemiş!")
    except Exception as e:
        await ctx.send(f"❌ DM gönderilemedi: {e}")


@bot.command(name="massdm")
@commands.check(yetkili_kontrol)
async def massdm_command(ctx, *, mesaj: str):
    """Sunucudaki tüm üyelere toplu DM gönderir."""
    
    onay_embed = discord.Embed(
        title="⚠️ Toplu DM Onayı",
        description=f"**{ctx.guild.member_count}** kişiye DM göndermek üzeresin!\n\n"
                    f"Mesaj: ```\n{mesaj}\n```\n\n"
                    "Bu işlem uzun sürebilir. Devam etmek istediğine emin misin?",
        color=discord.Color.orange(),
        timestamp=datetime.now(timezone.utc)
    )
    onay_embed.set_footer(text="10 saniye içinde cevap vermezsen iptal olur.")
    
    onay_mesaji = await ctx.send(embed=onay_embed)
    
    def kontrol(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["evet", "e", "hayir", "h", "iptal"]
    
    try:
        cevap = await bot.wait_for('message', timeout=10.0, check=kontrol)
        if cevap.content.lower() in ["hayir", "h", "iptal"]:
            await ctx.send("❌ Toplu DM iptal edildi!")
            await onay_mesaji.delete()
            await cevap.delete()
            return
    except asyncio.TimeoutError:
        await ctx.send("⏰ Zaman aşımı! Toplu DM iptal edildi.")
        await onay_mesaji.delete()
        return
    
    await cevap.delete()
    await onay_mesaji.delete()
    
    durum_mesaji = await ctx.send("📨 Toplu DM gönderimi başlatılıyor...")
    
    basarili = 0
    basarisiz = 0
    engelleyenler = []
    hatalar = []
    
    for index, member in enumerate(ctx.guild.members, 1):
        if member.bot:
            continue
        
        try:
            await member.send(f"# {mesaj}")
            basarili += 1
            
            if index % 10 == 0:
                await durum_mesaji.edit(content=f"📨 Mesaj gönderiliyor... ({basarili} başarılı, {basarisiz} başarısız)")
            
            await asyncio.sleep(0.5)
            
        except discord.Forbidden:
            basarisiz += 1
            engelleyenler.append(str(member))
        except Exception as e:
            basarisiz += 1
            hatalar.append(f"{member}: {str(e)[:50]}")
        
        if index % 20 == 0:
            await asyncio.sleep(1)
    
    embed = discord.Embed(
        title="📨 Toplu DM Tamamlandı!",
        color=discord.Color.green() if basarili > 0 else discord.Color.red(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="✅ Başarılı", value=f"{basarili} kişi", inline=True)
    embed.add_field(name="❌ Başarısız", value=f"{basarisiz} kişi", inline=True)
    embed.add_field(name="📊 Toplam", value=f"{basarili + basarisiz} kişi", inline=True)
    
    if engelleyenler:
        embed.add_field(
            name="🚫 DM Engelleyenler",
            value=", ".join(engelleyenler[:10]) + (f" ve {len(engelleyenler)-10} daha..." if len(engelleyenler) > 10 else ""),
            inline=False
        )
    
    if hatalar:
        embed.add_field(
            name="⚠️ Hatalar",
            value="\n".join(hatalar[:5]) + (f"\nve {len(hatalar)-5} daha..." if len(hatalar) > 5 else ""),
            inline=False
        )
    
    embed.set_footer(text=f"{SERVER_NAME} • Toplu DM Sistemi")
    
    await durum_mesaji.edit(content="", embed=embed)
    
    log_embed = discord.Embed(
        title="📨 Toplu DM Gönderildi",
        description=f"{ctx.author} tarafından toplu DM gönderildi.",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )
    log_embed.add_field(name="Mesaj", value=mesaj[:1000], inline=False)
    log_embed.add_field(name="✅ Başarılı", value=basarili, inline=True)
    log_embed.add_field(name="❌ Başarısız", value=basarisiz, inline=True)
    await send_log(log_embed)


# ============================================================
# MESAJ / DUYURU KOMUTU (Slash Command ve Prefix)
# ============================================================
@bot.command(name="mesaj")
@commands.check(yetkili_kontrol)
async def mesaj_command(ctx):
    """Bulunduğun kanala webhook ile duyuru gönderir (Modal açar)"""
    await ctx.send("📢 Duyuru oluşturmak için aşağıdaki butona tıkla!", view=DuyuruButtonView(), delete_after=30)
    try:
        await ctx.message.delete()
    except:
        pass


# ============================================================
# LOCK / UNLOCK / NUKE KOMUTLARI
# ============================================================
@bot.command(name="lock")
@commands.check(yetkili_kontrol)
async def lock_command(ctx):
    """Kanaldaki herkese yazma iznini kapatır."""
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
    """Kanaldaki herkese yazma iznini açar."""
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
    """Kanaldaki tüm mesajları siler ve kanalı yeniden oluşturur."""
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


# ============================================================
# GENEL KOMUTLAR
# ============================================================
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


@bot.command(name="yardim")
async def yardim_command(ctx):
    embed = discord.Embed(
        title=f"📚 {SERVER_NAME} Bot Komutları",
        description="**Prefix:** `.`",
        color=EMBED_COLOR
    )
    
    embed.add_field(
        name="👑 Yetkili Komutları",
        value=(
            "`.ban @kişi <sebep>` - Üyeyi banlar\n"
            "`.kick @kişi <sebep>` - Üyeyi kickler\n"
            "`.sescek <ses_id>` - Ses kanalına girer\n"
            "`.mute @kişi <süre> <sebep>` - Üyeyi susturur\n"
            "`.unmute @kişi` - Susturmayı kaldırır\n"
            "`.temizle <sayı>` - Mesajları siler (1-1000)\n"
            "`.ticketpanel` - Ticket panelini gönderir\n"
            "`.kurucupanel` - Kurucu panelini gönderir\n"
            "`.webhookekle <kanal_id>` - Webhook ekler\n"
            "`.rolver @kişi @rol` - Rol verir\n"
            "`.rolal @kişi @rol` - Rol alır\n"
            "`.lookup @kişi` - Kullanıcı bilgilerini DM ile gönderir\n"
            "`.dm <ID/@kişi> <mesaj>` - Kişiye DM gönderir\n"
            "`.massdm <mesaj>` - Herkese toplu DM gönderir\n"
            "`.mesaj` - Bulunduğun kanala duyuru gönderir (Modal açar)\n"
            "`.sorgupanel` - Sorgu panelini açar\n"
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
    
    embed.add_field(
        name="🎫 Ticket Sistemi",
        value=(
            "Destek kanalındaki **📩 Talep Aç** butonuna tıklayarak ticket oluşturabilirsin.\n"
            "Kurucu ile iletişim için **✉️ Mesaj Gönder** butonunu kullanabilirsin."
        ),
        inline=False
    )
    
    embed.set_footer(text=f"{SERVER_NAME} • Yardım Menüsü")
    await ctx.send(embed=embed)


if __name__ == "__main__":
    if not BOT_TOKEN:
        raise SystemExit("❌ BOT_TOKEN ortam değişkeni ayarlanmamış!")
    bot.run(BOT_TOKEN)

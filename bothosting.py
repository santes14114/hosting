import discord
from discord.ext import commands
from discord.ui import View, Button
import requests
import json
import random
import string
import os
from datetime import datetime

# --- BOT AYARLARI ---
TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = 359199132906422273
PANEL_CHANNEL_ID = 1523633754550046760  # Admin panel kanalının ID'si

# --- InfinityFree PHP API Adresi ---
API_URL = 'https://santeshub.great-site.net/api.php'
API_SECRET = 'SANTES_EN_IYI_BABA_VE_ADAMDIR_SECRET_API_KEY'

# Botu oluştur
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# Anahtar oluşturma fonksiyonu
def generate_key():
    chars = string.ascii_uppercase + string.digits
    part1 = ''.join(random.choices(chars, k=6))
    part2 = ''.join(random.choices(chars, k=6))
    return f"SANTES-{part1}-{part2}"

# --- YARDIMCI FONKSİYON: DM ATMA ---
async def send_dm_to_admin(content):
    try:
        admin_user = await bot.fetch_user(ADMIN_ID)
        await admin_user.send(content)
    except:
        pass

# --- BOT HAZIR OLDUĞUNDA ---
@bot.event
async def on_ready():
    print(f"✅ Premium bot giriş yaptı: {bot.user.name}")
    
    # Admin panel kanalına bir hoş geldin mesajı at
    channel = bot.get_channel(PANEL_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title="🛠️ Santes Hub Bot Aktif!",
            description="Aşağıdaki komutu kullanarak yeni anahtarlar oluşturabilirsin.\n\n`/key KullanıcıAdı 1gün`",
            color=0xff2a43
        )
        embed.set_footer(text="Santes Hub Premium Bot v3.0")
        await channel.send(embed=embed)

# --- ANA KOMUT: KEY OLUŞTUR ---
@bot.command()
async def key(ctx, username: str = None, duration: str = None):
    
    # Kullanıcı sadece /key yazarsa yardım mesajı göster
    if username is None or duration is None:
        embed = discord.Embed(
            title="❌ Eksik Bilgi",
            description="**Doğru kullanım:** `/key KullanıcıAdı 1gün`\n\n**Süre seçenekleri:** `1gün`, `1hafta`, `1ay`, `1yıl`",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return

    # Süre kontrolü
    allowed = ['1gün', '1hafta', '1ay', '1yıl']
    if duration not in allowed:
        embed = discord.Embed(
            title="❌ Geçersiz Süre",
            description=f"Lütfen şu sürelerden birini kullan: `{', '.join(allowed)}`",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return

    # Anahtar oluştur
    new_key = generate_key()
    
    # InfinityFree API'sine gönder
    payload = {
        "api_key": API_SECRET,
        "action": "create_key",
        "username": username,
        "duration": duration,
        "key": new_key
    }
    
    try:
        response = requests.post(API_URL, json=payload)
        data = response.json()
        
        if data.get('status') == 'success':
            
            # --- 1. KANALA (PUBLİK) BAŞARI MESAJI AT ---
            embed_public = discord.Embed(
                title="✅ Yeni Anahtar Oluşturuldu!",
                description=(
                    f"👤 **Kullanıcı:** {username}\n"
                    f"⏳ **Süre:** {duration}\n"
                    f"🔑 **Anahtar:** `{new_key}`"
                ),
                color=0x00ff00
            )
            embed_public.set_footer(text="Santes Hub Premium Bot")
            await ctx.send(embed=embed_public)
            
            # --- 2. ÖZEL BOT KANALINA (ADMIN PANEL) DETAYLI MESAJ AT ---
            admin_channel = bot.get_channel(PANEL_CHANNEL_ID)
            if admin_channel:
                embed_admin = discord.Embed(
                    title="🔐 **YENİ ANAHTAR OLUŞTURULDU (ADMIN)**",
                    description=(
                        f"📌 **Kullanıcı Adı:** {username}\n"
                        f"⏳ **Süre:** {duration}\n"
                        f"🔑 **Anahtar:** `{new_key}`\n"
                        f"📅 **Oluşturulma:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    ),
                    color=0xff2a43
                )
                embed_admin.set_footer(text="Admin Paneli")
                await admin_channel.send(embed=embed_admin)

            # --- 3. ADMİNE (SANA) DM GÖNDER ---
            await send_dm_to_admin(
                f"🔐 **Yeni anahtar oluşturuldu ve siteye kaydedildi!**\n\n"
                f"👤 Kullanıcı: {username}\n"
                f"⏳ Süre: {duration}\n"
                f"🔑 Anahtar: `{new_key}`\n\n"
                f"📌 Bu anahtarı kullanıcıya iletmeyi unutma."
            )
            
        else:
            # API hatası
            embed = discord.Embed(
                title="❌ API Hatası",
                description=f"Site hatası: {data.get('message', 'Bilinmeyen hata')}",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            
    except Exception as e:
        # Bağlantı hatası
        embed = discord.Embed(
            title="❌ Bağlantı Hatası",
            description=f"Discord botu siteye bağlanamıyor! Hata: {str(e)}",
            color=0xff0000
        )
        await ctx.send(embed=embed)

# Botu başlat
bot.run(TOKEN)

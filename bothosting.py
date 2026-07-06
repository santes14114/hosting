import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import requests
import json
import random
import string
import os
from datetime import datetime

# --- BOT AYARLARI ---
TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = 359199132906422273
PANEL_CHANNEL_ID = 1523633754550046760

# --- InfinityFree PHP API Adresi ---
API_URL = 'https://santeshub.great-site.net/api.php'
API_SECRET = 'SANTES_EN_IYI_BABA_VE_ADAMDIR_SECRET_API_KEY'

# Botu oluştur
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# --- YARDIMCI FONKSİYONLAR ---
def generate_key():
    chars = string.ascii_uppercase + string.digits
    part1 = ''.join(random.choices(chars, k=6))
    part2 = ''.join(random.choices(chars, k=6))
    return f"SANTES-{part1}-{part2}"

async def send_dm_to_admin(username, duration, new_key):
    try:
        admin_user = await bot.fetch_user(ADMIN_ID)
        embed = discord.Embed(
            title="🔐 **YENİ ANAHTAR OLUŞTURULDU!**",
            description=(
                f"👤 **Kullanıcı:** {username}\n"
                f"⏳ **Süre:** {duration}\n"
                f"🔑 **Anahtar:** `{new_key}`"
            ),
            color=0xff2a43
        )
        embed.set_footer(text="Bu anahtarı kullanıcıya iletmeyi unutma.")
        await admin_user.send(embed=embed)
    except:
        pass

# ============================================================
# MODAL (Key Oluşturma Formu) - ESKİ HALİ
# ============================================================
class KeyCreateModal(Modal):
    def __init__(self):
        super().__init__(title="🔐 Yeni Anahtar Oluştur")
        
        self.username_input = TextInput(
            label="👤 Kullanıcı Adı",
            placeholder="Örn: SantesKullanici",
            min_length=3,
            max_length=30
        )
        self.duration_input = TextInput(
            label="⏳ Süre (1gün, 1hafta, 1ay, 1yıl)",
            placeholder="Örn: 1ay"
        )
        self.add_item(self.username_input)
        self.add_item(self.duration_input)

    async def on_submit(self, interaction: discord.Interaction):
        username = self.username_input.value
        duration = self.duration_input.value.lower().strip()

        # Süre kontrolü
        allowed = ['1gün', '1hafta', '1ay', '1yıl']
        if duration not in allowed:
            embed = discord.Embed(
                title="❌ Geçersiz Süre",
                description=f"Lütfen şunlardan birini yaz: `{', '.join(allowed)}`",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
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
                
                # Admin'e DM at
                await send_dm_to_admin(username, duration, new_key)

                # Kullanıcıya başarılı mesaj
                embed = discord.Embed(
                    title="✅ Anahtar Oluşturuldu!",
                    description=(
                        f"👤 **Kullanıcı:** {username}\n"
                        f"⏳ **Süre:** {duration}\n"
                        f"🔑 **Anahtar:** `{new_key}`"
                    ),
                    color=0x00ff00
                )
                embed.set_footer(text="Anahtar DM'den admin'e iletildi.")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
            else:
                embed = discord.Embed(
                    title="❌ API Hatası",
                    description=f"Sunucu hatası: {data.get('message', 'Bilinmeyen hata')}",
                    color=0xff0000
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except:
            embed = discord.Embed(
                title="❌ Bağlantı Hatası",
                description="Bot, InfinityFree API'sine bağlanamadı!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

# ============================================================
# PANEL BUTONLARI (ESKİ HALİ)
# ============================================================
class PanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔐 Key Oluştur", style=discord.ButtonStyle.success, custom_id="btn_create")
    async def create_key(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(KeyCreateModal())

# ============================================================
# BOT HAZIR OLDUĞUNDA PANELİ KANALA AT
# ============================================================
@bot.event
async def on_ready():
    print(f"✅ Premium butonlu bot giriş yaptı: {bot.user.name}")
    
    channel = bot.get_channel(PANEL_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title="🛠️ **Santes Hub Yönetim Paneli**",
            description=(
                "Aşağıdaki butonu kullanarak anahtar oluşturabilirsin.\n\n"
                "🔐 **Key Oluştur:** Yeni bir lisans anahtarı oluşturur ve sana DM'den gönderir."
            ),
            color=0xff2a43
        )
        embed.set_footer(text="Santes Hub Premium Bot v3.0")
        
        # Mesajı ve butonları kanala gönder
        await channel.send(embed=embed, view=PanelView())

# ============================================================
# BOTU BAŞLAT
# ============================================================
bot.run(TOKEN)

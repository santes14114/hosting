"""
============================================================
SANTES HUB - DISCORD BOTU (PREMIUM VERSION - FULL)
Bu bot, yönetim paneli için butonlar, modal formlar,
anahtar listeleme ve silme özelliklerini içerir.
============================================================
"""

import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import requests
import json
import random
import string
import os
from datetime import datetime, timedelta

# ----------------------------------------------------------------
# 1. BOT AYARLARI VE DEĞİŞKENLER
# ----------------------------------------------------------------

# Discord Bot Tokeni (Railway Environment Variable'dan alınır)
TOKEN = os.getenv('BOT_TOKEN')

# Admin ve Kanal ID'leri (Hardcoded)
ADMIN_ID = 359199132906422273
PANEL_CHANNEL_ID = 1523633754550046760

# InfinityFree PHP API Adresi
API_URL = 'https://santeshub.great-site.net/api.php'
API_SECRET = 'SANTES_EN_IYI_BABA_VE_ADAMDIR_SECRET_API_KEY'

# Botu oluştur
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# ----------------------------------------------------------------
# 2. YARDIMCI FONKSİYONLAR
# ----------------------------------------------------------------

def generate_key():
    """Rastgele 16 haneli bir SANTES anahtarı oluşturur."""
    chars = string.ascii_uppercase + string.digits
    part1 = ''.join(random.choices(chars, k=6))
    part2 = ''.join(random.choices(chars, k=6))
    return f"SANTES-{part1}-{part2}"

def calculate_duration(duration_str):
    """Verilen süreye göre bitiş tarihini hesaplar (Yerel hesaplama, API'ye gerek yok)."""
    now = datetime.now()
    if duration_str == '1gün':
        return now + timedelta(days=1)
    elif duration_str == '1hafta':
        return now + timedelta(weeks=1)
    elif duration_str == '1ay':
        return now + timedelta(days=30)
    elif duration_str == '1yıl':
        return now + timedelta(days=365)
    return now + timedelta(days=1)

def days_left(expiry_date_str):
    """Kalan gün ve saati hesaplar (Süslü format)."""
    try:
        expiry = datetime.strptime(expiry_date_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        delta = expiry - now
        if delta.total_seconds() <= 0:
            return "⛔ **Süresi Doldu**"
        days = delta.days
        hours = delta.seconds // 3600
        if days > 0:
            return f"📅 **{days} gün {hours} saat**"
        else:
            return f"⏰ **{hours} saat**"
    except:
        return "❓ **Hesaplanamıyor**"

async def send_dm_to_admin(username, duration, new_key):
    """Admin'e özel mesaj (DM) gönderir."""
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

# ----------------------------------------------------------------
# 3. MODAL: KEY OLUŞTURMA FORMU
# ----------------------------------------------------------------
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

        # Yeni anahtar oluştur
        new_key = generate_key()
        
        # ----------------------------------------------------------------
        # API'YE VERİ GÖNDER (InfinityFree) - Timeout ve User-Agent eklendi
        # ----------------------------------------------------------------
        payload = {
            "api_key": API_SECRET,
            "action": "create_key",
            "username": username,
            "duration": duration,
            "key": new_key
        }
        
        try:
            # Timeout ve User-Agent ekleyerek bağlantı hatasını önledik
            headers = {
                'User-Agent': 'SantesHub-Bot/3.0',
                'Content-Type': 'application/json'
            }
            response = requests.post(API_URL, json=payload, headers=headers, timeout=10)
            data = response.json()
            
            if data.get('status') == 'success':
                
                # 1. Admin'e DM gönder
                await send_dm_to_admin(username, duration, new_key)

                # 2. Kullanıcıya başarılı mesaj göster
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
                
        except requests.exceptions.Timeout:
            embed = discord.Embed(
                title="❌ Zaman Aşımı Hatası",
                description="InfinityFree sunucusu yanıt vermiyor. Lütfen birkaç saniye sonra tekrar deneyin.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except requests.exceptions.ConnectionError as e:
            embed = discord.Embed(
                title="❌ Bağlantı Kesildi",
                description="InfinityFree ile bağlantı kurulamadı. (Sunucu botu bloklamış olabilir).",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

# ----------------------------------------------------------------
# 4. KEY KONTROL PANELİ (Listeleme ve Silme Modalı)
# ----------------------------------------------------------------

# Silme Onay Butonları
class ConfirmDeleteView(View):
    def __init__(self, key_to_delete):
        super().__init__(timeout=60)
        self.key_to_delete = key_to_delete

    @discord.ui.button(label="✅ Evet, Sil", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        # Bot API'ye silme isteği gönderir
        payload = {
            "api_key": API_SECRET,
            "action": "delete_key",
            "key": self.key_to_delete
        }
        try:
            response = requests.post(API_URL, json=payload, timeout=10)
            data = response.json()
            if data.get('status') == 'success':
                embed = discord.Embed(
                    title="🗑️ Anahtar Silindi!",
                    description=f"**`{self.key_to_delete}`** anahtarı başarıyla silindi.",
                    color=0x00ff00
                )
                await interaction.response.edit_message(embed=embed, view=None)
            else:
                embed = discord.Embed(
                    title="❌ Silme Hatası",
                    description=data.get('message', 'Bilinmeyen hata'),
                    color=0xff0000
                )
                await interaction.response.edit_message(embed=embed, view=None)
        except:
            embed = discord.Embed(title="❌ Bağlantı Hatası", description="Silme işlemi sırasında hata oluştu.", color=0xff0000)
            await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="❌ İptal", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(title="❌ Silme İşlemi İptal Edildi", description="Hiçbir anahtar silinmedi.", color=0xff2a43)
        await interaction.response.edit_message(embed=embed, view=None)

# Silme Modalı
class KeyDeleteModal(Modal):
    def __init__(self):
        super().__init__(title="🗑️ Anahtar Sil")
        self.key_input = TextInput(label="Silmek istediğin anahtarı yaz", placeholder="SANTES-XXXXXX-YYYYYY")
        self.add_item(self.key_input)

    async def on_submit(self, interaction: discord.Interaction):
        key_to_delete = self.key_input.value.strip()
        embed = discord.Embed(
            title="⚠️ **Silme Onayı**",
            description=f"**`{key_to_delete}`** anahtarını silmek istediğinize emin misiniz?\n\n⚠️ **Bu işlem geri alınamaz!**",
            color=0xff2a43
        )
        await interaction.response.send_message(embed=embed, view=ConfirmDeleteView(key_to_delete), ephemeral=True)

# ----------------------------------------------------------------
# 5. PANEL BUTONLARI (ANA PANEL)
# ----------------------------------------------------------------
class PanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔐 Key Oluştur", style=discord.ButtonStyle.success, custom_id="btn_create")
    async def create_key(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(KeyCreateModal())

    @discord.ui.button(label="📋 Key Kontrol Paneli", style=discord.ButtonStyle.primary, custom_id="btn_list")
    async def list_keys(self, interaction: discord.Interaction, button: Button):
        # API'den anahtarları çek
        try:
            response = requests.get(f"{API_URL}?action=list_keys&api_key={API_SECRET}", timeout=10)
            data = response.json()
            keys = data.get('keys', [])
            
            if not keys:
                embed = discord.Embed(title="📋 Key Kontrol Paneli", description="📭 **Henüz hiç anahtar oluşturulmamış.**", color=0xff2a43)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            embed = discord.Embed(title="📋 **Key Kontrol Paneli**", description=f"**Toplam {len(keys)} anahtar bulundu.**", color=0xff2a43)
            
            for k in keys[:10]:
                remaining = days_left(k['expires_at'])
                embed.add_field(
                    name=f"🔑 **{k['username']}**",
                    value=f"`{k['key']}`\n⏳ **Kalan:** {remaining}\n📅 **Bitiş:** {k['expires_at']}",
                    inline=False
                )
            if len(keys) > 10:
                embed.set_footer(text=f"ve {len(keys) - 10} anahtar daha...")
            await interaction.response.send_message(embed=embed, view=KeyControlView(), ephemeral=True)
            
        except:
            embed = discord.Embed(title="❌ Bağlantı Hatası", description="Anahtar listesi alınamadı.", color=0xff0000)
            await interaction.response.send_message(embed=embed, ephemeral=True)

# ----------------------------------------------------------------
# 6. KEY KONTROL PANELİ (Yenile ve Sil Butonları)
# ----------------------------------------------------------------
class KeyControlView(View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="🔄 Yenile", style=discord.ButtonStyle.secondary, custom_id="btn_refresh")
    async def refresh(self, interaction: discord.Interaction, button: Button):
        # Aynı listeleme kodunu tekrar çalıştır
        try:
            response = requests.get(f"{API_URL}?action=list_keys&api_key={API_SECRET}", timeout=10)
            data = response.json()
            keys = data.get('keys', [])
            
            embed = discord.Embed(title="📋 **Key Kontrol Paneli (Yenilendi)**", description=f"**Toplam {len(keys)} anahtar bulundu.**", color=0xff2a43)
            for k in keys[:10]:
                remaining = days_left(k['expires_at'])
                embed.add_field(
                    name=f"🔑 **{k['username']}**",
                    value=f"`{k['key']}`\n⏳ **Kalan:** {remaining}\n📅 **Bitiş:** {k['expires_at']}",
                    inline=False
                )
            if len(keys) > 10:
                embed.set_footer(text=f"ve {len(keys) - 10} anahtar daha...")
            await interaction.response.edit_message(embed=embed, view=KeyControlView())
        except:
            embed = discord.Embed(title="❌ Bağlantı Hatası", description="Liste yenilenemedi.", color=0xff0000)
            await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="🗑️ Anahtar Sil", style=discord.ButtonStyle.danger, custom_id="btn_delete")
    async def delete_key(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(KeyDeleteModal())

# ----------------------------------------------------------------
# 7. BOT HAZIR OLDUĞUNDA PANELİ KANALA AT
# ----------------------------------------------------------------
@bot.event
async def on_ready():
    print(f"✅ Premium butonlu bot giriş yaptı: {bot.user.name}")
    
    channel = bot.get_channel(PANEL_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title="🛠️ **Santes Hub Yönetim Paneli**",
            description=(
                "Aşağıdaki butonları kullanarak anahtar oluşturabilir veya kontrol edebilirsin.\n\n"
                "🔐 **Key Oluştur:** Yeni bir lisans anahtarı oluşturur ve sana DM'den gönderir.\n\n"
                "📋 **Key Kontrol Paneli:** Tüm anahtarları listeler, kalan sürelerini gösterir ve silme imkanı verir."
            ),
            color=0xff2a43
        )
        embed.set_footer(text="Santes Hub Premium Bot v3.0")
        
        await channel.send(embed=embed, view=PanelView())

# ----------------------------------------------------------------
# 8. BOTU BAŞLAT
# ----------------------------------------------------------------
bot.run(TOKEN)

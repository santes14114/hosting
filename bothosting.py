"""
============================================================
SANTES HUB - DISCORD BOTU (FULL VERSION)
Bu bot, admin komutlarıyla anahtar oluşturur.
Site API'sine JSON olarak gönderir.
============================================================
"""

import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import requests
import json
import random
import string
from datetime import datetime, timedelta
import os

# --- TÜRKİYE ZAMAN DİLİMİ ---
os.environ['TZ'] = 'Europe/Istanbul'
try:
    from time import tzset
    tzset()
except:
    pass

# --- BOT AYARLARI (Hardcoded) ---
TOKEN = os.getenv('BOT_TOKEN')  # Railway'den alınır

ADMIN_ID = 359199132906422273
PANEL_CHANNEL_ID = 1523633754550046760
API_URL = 'https://santeshub.great-site.net/api.php'
API_SECRET = 'SANTES_EN_IYI_BABA_VE_ADAMDIR_SECRET_API_KEY'

# Botu oluştur
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# Veri dosyası yolu (Yedek için)
DATA_FILE = 'keys_data.json'

# ============================================================
# YARDIMCI FONKSİYONLAR
# ============================================================

def generate_key():
    """Rastgele 16 haneli bir SANTES anahtarı oluşturur."""
    chars = string.ascii_uppercase + string.digits
    part1 = ''.join(random.choices(chars, k=6))
    part2 = ''.join(random.choices(chars, k=6))
    return f"SANTES-{part1}-{part2}"

def calculate_duration(duration_str):
    """Verilen süreye göre bitiş tarihini hesaplar."""
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
    """Kalan gün ve saati hesaplar."""
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

def load_keys():
    """Yerel JSON dosyasından anahtarları okur."""
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, 'r') as f:
        try:
            return json.load(f)
        except:
            return []

def save_keys(keys):
    """Anahtarları yerel JSON dosyasına yazar."""
    with open(DATA_FILE, 'w') as f:
        json.dump(keys, f, indent=4)

def send_key_to_api(key_data):
    """Oluşturulan anahtarı site API'sine gönderir."""
    try:
        payload = {
            "api_key": API_SECRET,
            "action": "create_key",
            "username": key_data['username'],
            "duration": key_data['duration'],
            "key": key_data['key']
        }
        response = requests.post(API_URL, json=payload)
        return response.json()
    except Exception as e:
        return {"status": "error", "message": f"API bağlantı hatası: {str(e)}"}

# ============================================================
# HATA MESAJI
# ============================================================
async def send_error(interaction, message):
    embed = discord.Embed(
        title="❌ **Hata!**",
        description=f"**{message}**",
        color=0xff0000
    )
    embed.set_footer(text="Santes Hub Bot | Lütfen tekrar deneyin.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ============================================================
# MODAL: Key Oluşturma Formu
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
            await send_error(interaction, f"Süre sadece şunlar olabilir:\n**`{', '.join(allowed)}`**")
            return

        # Anahtar oluştur
        new_key = generate_key()
        expiry_date = calculate_duration(duration)
        expiry_str = expiry_date.strftime("%Y-%m-%d %H:%M:%S")

        # Yerel veriye kaydet
        keys = load_keys()
        key_data = {
            'key': new_key,
            'username': username,
            'duration': duration,
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'expires_at': expiry_str
        }
        keys.append(key_data)
        save_keys(keys)

        # Site API'sine gönder
        api_response = send_key_to_api(key_data)

        # Admin'e DM at
        try:
            admin_user = await bot.fetch_user(ADMIN_ID)
            embed = discord.Embed(
                title="🔐 **YENİ ANAHTAR OLUŞTURULDU!**",
                description=(
                    f"👤 **Kullanıcı:** {username}\n\n"
                    f"⏳ **Süre:** {duration}\n\n"
                    f"📅 **Bitiş:** {expiry_str}\n\n"
                    f"🔑 **Anahtar:** `{new_key}`"
                ),
                color=0xff2a43
            )
            embed.set_footer(text="Bu anahtarı kullanıcıya iletmeyi unutma.")
            await admin_user.send(embed=embed)
        except Exception as e:
            pass

        # Kullanıcıya geri bildirim
        embed = discord.Embed(
            title="✅ **Anahtar Başarıyla Oluşturuldu!**",
            description=(
                f"👤 **Kullanıcı:** {username}\n\n"
                f"⏳ **Süre:** {duration}\n\n"
                f"🔑 **Anahtar:** `{new_key}`"
            ),
            color=0x00ff00
        )
        embed.set_footer(text="Anahtar DM'den admin'e iletildi.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ============================================================
# ANAHTAR SİLME ONAY BUTONLARI
# ============================================================
class ConfirmDeleteView(View):
    def __init__(self, key_to_delete):
        super().__init__(timeout=60)
        self.key_to_delete = key_to_delete

    @discord.ui.button(label="✅ Evet, Sil", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        keys = load_keys()
        new_keys = [k for k in keys if k['key'] != self.key_to_delete]
        
        if len(new_keys) < len(keys):
            save_keys(new_keys)
            embed = discord.Embed(
                title="🗑️ **Anahtar Silindi!**",
                description=f"**`{self.key_to_delete}`** anahtarı başarıyla silindi.",
                color=0x00ff00
            )
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            await send_error(interaction, "Anahtar bulunamadı veya zaten silinmiş.")

    @discord.ui.button(label="❌ İptal", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="❌ **Silme İşlemi İptal Edildi**",
            description="Hiçbir anahtar silinmedi.",
            color=0xff2a43
        )
        await interaction.response.edit_message(embed=embed, view=None)

# ============================================================
# ANA PANEL BUTONLARI
# ============================================================
class PanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔐 Key Oluştur", style=discord.ButtonStyle.success, custom_id="btn_create")
    async def create_key(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(KeyCreateModal())

    @discord.ui.button(label="📋 Key Kontrol Paneli", style=discord.ButtonStyle.primary, custom_id="btn_list")
    async def list_keys(self, interaction: discord.Interaction, button: Button):
        keys = load_keys()
        
        if not keys:
            embed = discord.Embed(
                title="📋 **Key Kontrol Paneli**",
                description="📭 **Henüz hiç anahtar oluşturulmamış.**",
                color=0xff2a43
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="📋 **Key Kontrol Paneli**",
            description=f"**Toplam {len(keys)} anahtar bulundu.**",
            color=0xff2a43
        )
        
        for i, k in enumerate(keys[:10]):
            remaining = days_left(k['expires_at'])
            embed.add_field(
                name=f"🔑 **{k['username']}**",
                value=(
                    f"`{k['key']}`\n\n"
                    f"⏳ **Kalan:** {remaining}\n\n"
                    f"📅 **Bitiş:** {k['expires_at']}"
                ),
                inline=False
            )
        
        if len(keys) > 10:
            embed.set_footer(text=f"ve {len(keys) - 10} anahtar daha...")

        await interaction.response.send_message(embed=embed, view=KeyControlView(), ephemeral=True)

# ============================================================
# KEY KONTROL PANELİ
# ============================================================
class KeyControlView(View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="🔄 Yenile", style=discord.ButtonStyle.secondary, custom_id="btn_refresh")
    async def refresh(self, interaction: discord.Interaction, button: Button):
        keys = load_keys()
        embed = discord.Embed(
            title="📋 **Key Kontrol Paneli (Yenilendi)**",
            description=f"**Toplam {len(keys)} anahtar bulundu.**",
            color=0xff2a43
        )
        for i, k in enumerate(keys[:10]):
            remaining = days_left(k['expires_at'])
            embed.add_field(
                name=f"🔑 **{k['username']}**",
                value=(
                    f"`{k['key']}`\n\n"
                    f"⏳ **Kalan:** {remaining}\n\n"
                    f"📅 **Bitiş:** {k['expires_at']}"
                ),
                inline=False
            )
        if len(keys) > 10:
            embed.set_footer(text=f"ve {len(keys) - 10} anahtar daha...")
        await interaction.response.edit_message(embed=embed, view=KeyControlView())

    @discord.ui.button(label="🗑️ Anahtar Sil", style=discord.ButtonStyle.danger, custom_id="btn_delete")
    async def delete_key(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(KeyDeleteModal())

# ============================================================
# ANAHTAR SİLME MODALI
# ============================================================
class KeyDeleteModal(Modal):
    def __init__(self):
        super().__init__(title="🗑️ Anahtar Sil")
        self.key_input = TextInput(
            label="Silmek istediğin anahtarı yaz",
            placeholder="SANTES-XXXXXX-YYYYYY"
        )
        self.add_item(self.key_input)

    async def on_submit(self, interaction: discord.Interaction):
        key_to_delete = self.key_input.value.strip()
        
        embed = discord.Embed(
            title="⚠️ **Silme Onayı**",
            description=(
                f"**`{key_to_delete}`** anahtarını silmek istediğinize emin misiniz?\n\n"
                f"⚠️ **Bu işlem geri alınamaz!**"
            ),
            color=0xff2a43
        )
        await interaction.response.send_message(embed=embed, view=ConfirmDeleteView(key_to_delete), ephemeral=True)

# ============================================================
# BOT AYAKLANMA VE PANEL GÖNDERME
# ============================================================
@bot.event
async def on_ready():
    print(f"✅ Bot giriş yaptı: {bot.user.name}")
    
    channel = bot.get_channel(PANEL_CHANNEL_ID)
    if channel is None:
        print(f"❌ Kanal bulunamadı! ID: {PANEL_CHANNEL_ID}")
        return

    embed = discord.Embed(
        title="🛠️ **Santes Hub Yönetim Paneli**",
        description=(
            "Aşağıdaki butonları kullanarak anahtar oluşturabilir veya mevcut anahtarları kontrol edebilirsin.\n\n"
            "🔐 **Key Oluştur:** Yeni bir lisans anahtarı oluşturur ve sana DM'den gönderir.\n\n"
            "📋 **Key Kontrol Paneli:** Tüm anahtarları listeler, kalan sürelerini gösterir ve silme imkanı verir."
        ),
        color=0xff2a43
    )
    embed.set_footer(text="Santes Hub Bot v3.0 | Tüm hakları saklıdır.")

    await channel.send(embed=embed, view=PanelView())

# ============================================================
# BOTU BAŞLAT
# ============================================================
bot.run(TOKEN)

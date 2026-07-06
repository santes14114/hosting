import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput
import requests
import json
import random
import string
from datetime import datetime, timedelta
import os

# --- BOT AYARLARI ---
TOKEN = os.getenv('BOT_TOKEN')  # Discord Developer Portal'dan al
ADMIN_ID = 359199132906422273  # Senin Discord ID'n

# --- SİTE API AYARLARI ---
API_URL = 'https://santeshub.great-site.net/api.php'
API_SECRET = 'SANTES_EN_IYI_BABA_VE_ADAMDIR_SECRET_API_KEY'

# --- KANAL AYARI ---
PANEL_CHANNEL_ID = 1523633754550046760  # Botun paneli yollayacağı kanal ID'si

# Botu oluştur
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# Veri dosyası yolu (Txt dosyası)
DATA_FILE = 'keys_data.json'

# Anahtar oluşturma
def generate_key():
    chars = string.ascii_uppercase + string.digits
    part1 = ''.join(random.choices(chars, k=6))
    part2 = ''.join(random.choices(chars, k=6))
    return f"SANTES-{part1}-{part2}"

# Tarih hesaplama
def calculate_duration(duration_str):
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

# Kalan gün hesaplama
def days_left(expiry_date_str):
    try:
        expiry = datetime.strptime(expiry_date_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        delta = expiry - now
        if delta.total_seconds() <= 0:
            return "Süresi Doldu ❌"
        return f"{delta.days} gün {delta.seconds // 3600} saat"
    except:
        return "Hesaplanamıyor"

# Veri dosyasını oku
def load_keys():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, 'r') as f:
        try:
            return json.load(f)
        except:
            return []

# Veri dosyasına yaz
def save_keys(keys):
    with open(DATA_FILE, 'w') as f:
        json.dump(keys, f, indent=4)

# API'ye anahtar gönder
def send_key_to_api(key_data):
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
    except:
        return {"status": "error", "message": "API bağlantı hatası!"}

# ============================================================
# MODAL (Key Oluşturma Formu)
# ============================================================
class KeyCreateModal(Modal):
    def __init__(self):
        super().__init__(title="🔐 Yeni Anahtar Oluştur")
        
        self.username_input = TextInput(
            label="Kullanıcı Adı",
            placeholder="Örn: SantesKullanici",
            min_length=3,
            max_length=30
        )
        self.duration_input = TextInput(
            label="Süre (1gün, 1hafta, 1ay, 1yıl)",
            placeholder="1ay",
            min_length=4,
            max_length=6
        )
        self.add_item(self.username_input)
        self.add_item(self.duration_input)

    async def on_submit(self, interaction: discord.Interaction):
        username = self.username_input.value
        duration = self.duration_input.value.lower()

        # Süre kontrolü
        allowed = ['1gün', '1hafta', '1ay', '1yıl']
        if duration not in allowed:
            await interaction.response.send_message(f"❌ Süre sadece şunlar olabilir: {', '.join(allowed)}", ephemeral=True)
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

        # API'ye gönder (Site için)
        api_response = send_key_to_api(key_data)

        # Admin'e DM at
        try:
            admin_user = await bot.fetch_user(ADMIN_ID)
            embed = discord.Embed(
                title="🔐 YENİ ANAHTAR OLUŞTURULDU!",
                description=f"👤 **Kullanıcı:** {username}\n⏳ **Süre:** {duration}\n📅 **Bitiş:** {expiry_str}\n🔑 **Anahtar:** `{new_key}`",
                color=0xff2a43
            )
            embed.set_footer(text="Bu anahtarı kullanıcıya iletmeyi unutma.")
            await admin_user.send(embed=embed)
        except:
            pass

        # Kullanıcıya geri bildirim
        embed = discord.Embed(
            title="✅ Anahtar Oluşturuldu!",
            description=f"**Kullanıcı:** {username}\n**Süre:** {duration}\n**Anahtar:** `{new_key}`",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ============================================================
# BUTONLAR
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
                title="📋 Key Kontrol Paneli",
                description="📭 Henüz hiç anahtar oluşturulmamış.",
                color=0xff2a43
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Anahtarları listele (Her key için ayrı embed veya tek embed)
        embed = discord.Embed(
            title="📋 Key Kontrol Paneli",
            description=f"Toplam **{len(keys)}** anahtar bulundu.",
            color=0xff2a43
        )
        
        for i, k in enumerate(keys[:10]):  # İlk 10 tanesini göster (çok fazlaysa mesaj sınırı)
            remaining = days_left(k['expires_at'])
            embed.add_field(
                name=f"🔑 {k['username']}",
                value=f"`{k['key']}`\n⏳ **Kalan:** {remaining}\n📅 **Bitiş:** {k['expires_at']}",
                inline=False
            )
        
        if len(keys) > 10:
            embed.set_footer(text=f"ve {len(keys) - 10} anahtar daha...")

        await interaction.response.send_message(embed=embed, view=KeyControlView(), ephemeral=True)

# ============================================================
# KEY KONTROL PANELİ (Silme Butonları)
# ============================================================
class KeyControlView(View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="🔄 Yenile", style=discord.ButtonStyle.secondary, custom_id="btn_refresh")
    async def refresh(self, interaction: discord.Interaction, button: Button):
        keys = load_keys()
        embed = discord.Embed(
            title="📋 Key Kontrol Paneli (Yenilendi)",
            description=f"Toplam **{len(keys)}** anahtar bulundu.",
            color=0xff2a43
        )
        for i, k in enumerate(keys[:10]):
            remaining = days_left(k['expires_at'])
            embed.add_field(
                name=f"🔑 {k['username']}",
                value=f"`{k['key']}`\n⏳ **Kalan:** {remaining}\n📅 **Bitiş:** {k['expires_at']}",
                inline=False
            )
        if len(keys) > 10:
            embed.set_footer(text=f"ve {len(keys) - 10} anahtar daha...")
        await interaction.response.edit_message(embed=embed, view=KeyControlView())

    @discord.ui.button(label="🗑️ Anahtar Sil", style=discord.ButtonStyle.danger, custom_id="btn_delete")
    async def delete_key(self, interaction: discord.Interaction, button: Button):
        # Silme işlemi için bir modal aç
        await interaction.response.send_modal(KeyDeleteModal())

# ============================================================
# ANAHTAR SİLME MODALI
# ============================================================
class KeyDeleteModal(Modal):
    def __init__(self):
        super().__init__(title="🗑️ Anahtar Sil")
        self.key_input = TextInput(
            label="Silmek istediğin anahtarı yaz",
            placeholder="SANTES-XXXXXX-YYYYYY",
            min_length=15,
            max_length=25
        )
        self.add_item(self.key_input)

    async def on_submit(self, interaction: discord.Interaction):
        key_to_delete = self.key_input.value.strip()
        keys = load_keys()
        
        found = False
        new_keys = []
        for k in keys:
            if k['key'] == key_to_delete:
                found = True
            else:
                new_keys.append(k)
        
        if found:
            save_keys(new_keys)
            await interaction.response.send_message(f"✅ Anahtar `{key_to_delete}` başarıyla silindi.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ `{key_to_delete}` anahtarı bulunamadı.", ephemeral=True)

# ============================================================
# BOT AYAKLANMA VE PANEL GÖNDERME
# ============================================================
@bot.event
async def on_ready():
    print(f"✅ Bot giriş yaptı: {bot.user.name}")
    
    # Panel kanalını bul
    channel = bot.get_channel(PANEL_CHANNEL_ID)
    if channel is None:
        print(f"❌ Kanal bulunamadı! ID: {PANEL_CHANNEL_ID}")
        return

    # Embed mesaj oluştur
    embed = discord.Embed(
        title="🛠️ Santes Hub Yönetim Paneli",
        description="Aşağıdaki butonları kullanarak anahtar oluşturabilir veya mevcut anahtarları kontrol edebilirsin.",
        color=0xff2a43
    )
    embed.add_field(name="🔐 Key Oluştur", value="Yeni bir lisans anahtarı oluşturur ve sana DM'den gönderir.", inline=False)
    embed.add_field(name="📋 Key Kontrol Paneli", value="Tüm anahtarları listeler, kalan sürelerini gösterir ve silme imkanı verir.", inline=False)
    embed.set_footer(text="Santes Hub Bot v3.0 | Tüm hakları saklıdır.")

    # Mesajı kanala gönder
    await channel.send(embed=embed, view=PanelView())

# ============================================================
# BOTU BAŞLAT
# ============================================================
bot.run(TOKEN)

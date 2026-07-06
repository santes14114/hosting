import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import requests
import json
import random
import string
from datetime import datetime, timedelta
import os

# --- BOT AYARLARI ---
TOKEN = os.getenv('BOT_TOKEN')

ADMIN_ID = 359199132906422273
PANEL_CHANNEL_ID = 1523633754550046760
API_URL = 'https://santeshub.great-site.net/api.php'
API_SECRET = 'SANTES_EN_IYI_BABA_VE_ADAMDIR_SECRET_API_KEY'

# Botu oluştur
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# Veri dosyası yolu
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

# Kalan gün hesaplama (Süslü format)
def days_left(expiry_date_str):
    try:
        expiry = datetime.strptime(expiry_date_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        delta = expiry - now
        if delta.total_seconds() <= 0:
            return "⛔ Süresi Doldu"
        days = delta.days
        hours = delta.seconds // 3600
        if days > 0:
            return f"📅 {days} gün {hours} saat"
        else:
            return f"⏰ {hours} saat"
    except:
        return "❓ Hesaplanamıyor"

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
# ÖZEL HATA MESAJI (Gömülü ve Süslü)
# ============================================================
async def send_error(interaction, message):
    embed = discord.Embed(
        title="❌ Hata!",
        description=message,
        color=0xff0000
    )
    embed.set_footer(text="Santes Hub Bot | Lütfen tekrar deneyin.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ============================================================
# MODAL (Key Oluşturma Formu)
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
            await send_error(interaction, f"❌ Süre sadece şunlar olabilir:\n`{', '.join(allowed)}`")
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

        # API'ye gönder
        api_response = send_key_to_api(key_data)

        # Admin'e DM at (Süslü ve efektli)
        try:
            admin_user = await bot.fetch_user(ADMIN_ID)
            embed = discord.Embed(
                title="🔐 YENİ ANAHTAR OLUŞTURULDU!",
                description=(
                    f"👤 **Kullanıcı:** {username}\n"
                    f"⏳ **Süre:** {duration}\n"
                    f"📅 **Bitiş:** {expiry_str}\n"
                    f"🔑 **Anahtar:** `{new_key}`"
                ),
                color=0xff2a43
            )
            embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/123456789012345678.png") # İsteğe bağlı
            embed.set_footer(text="Bu anahtarı kullanıcıya iletmeyi unutma.")
            await admin_user.send(embed=embed)
        except:
            pass

        # Kullanıcıya başarılı geri bildirim
        embed = discord.Embed(
            title="✅ Anahtar Başarıyla Oluşturuldu!",
            description=(
                f"👤 **Kullanıcı:** {username}\n"
                f"⏳ **Süre:** {duration}\n"
                f"🔑 **Anahtar:** `{new_key}`"
            ),
            color=0x00ff00
        )
        embed.set_footer(text="Anahtar DM'den admin'e iletildi.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ============================================================
# ANAHTAR SİLME ONAY BUTONLARI (Premium Özellik)
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
                title="🗑️ Anahtar Silindi!",
                description=f"`{self.key_to_delete}` anahtarı başarıyla silindi.",
                color=0x00ff00
            )
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            await send_error(interaction, "❌ Anahtar bulunamadı veya zaten silinmiş.")

    @discord.ui.button(label="❌ İptal", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="❌ Silme İşlemi İptal Edildi",
            description="Hiçbir anahtar silinmedi.",
            color=0xff2a43
        )
        await interaction.response.edit_message(embed=embed, view=None)

# ============================================================
# BUTONLAR (Ana Panel)
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

        embed = discord.Embed(
            title="📋 Key Kontrol Paneli",
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

        await interaction.response.send_message(embed=embed, view=KeyControlView(), ephemeral=True)

# ============================================================
# KEY KONTROL PANELİ (Premium Silme)
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
            placeholder="SANTES-XXXXXX-YYYYYY"
        )
        self.add_item(self.key_input)

    async def on_submit(self, interaction: discord.Interaction):
        key_to_delete = self.key_input.value.strip()
        
        # Doğrulama ve Onay butonlarını göster
        embed = discord.Embed(
            title="⚠️ Silme Onayı",
            description=f"**`{key_to_delete}`** anahtarını silmek istediğinize emin misiniz?\n\nBu işlem geri alınamaz!",
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
        title="🛠️ Santes Hub Yönetim Paneli",
        description="Aşağıdaki butonları kullanarak anahtar oluşturabilir veya mevcut anahtarları kontrol edebilirsin.",
        color=0xff2a43
    )
    embed.add_field(name="🔐 Key Oluştur", value="Yeni bir lisans anahtarı oluşturur ve sana DM'den gönderir.", inline=False)
    embed.add_field(name="📋 Key Kontrol Paneli", value="Tüm anahtarları listeler, kalan sürelerini gösterir ve silme imkanı verir.", inline=False)
    embed.set_footer(text="Santes Hub Bot | Tüm hakları saklıdır.")

    await channel.send(embed=embed, view=PanelView())

# ============================================================
# BOTU BAŞLAT
# ============================================================
bot.run(TOKEN)

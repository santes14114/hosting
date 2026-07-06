import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import requests
import urllib.parse
import json
import random
import string
import os

TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = 359199132906422273
PANEL_CHANNEL_ID = 1523633754550046760

API_BASE_URL = 'https://santeshub.great-site.net/api.php'
API_SECRET = 'SANTES_GIZLI_API_SIFRESI_2026'

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# -----------------------------------------------------
# 1. API'YE GET İSTEĞİ ATMA FONKSİYONU
# -----------------------------------------------------
async def send_api_request(action, params):
    # URL'yi oluştur
    url = f"{API_BASE_URL}?api_key={API_SECRET}&action={action}"
    for key, value in params.items():
        url += f"&{key}={urllib.parse.quote(str(value))}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            return {"status": "error", "message": f"HTTP Hatası: {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": f"Bağlantı Hatası: {str(e)}"}

# -----------------------------------------------------
# 2. SONUCU DM'YE GÖNDER
# -----------------------------------------------------
async def send_result_to_dm(result_json):
    try:
        admin_user = await bot.fetch_user(ADMIN_ID)
        embed = discord.Embed(
            title="📦 API Yanıtı",
            description=f"```json\n{json.dumps(result_json, indent=4, ensure_ascii=False)}\n```",
            color=0xff2a43
        )
        await admin_user.send(embed=embed)
    except:
        pass

# -----------------------------------------------------
# 3. BUTONLAR
# -----------------------------------------------------
class PanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔐 Key Oluştur", style=discord.ButtonStyle.success)
    async def create_key(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(CreateKeyModal())

    @discord.ui.button(label="🗑️ Key Sil", style=discord.ButtonStyle.danger)
    async def delete_key(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(DeleteKeyModal())

# -----------------------------------------------------
# 4. MODAL: KEY OLUŞTURMA
# -----------------------------------------------------
class CreateKeyModal(Modal):
    def __init__(self):
        super().__init__(title="🔐 Yeni Anahtar Oluştur")
        self.username_input = TextInput(label="Kullanıcı Adı", placeholder="Örn: Santes")
        self.duration_input = TextInput(label="Süre", placeholder="1gün, 1hafta, 1ay, 1yıl")
        self.add_item(self.username_input)
        self.add_item(self.duration_input)

    async def on_submit(self, interaction: discord.Interaction):
        username = self.username_input.value
        duration = self.duration_input.value.lower().strip()

        if duration not in ['1gün', '1hafta', '1ay', '1yıl']:
            await interaction.response.send_message("❌ Geçersiz süre!", ephemeral=True)
            return

        # Rastgele anahtar oluştur
        new_key = f"SANTES-{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"

        # API'ye GET isteği at
        result = await send_api_request("create_key", {
            "username": username,
            "duration": duration,
            "key": new_key
        })

        # Sonucu DM'ye gönder
        await send_result_to_dm(result)

        await interaction.response.send_message("✅ İstek atıldı. Sonuç DM'den gönderildi.", ephemeral=True)

# -----------------------------------------------------
# 5. MODAL: KEY SİLME
# -----------------------------------------------------
class DeleteKeyModal(Modal):
    def __init__(self):
        super().__init__(title="🗑️ Anahtar Sil")
        self.key_input = TextInput(label="Silinecek Anahtar", placeholder="Örn: SANTES-XXXXXX-YYYYYY")
        self.add_item(self.key_input)

    async def on_submit(self, interaction: discord.Interaction):
        key_to_delete = self.key_input.value.strip()
        if not key_to_delete:
            await interaction.response.send_message("❌ Geçerli bir anahtar girin!", ephemeral=True)
            return

        # API'ye GET isteği at
        result = await send_api_request("delete_key", {"key": key_to_delete})

        # Sonucu DM'ye gönder
        await send_result_to_dm(result)

        await interaction.response.send_message("✅ İstek atıldı. Sonuç DM'den gönderildi.", ephemeral=True)

# -----------------------------------------------------
# 6. BOT HAZIR OLDUĞUNDA
# -----------------------------------------------------
@bot.event
async def on_ready():
    print(f"✅ Bot giriş yaptı: {bot.user.name}")
    channel = bot.get_channel(PANEL_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title="🛠️ API Yönetim Paneli",
            description="🔐 **Key Oluştur:** Yeni anahtar oluşturur.\n🗑️ **Key Sil:** Anahtar siler.\n📥 **Sonuçlar DM'ye gelir.**",
            color=0xff2a43
        )
        await channel.send(embed=embed, view=PanelView())

bot.run(TOKEN)

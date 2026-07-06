import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import requests
import json
import random
import string
import os

TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = 359199132906422273
PANEL_CHANNEL_ID = 1523633754550046760

API_URL = 'https://santeshub.great-site.net/api.php'
API_SECRET = 'SANTES_GIZLI_API_SIFRESI_2026'

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# ----------------------------------------------------------------
# 1. BUTON PANELİ
# ----------------------------------------------------------------
class PanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    # 1.1 Key Oluştur Butonu
    @discord.ui.button(label="🔐 Key Oluştur", style=discord.ButtonStyle.success)
    async def create_key(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(CreateKeyModal())

    # 1.2 Key Sil Butonu
    @discord.ui.button(label="🗑️ Key Sil", style=discord.ButtonStyle.danger)
    async def delete_key(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(DeleteKeyModal())


# ----------------------------------------------------------------
# 2. MODAL: KEY OLUŞTUR
# ----------------------------------------------------------------
class CreateKeyModal(Modal):
    def __init__(self):
        super().__init__(title="🔐 Yeni Anahtar Oluştur")
        self.username_input = TextInput(label="Kullanıcı Adı", placeholder="Örn: Santes")
        self.duration_input = TextInput(label="Süre", placeholder="1gün / 1hafta / 1ay / 1yıl")
        self.add_item(self.username_input)
        self.add_item(self.duration_input)

    async def on_submit(self, interaction: discord.Interaction):
        username = self.username_input.value
        duration = self.duration_input.value.lower().strip()

        # Rastgele anahtar oluştur
        new_key = f"SANTES-{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"

        # API'ye istek at (GET)
        url = f"{API_URL}?api_key={API_SECRET}&action=create_key&username={username}&duration={duration}&key={new_key}"

        try:
            response = requests.get(url, timeout=10)
            data = response.json()
            
            # Sonucu DM'ye yolla
            admin_user = await bot.fetch_user(ADMIN_ID)
            embed = discord.Embed(
                title="📦 API Sonucu (Key Oluştur)",
                description=f"```json\n{json.dumps(data, indent=4, ensure_ascii=False)}\n```",
                color=0xff2a43
            )
            await admin_user.send(embed=embed)

            await interaction.response.send_message("✅ Anahtar oluşturma isteği atıldı. Sonuç DM'den gönderildi.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Hata: {str(e)}", ephemeral=True)


# ----------------------------------------------------------------
# 3. MODAL: KEY SİL
# ----------------------------------------------------------------
class DeleteKeyModal(Modal):
    def __init__(self):
        super().__init__(title="🗑️ Anahtar Sil")
        self.key_input = TextInput(label="Silinecek Anahtar", placeholder="Örn: SANTES-XXXXXX-YYYYYY")
        self.add_item(self.key_input)

    async def on_submit(self, interaction: discord.Interaction):
        key_to_delete = self.key_input.value.strip()

        # API'ye istek at (GET)
        url = f"{API_URL}?api_key={API_SECRET}&action=delete_key&key={key_to_delete}"

        try:
            response = requests.get(url, timeout=10)
            data = response.json()
            
            # Sonucu DM'ye yolla
            admin_user = await bot.fetch_user(ADMIN_ID)
            embed = discord.Embed(
                title="📦 API Sonucu (Key Sil)",
                description=f"```json\n{json.dumps(data, indent=4, ensure_ascii=False)}\n```",
                color=0xff2a43
            )
            await admin_user.send(embed=embed)

            await interaction.response.send_message("✅ Silme isteği atıldı. Sonuç DM'den gönderildi.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Hata: {str(e)}", ephemeral=True)


# ----------------------------------------------------------------
# 4. BOT BAŞLANGICI
# ----------------------------------------------------------------
@bot.event
async def on_ready():
    print(f"✅ Bot giriş yaptı: {bot.user.name}")
    channel = bot.get_channel(PANEL_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title="🛠️ Santes Hub Yönetim Paneli",
            description="🔐 **Key Oluştur:** Yeni anahtar oluştur (Sonuç DM'ye gelir).\n🗑️ **Key Sil:** Anahtar sil (Sonuç DM'ye gelir).",
            color=0xff2a43
        )
        await channel.send(embed=embed, view=PanelView())

bot.run(TOKEN)

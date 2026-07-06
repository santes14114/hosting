import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import requests
import json
import random
import string
import os
import urllib.parse

TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = 359199132906422273
PANEL_CHANNEL_ID = 1523633754550046760

API_URL = 'https://santeshub.great-site.net/api.php'

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# ----------------------------------------------------------------
# 1. BUTON PANELİ
# ----------------------------------------------------------------
class PanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔐 Key Oluştur", style=discord.ButtonStyle.success)
    async def create_key(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(CreateKeyModal())

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

        if duration not in ['1gün', '1hafta', '1ay', '1yıl']:
            await interaction.response.send_message("❌ Geçersiz süre!", ephemeral=True)
            return

        new_key = f"SANTES-{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"

        # API'ye GET isteği at (Şifre yok!)
        url = f"{API_URL}?action=create_key&username={urllib.parse.quote(username)}&duration={duration}&key={new_key}"

        try:
            response = requests.get(url, timeout=10)
            
            if response.status_code != 200:
                await interaction.response.send_message(f"❌ HTTP Hatası: {response.status_code}", ephemeral=True)
                return

            if not response.text.strip():
                await interaction.response.send_message("❌ API'den boş cevap geldi!", ephemeral=True)
                return

            try:
                data = response.json()
            except json.JSONDecodeError:
                await interaction.response.send_message(f"❌ JSON Hatası! Gelen: {response.text[:100]}...", ephemeral=True)
                return

            # Sonucu DM'ye yolla
            admin_user = await bot.fetch_user(ADMIN_ID)
            embed = discord.Embed(
                title="📦 API Sonucu (Key Oluştur)",
                description=f"```json\n{json.dumps(data, indent=4, ensure_ascii=False)}\n```",
                color=0xff2a43
            )
            await admin_user.send(embed=embed)

            await interaction.response.send_message("✅ Anahtar oluşturma isteği atıldı. Sonuç DM'den gönderildi.", ephemeral=True)
        
        except requests.exceptions.ConnectionError:
            await interaction.response.send_message("❌ Bağlantı kesildi! InfinityFree sunucusu yanıt vermiyor.", ephemeral=True)
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

        if not key_to_delete:
            await interaction.response.send_message("❌ Lütfen geçerli bir anahtar girin!", ephemeral=True)
            return

        # API'ye GET isteği at (Şifre yok!)
        url = f"{API_URL}?action=delete_key&key={urllib.parse.quote(key_to_delete)}"

        try:
            response = requests.get(url, timeout=10)
            
            if response.status_code != 200:
                await interaction.response.send_message(f"❌ HTTP Hatası: {response.status_code}", ephemeral=True)
                return

            if not response.text.strip():
                await interaction.response.send_message("❌ API'den boş cevap geldi!", ephemeral=True)
                return

            try:
                data = response.json()
            except json.JSONDecodeError:
                await interaction.response.send_message(f"❌ JSON Hatası! Gelen: {response.text[:100]}...", ephemeral=True)
                return

            # Sonucu DM'ye yolla
            admin_user = await bot.fetch_user(ADMIN_ID)
            embed = discord.Embed(
                title="📦 API Sonucu (Key Sil)",
                description=f"```json\n{json.dumps(data, indent=4, ensure_ascii=False)}\n```",
                color=0xff2a43
            )
            await admin_user.send(embed=embed)

            await interaction.response.send_message("✅ Silme isteği atıldı. Sonuç DM'den gönderildi.", ephemeral=True)
        
        except requests.exceptions.ConnectionError:
            await interaction.response.send_message("❌ Bağlantı kesildi! InfinityFree sunucusu yanıt vermiyor.", ephemeral=True)
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

import os
import json
import discord
from discord.ext import commands
from discord import app_commands
from keep_alive import keep_alive

import gspread
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import AuthorizedSession

TOKEN = os.getenv("TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
GUILD_ID = int(os.getenv("GUILD_ID"))
SHEET_ID = os.getenv("SHEET_ID")  # Google Sheet ID
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")  # The full JSON content as a string

# Load Google credentials from JSON string
creds_dict = json.loads(GOOGLE_CREDS_JSON)
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
gc = gspread.authorize(creds)

WORKSHEET_NAME = "Sheet1"  # Change if needed

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.publish_submissions = {}
bot.verify_submissions = {}

REGISTERED_CREATOR_ROLE_NAME = "Registered Creator"

class PublishModal(discord.ui.Modal, title="Submit UGC Item"):
    item_name = discord.ui.TextInput(label="Item Name", max_length=100)
    description = discord.ui.TextInput(label="Item Description", style=discord.TextStyle.paragraph, max_length=1000)
    fbx_url = discord.ui.TextInput(label="FBX File URL", placeholder="Provide a link to your .fbx file", max_length=200)
    texture_url = discord.ui.TextInput(label="Texture File URL", placeholder="Link to baked texture file", max_length=200)

    async def on_submit(self, interaction: discord.Interaction):
        bot.publish_submissions[interaction.user.id] = {
            "item_name": self.item_name.value,
            "description": self.description.value,
            "fbx_url": self.fbx_url.value,
            "texture_url": self.texture_url.value,
        }
        # Send submission info to owner
        owner = await bot.fetch_user(OWNER_ID)
        embed = discord.Embed(
            title=f"New UGC Item Submission: {self.item_name.value}",
            description=f"{self.description.value}",
            color=discord.Color.green()
        )
        embed.add_field(name="FBX URL", value=self.fbx_url.value, inline=False)
        embed.add_field(name="Texture URL", value=self.texture_url.value, inline=False)
        embed.set_author(name=interaction.user.name, icon_url=interaction.user.display_avatar.url)
        await owner.send(embed=embed)

        await interaction.response.send_message("✅ Your UGC item submission has been received and sent for review.", ephemeral=True)

class VerifyModal(discord.ui.Modal, title="UGC Creator Verification"):
    roblox_username = discord.ui.TextInput(label="Roblox Username", max_length=100)
    roblox_user_id = discord.ui.TextInput(label="Roblox User ID", max_length=20)
    ugc_example_link = discord.ui.TextInput(label="UGC Example or Portfolio Link", style=discord.TextStyle.paragraph, max_length=500)
    acknowledgment = discord.ui.TextInput(label="Type 'I agree' to confirm you understand", max_length=10)

    async def on_submit(self, interaction: discord.Interaction):
        if self.acknowledgment.value.strip().lower() != "i agree":
            await interaction.response.send_message("❌ You must type 'I agree' to confirm the requirements.", ephemeral=True)
            return

        # Append to Google Sheet
        try:
            sheet = gc.open_by_key(SHEET_ID).worksheet(WORKSHEET_NAME)
            # Find the next available row (1-based)
            next_row = len(sheet.get_all_values()) + 1

            # Prepare the row data:
            # Column 1: Roblox Username (string)
            # Column 2: Roblox User ID (string)
            # Column 3: formula for COUNTIF(...) referencing current row
            # Column 4: formula referencing column 3 of current row and range C4:C20

            col1 = self.roblox_username.value.strip()
            col2 = self.roblox_user_id.value.strip()
            col3 = f'=COUNTIF(INDIRECT("E{next_row}:Z{next_row}"), "<>")'
            col4 = f'=(INDIRECT(ADDRESS(ROW(), COLUMN() - 1)) / SUM(C4:C20)) * 70'

            row_data = [col1, col2, col3, col4]

            sheet.insert_row(row_data, next_row)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to save verification info: {e}", ephemeral=True)
            return

        bot.verify_submissions[interaction.user.id] = {
            "roblox_username": self.roblox_username.value.strip(),
            "roblox_user_id": self.roblox_user_id.value.strip(),
            "ugc_example_link": self.ugc_example_link.value.strip(),
        }

        guild = bot.get_guild(GUILD_ID)
        member = guild.get_member(interaction.user.id)
        if not member:
            await interaction.response.send_message("❌ Could not find you in the server.", ephemeral=True)
            return

        role = discord.utils.get(guild.roles, name=REGISTERED_CREATOR_ROLE_NAME)
        if not role:
            role = await guild.create_role(name=REGISTERED_CREATOR_ROLE_NAME)

        try:
            await member.add_roles(role, reason="UGC Creator verified")
            await interaction.response.send_message("✅ Verified! You have been given the Registered Creator role.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to assign role: {e}", ephemeral=True)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    print("Commands registered before sync:")
    for cmd in bot.tree.walk_commands():
        print(f"- {cmd.name}")

    try:
        guild = discord.Object(id=GUILD_ID)
        synced = await bot.tree.sync(guild=guild)
        print(f"Synced {len(synced)} command(s) for guild {GUILD_ID}")
    except Exception as e:
        print(f"Sync error: {e}")

    print("Commands registered after sync:")
    for cmd in bot.tree.walk_commands():
        print(f"- {cmd.name}")

@bot.tree.command(name="publish", description="Submit a UGC item for publishing", guild=discord.Object(id=GUILD_ID))
async def publish(interaction: discord.Interaction):
    await interaction.response.send_modal(PublishModal())

@bot.tree.command(name="verify", description="Verify as a UGC creator to get access", guild=discord.Object(id=GUILD_ID))
async def verify(interaction: discord.Interaction):
    await interaction.response.send_modal(VerifyModal())

@bot.command()
@commands.is_owner()
async def sync(ctx):
    synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    await ctx.send(f"Synced {len(synced)} commands.")

keep_alive()
bot.run(TOKEN)

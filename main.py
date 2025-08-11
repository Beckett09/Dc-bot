import os
import json
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from keep_alive import keep_alive

import gspread
from google.oauth2.service_account import Credentials

# ===== Environment Variables =====
TOKEN = os.getenv("TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
GUILD_ID = int(os.getenv("GUILD_ID"))
SHEET_ID = os.getenv("SHEET_ID")
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")

# ===== Google Sheets Auth =====
creds_dict = json.loads(GOOGLE_CREDS_JSON)
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
gc = gspread.authorize(creds)

WORKSHEET_NAME = "Sheet1"
REGISTERED_CREATOR_ROLE_NAME = "Registered Creator"

# ===== Discord Bot =====
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.publish_submissions = {}
bot.verify_submissions = {}

# ===== Modals =====
class PublishModal(discord.ui.Modal, title="Submit UGC Item"):
    item_name = discord.ui.TextInput(label="Item Name", max_length=100)
    description = discord.ui.TextInput(label="Item Description", style=discord.TextStyle.paragraph, max_length=1000)
    fbx_url = discord.ui.TextInput(label="FBX File URL", placeholder="Link to .fbx file", max_length=200)
    texture_url = discord.ui.TextInput(label="Texture File URL", placeholder="Link to baked texture", max_length=200)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            bot.publish_submissions[interaction.user.id] = {
                "item_name": self.item_name.value,
                "description": self.description.value,
                "fbx_url": self.fbx_url.value,
                "texture_url": self.texture_url.value,
            }

            async def send_owner():
                try:
                    owner = await bot.fetch_user(OWNER_ID)
                    embed = discord.Embed(
                        title=f"New UGC Item Submission: {self.item_name.value}",
                        description=self.description.value,
                        color=discord.Color.green()
                    )
                    embed.add_field(name="FBX URL", value=self.fbx_url.value, inline=False)
                    embed.add_field(name="Texture URL", value=self.texture_url.value, inline=False)
                    embed.set_author(name=interaction.user.name, icon_url=interaction.user.display_avatar.url)
                    await owner.send(embed=embed)
                except Exception as e:
                    print(f"[PublishModal] Failed to DM owner: {e}")

            asyncio.create_task(send_owner())
            await interaction.followup.send("✅ Your UGC item has been submitted for review.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Submission failed: {e}", ephemeral=True)


class VerifyModal(discord.ui.Modal, title="UGC Creator Verification"):
    roblox_username = discord.ui.TextInput(label="Roblox Username", max_length=100)
    roblox_user_id = discord.ui.TextInput(label="Roblox User ID", max_length=20)
    ugc_example_link = discord.ui.TextInput(label="UGC Example or Portfolio Link", style=discord.TextStyle.paragraph, max_length=500)
    acknowledgment = discord.ui.TextInput(label="Type 'I agree' to confirm", max_length=10)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            if self.acknowledgment.value.strip().lower() != "i agree":
                await interaction.followup.send("❌ You must type 'I agree' exactly.", ephemeral=True)
                return

            # Google Sheets operation
            def write_to_sheets():
                sheet = gc.open_by_key(SHEET_ID).worksheet(WORKSHEET_NAME)
                next_row = len(sheet.get_all_values()) + 1
                col1 = self.roblox_username.value.strip()
                col2 = self.roblox_user_id.value.strip()
                col3 = f'=COUNTIF(INDIRECT("E{next_row}:Z{next_row}"), "<>")'
                col4 = f'=(INDIRECT(ADDRESS(ROW(), COLUMN() - 1)) / SUM(C4:C20)) * 70'
                row_data = [col1, col2, col3, col4]
                sheet.insert_row(row_data, next_row)
                sheet.update_acell(f"C{next_row}", col3)
                sheet.update_acell(f"D{next_row}", col4)
                return col1, col2

            try:
                col1, col2 = await asyncio.to_thread(write_to_sheets)
            except Exception as e:
                await interaction.followup.send(f"❌ Google Sheets update failed: {e}", ephemeral=True)
                return

            bot.verify_submissions[interaction.user.id] = {
                "roblox_username": col1,
                "roblox_user_id": col2,
                "ugc_example_link": self.ugc_example_link.value.strip(),
            }

            guild = bot.get_guild(GUILD_ID)
            member = guild.get_member(interaction.user.id) or await guild.fetch_member(interaction.user.id)

            if not member:
                await interaction.followup.send("❌ Could not find you in the server.", ephemeral=True)
                return

            role = discord.utils.get(guild.roles, name=REGISTERED_CREATOR_ROLE_NAME)
            if not role:
                try:
                    role = await guild.create_role(name=REGISTERED_CREATOR_ROLE_NAME)
                except Exception as e:
                    await interaction.followup.send(f"❌ Failed to create role: {e}", ephemeral=True)
                    return

            try:
                await member.add_roles(role, reason="UGC Creator verified")
                await interaction.followup.send("✅ Verified! You have been given the Registered Creator role.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Failed to assign role: {e}", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Unexpected error: {e}", ephemeral=True)


# ===== Slash Commands =====
@app_commands.checks.cooldown(1, 10)
@bot.tree.command(name="publish", description="Submit a UGC item", guild=discord.Object(id=GUILD_ID))
async def publish(interaction: discord.Interaction):
    guild = bot.get_guild(GUILD_ID)
    member = guild.get_member(interaction.user.id) or await guild.fetch_member(interaction.user.id)
    role = discord.utils.get(guild.roles, name=REGISTERED_CREATOR_ROLE_NAME)

    if not role or not member or role not in member.roles:
        await interaction.response.send_message("❌ You must be a Registered Creator to submit items.", ephemeral=True)
        return

    await interaction.response.send_modal(PublishModal())


@app_commands.checks.cooldown(1, 10)
@bot.tree.command(name="verify", description="Verify as a UGC creator", guild=discord.Object(id=GUILD_ID))
async def verify(interaction: discord.Interaction):
    guild = bot.get_guild(GUILD_ID)
    member = guild.get_member(interaction.user.id) or await guild.fetch_member(interaction.user.id)
    role = discord.utils.get(guild.roles, name=REGISTERED_CREATOR_ROLE_NAME)

    if role and member and role in member.roles:
        await interaction.response.send_message("✅ You are already verified.", ephemeral=True)
        return

    await interaction.response.send_modal(VerifyModal())


# ===== Sync Command =====
@bot.command()
@commands.is_owner()
async def sync(ctx):
    synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    await ctx.send(f"Synced {len(synced)} commands.")

# ===== Events =====
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"Synced {len(synced)} command(s) for guild {GUILD_ID}")
    except Exception as e:
        print(f"Command sync failed: {e}")

# ===== Run =====
keep_alive()
bot.run(TOKEN)

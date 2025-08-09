import os
import discord
from discord.ext import commands
from discord import app_commands
from keep_alive import keep_alive

TOKEN = os.getenv("TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
GUILD_ID = int(os.getenv("GUILD_ID"))

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True  # Required for role assignment

bot = commands.Bot(command_prefix="!", intents=intents)
bot.user_submissions = {}
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
        await interaction.response.send_message("✅ Your UGC item submission has been received and will be reviewed.", ephemeral=True)

class VerifyModal(discord.ui.Modal, title="UGC Creator Verification"):
    roblox_username = discord.ui.TextInput(label="Roblox Username", max_length=100)
    roblox_user_id = discord.ui.TextInput(label="Roblox User ID", max_length=20)
    ugc_example_link = discord.ui.TextInput(label="UGC Example (render, portfolio link, or past work)", style=discord.TextStyle.paragraph, max_length=500)
    acknowledgment = discord.ui.TextInput(label="Type 'I agree' to confirm you understand the requirements", max_length=10)

    async def on_submit(self, interaction: discord.Interaction):
        # Validate acknowledgment
        if self.acknowledgment.value.strip().lower() != "i agree":
            await interaction.response.send_message("❌ You must type 'I agree' to confirm the requirements.", ephemeral=True)
            return

        bot.verify_submissions[interaction.user.id] = {
            "roblox_username": self.roblox_username.value.strip(),
            "roblox_user_id": self.roblox_user_id.value.strip(),
            "ugc_example_link": self.ugc_example_link.value.strip(),
        }

        # Attempt to assign Registered Creator role
        guild = bot.get_guild(GUILD_ID)
        member = guild.get_member(interaction.user.id)
        if not member:
            await interaction.response.send_message("❌ Could not find you in the server.", ephemeral=True)
            return

        role = discord.utils.get(guild.roles, name=REGISTERED_CREATOR_ROLE_NAME)
        if not role:
            # Create role if it doesn't exist
            role = await guild.create_role(name=REGISTERED_CREATOR_ROLE_NAME)
        
        try:
            await member.add_roles(role, reason="UGC Creator verified")
            await interaction.response.send_message("✅ Verified! You have been given the Registered Creator role.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to assign role: {e}", ephemeral=True)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        guild = discord.Object(id=GUILD_ID)
        synced = await bot.tree.sync(guild=guild)
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

@bot.tree.command(name="post", description="Submit content", guild=discord.Object(id=GUILD_ID))
async def post(interaction: discord.Interaction):
    await interaction.response.send_modal(PostModal())

@bot.tree.command(name="publish", description="Submit a UGC item for publishing", guild=discord.Object(id=GUILD_ID))
async def publish(interaction: discord.Interaction):
    await interaction.response.send_modal(PublishModal())

@bot.tree.command(name="verify", description="Verify as a UGC creator to get access", guild=discord.Object(id=GUILD_ID))
async def verify(interaction: discord.Interaction):
    await interaction.response.send_modal(VerifyModal())

@bot.event
async def on_message(message):
    await bot.process_commands(message)
    if message.author.bot:
        return

    # Handle simple image submission after /post modal
    if message.author.id in bot.user_submissions:
        data = bot.user_submissions.pop(message.author.id)

        image_url = None
        if message.attachments:
            image_url = message.attachments[0].url

        user = await bot.fetch_user(OWNER_ID)

        embed = discord.Embed(
            title=data["title"],
            description=data["description"],
            color=discord.Color.teal()
        )
        if image_url:
            embed.set_image(url=image_url)

        await user.send(f"New submission from {message.author.mention}:", embed=embed)
        await message.reply("✅ Sent to the owner!")

keep_alive()
bot.run(TOKEN)

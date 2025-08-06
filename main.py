import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

from keep_alive import keep_alive

load_dotenv()


print("TOKEN:", os.environ.get('YOUR_VARIABLE_NAME'))
print("OWNER_ID:", os.getenv("OWNER_ID"))
print("GUILD_ID:", os.getenv("GUILD_ID"))


TOKEN = os.getenv("TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
GUILD_ID = int(os.getenv("GUILD_ID"))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
bot.user_submissions = {}

class PostModal(discord.ui.Modal, title="Submit Your Info"):
    title_input = discord.ui.TextInput(label="Title", max_length=100)
    description_input = discord.ui.TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        bot.user_submissions[interaction.user.id] = {
            "title": self.title_input.value,
            "description": self.description_input.value
        }
        await interaction.response.send_message("✅ Info received! Now reply to this with an image.", ephemeral=True)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

@bot.tree.command(name="post", description="Submit content", guild=discord.Object(id=GUILD_ID))
async def post(interaction: discord.Interaction):
    await interaction.response.send_modal(PostModal())

@bot.event
async def on_message(message):
    await bot.process_commands(message)
    if message.author.bot:
        return

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

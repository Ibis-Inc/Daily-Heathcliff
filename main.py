import discord
from discord import app_commands
from discord.ext import tasks, commands
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import json
import asyncio
from playwright_stealth import Stealth
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

load_dotenv()

TOKEN = os.getenv('TOKEN')

intents = discord.Intents.default()
intents.messages = True  
intents.guilds = True    

bot = commands.Bot(command_prefix='!', intents=intents)

CHANNEL_DATA_FILE = 'channel_data.json'

def load_channel_data():
    if os.path.exists(CHANNEL_DATA_FILE):
        with open(CHANNEL_DATA_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_channel_data(data):
    with open(CHANNEL_DATA_FILE, 'w') as f:
        json.dump(data, f)

channel_data = load_channel_data()

ROLE_DATA_FILE = 'role_data.json'

def load_role_data():
    if os.path.exists(ROLE_DATA_FILE):
        with open(ROLE_DATA_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_role_data(data):
    with open(ROLE_DATA_FILE, 'w') as f:
        json.dump(data, f)

role_data = load_role_data()

IMAGE_SOURCE_FILE = 'image_sources.json'
ES_IMAGE_SOURCE_FILE = 'es_image_sources.json'

if os.path.exists(IMAGE_SOURCE_FILE):
    with open(IMAGE_SOURCE_FILE, 'r') as f:
        image_sources = json.load(f)
else:
    image_sources = {}

if os.path.exists(ES_IMAGE_SOURCE_FILE):
    with open(ES_IMAGE_SOURCE_FILE, 'r') as f:
        es_image_sources = json.load(f)
else:
    es_image_sources = {}


async def webRequest(formatted_date, lang):
    if lang == "ES":
        url = f"https://www.gocomics.com/heathcliffespanol/{formatted_date}"
    else:
        url = f"https://www.gocomics.com/heathcliff/{formatted_date}"

    print(f"Beginning process to obtain image source for {formatted_date}")
    
    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
                "--no-sandbox"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US"
        )
        page = await context.new_page()
        img_src = None
        
        try:
            print(f"Navigating to: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            #filter for ComicStory
            scripts = await page.locator("script[type='application/ld+json']").all_inner_texts()
            for script in scripts:
                try:
                    data = json.loads(script)
                    if isinstance(data, dict):
                        #must match ComicStory
                        if data.get("@type") == "ComicStory":
                            # The main strip image is stored inside the 'image' key or feature asset links
                            if "image" in data and isinstance(data["image"], str):
                                #if the image points to the header splash check if theres a feature asset link in page html
                                if "Feature_Splash" not in data["image"]:
                                    img_src = data["image"]
                                    break
                except json.JSONDecodeError:
                    continue

            #fallback on filtering for tags or metadata if splash is returned
            if not img_src or "Feature_Splash" in img_src:
                # GoComics stores the strip image URL in twitter/og meta tags as well
                og_image = await page.locator("meta[property='og:image']").get_attribute("content")
                if og_image and "Feature_Splash" not in og_image:
                    img_src = og_image

            if not img_src:
                target_selector = "img[class*='comic__image']"
                await page.wait_for_selector(target_selector, timeout=10000)
                img_src = await page.locator(target_selector).first.get_attribute("src")

            print(f"Image source successfully obtained: {img_src}")

        except PlaywrightTimeoutError as e:
            print(f"Scraper timeout for {formatted_date}: {e}")
            await browser.close()
            return f"Error: Could not retrieve comic image for {formatted_date}."
        except Exception as e:
            print(f"Scraper exception: {e}")
            await browser.close()
            return f"Error: {e}"

        await browser.close()

        #cache valid image urls
        if img_src and not img_src.startswith("Error"):
            if lang == "ES":
                es_image_sources[formatted_date] = img_src
                with open(ES_IMAGE_SOURCE_FILE, 'w') as json_file:
                    json.dump(es_image_sources, json_file)
            else:
                image_sources[formatted_date] = img_src
                with open(IMAGE_SOURCE_FILE, 'w') as json_file:
                    json.dump(image_sources, json_file)
            print("Updated local image source cache dictionaries.")

        return img_src

async def obtainImageSource(formatted_date, lang):
    sources = es_image_sources if lang == "ES" else image_sources
    datesrc = sources.get(formatted_date)

    #return cached URL unless it's a previously stored error string
    if datesrc and not datesrc.startswith("Error"):
        print(f"Image source obtained from cache for {lang}.")
        return datesrc

    print(f"Running web request for {lang}")
    return await webRequest(formatted_date, lang)


@tasks.loop(hours=24)
async def send_daily_message():
    now = datetime.now(timezone.utc)
    formatted_date = now.strftime("%Y/%m/%d")
    imgsrc = await webRequest(formatted_date, "EN")
    print("Obtained source within the 24 hour loop")

    for guild_id, channel_id in channel_data.items():
        channel = bot.get_channel(channel_id)
        if channel is None:
            continue

        role_id = role_data.get(str(guild_id))
        try:
            await channel.send(imgsrc)
            print(f'Sent daily message to {channel.mention}: {imgsrc}')
            if role_id:
                await channel.send(f"<@&{role_id}>")
        except Exception as e:
            print(f"Failed to send message to channel {channel_id}: {e}")


@bot.event
async def on_ready():
    print(f"{bot.user.name} has logged in successfully")
    await bot.tree.sync()
    if not send_daily_message.is_running():
        send_daily_message.start()


@bot.tree.command(name='ping', description='What do you think will happen')
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message('Pong!', ephemeral=True)


@bot.tree.command(name='set-channel', description='Use it to set where the comic is sent daily')
@app_commands.checks.has_permissions(manage_channels=True)
async def channel(interaction: discord.Interaction, channel: discord.TextChannel):
    global channel_data
    channel_data[str(interaction.guild.id)] = channel.id
    save_channel_data(channel_data)
    await interaction.response.send_message(f'Channel set to: {channel.mention}', ephemeral=True)


@bot.tree.command(name='set-role', description='Use it to set where the role to ping for the daily comic')
@app_commands.checks.has_permissions(manage_channels=True)
async def role(interaction: discord.Interaction, role: discord.Role):
    if role is None:
        await interaction.response.send_message("The selected role is invalid.", ephemeral=True)
        return

    global role_data
    role_data[str(interaction.guild.id)] = role.id
    save_role_data(role_data)
    await interaction.response.send_message(f'Role set to: {role.mention}', ephemeral=True)


@bot.tree.command(name='reset-role', description='Reset the ping role for the bot')
@app_commands.checks.has_permissions(manage_channels=True)
async def resetrole(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    if guild_id in role_data:
        del role_data[guild_id]
        save_role_data(role_data)
        await interaction.response.send_message("The role has been reset for this server.", ephemeral=True)
    else:
        await interaction.response.send_message("No role has been set for this server to reset.", ephemeral=True)


@bot.tree.command(name='send-now', description='Send Heathcliff comic (Defaults to today) YYYY/MM/DD')
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.choices(lang=[app_commands.Choice(name="EN", value="EN"), app_commands.Choice(name="ES", value="ES")])
async def sendnow(interaction: discord.Interaction, date: str = None, lang: str = "EN"):
    # Defer immediately to allow Playwright execution beyond Discord's 3-second limit
    await interaction.response.defer()

    if date is None:
        now = datetime.now(timezone.utc)
        if lang == "ES":
            formatted_date = (now - timedelta(days=1)).strftime("%Y/%m/%d")
        else:
            formatted_date = now.strftime("%Y/%m/%d")
    else:
        try:
            parsed_date = datetime.strptime(date, "%Y/%m/%d")
            formatted_date = parsed_date.strftime("%Y/%m/%d")

            if parsed_date.year < 2002:
                await interaction.followup.send("The year must be 2002 or later.")
                return

            if lang == "ES" and parsed_date < datetime(2012, 5, 21):
                await interaction.followup.send("Los archivos españoles solo llegan hasta el 21/05/2012.")
                return

        except ValueError:
            await interaction.followup.send("Invalid date format. Please use YYYY/MM/DD.")
            return

    imgsrc = await obtainImageSource(formatted_date, lang)
    await interaction.followup.send(imgsrc)


@bot.tree.command(name='see-channel', description='Shows currently assigned channel')
@app_commands.checks.has_permissions(manage_channels=True)
async def ping_channel(interaction: discord.Interaction):
    channel_id = channel_data.get(str(interaction.guild.id))
    if channel_id:
        channel = interaction.guild.get_channel(channel_id)
        if channel:
            await interaction.response.send_message(f'Here is the channel: {channel.mention}', ephemeral=True)
        else:
            await interaction.response.send_message("The channel set for this server no longer exists.", ephemeral=True)
    else:
        await interaction.response.send_message("No channel has been set for this server.", ephemeral=True)


if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        print("Bot has been stopped.")
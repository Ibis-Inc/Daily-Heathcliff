import discord
from discord import app_commands
from discord.ext import tasks, commands
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import time
import json
import asyncio
from playwright_stealth import Stealth
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


load_dotenv()

TOKEN = os.getenv('TOKEN')  # Use environment variable for the token

# Create intents
intents = discord.Intents.default()
intents.messages = True  
intents.guilds = True    

# Create an instance of commands.Bot with intents
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
            print(f"role id {f}")
            return json.load(f)
    return {}

def save_role_data(data):
    print(f"role id {data}")
    with open(ROLE_DATA_FILE, 'w') as f:
        json.dump(data, f)
        print(f"role id {data}")

role_data = load_role_data()

IMAGE_SOURCE_FILE = 'image_sources.json'
ES_IMAGE_SOURCE_FILE = 'es_image_sources.json'

if os.path.exists(IMAGE_SOURCE_FILE):
    with open(IMAGE_SOURCE_FILE, 'r') as f:
        image_sources = json.load(f)
else:
    image_sources = {}

IMAGE_SOURCE_FILE = 'image_sources.json'

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
    
    #  Open the stealth execution context manager
    async with Stealth().use_async(async_playwright()) as p:
        
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        print("Launched invisible browser engine")
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US"
        )
        
        page = await context.new_page()
        
        try:
            # Navigate using the domcontentloaded strategy to outrun heavy ad servers
            print(f"Navigating to: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            print("Base HTML structure loaded completely")
            
            # Substring bypasses obfuscation
            target_selector = "img[class*='comic__image']"
            
            print(f"Waiting for selector: {target_selector}")
            await page.wait_for_selector(target_selector, timeout=15000)
            
            # Extract the raw source URL string
            img_src = await page.locator(target_selector).first.get_attribute("src")
            print(f"Image source successfully obtained: {img_src}")
            
        except PlaywrightTimeoutError as e:
            print(f"Scraper error encountered tracking {formatted_date}: {e}")
            try:
                await page.screenshot(path="bot_error_view.png")
                print("Saved emergency visual snapshot to 'bot_error_view.png'")
            except Exception:
                pass
            await browser.close()
            return "Error: Could not retrieve the comic image due to a layout or loading timeout."
            
        await browser.close()
        
        #  File-saving logic blocks
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



async def obtainHeathcliffSource(formatted_date,lang):

    if lang == "ES":
        # Check if the date requested is stored in the Spanish dictionary
        datesrc = es_image_sources.get(formatted_date)

        if datesrc:
            src = datesrc  # Obtain source URL from the Spanish dictionary for the date
            print("Image source obtained from the Spanish dictionary.")
        else:
            print("running web request for Spanish")
            src = await webRequest(formatted_date, lang)
        return src
    # Check if the date requested is stored in the dictionary
    datesrc = image_sources.get(formatted_date)

    if datesrc:
        src = datesrc  # Obtain source URL from the dictionary for the date
        print("Image source obtained from the dictionary.")
    else:
        print("running web request")
        src = await webRequest(formatted_date, lang)
    return src

# async def waitUntil(end_hour,end_minute,end_second):
#     print("currently: " + str(datetime.now().hour)+ ":" + str(datetime.now().minute)+ ":" + str(datetime.now().second))

#     while datetime.now().hour != end_hour: 

#         while datetime.now().minute != end_minute:

#             while datetime.now().second != end_second:  
                                                        
#                 print("waiting second")                 #¦timing for the specified second
#                 await asyncio.sleep(1)                          #¦

#             print("waiting minute") #¦timing for the specified hour
#             await asyncio.sleep(1)          #¦

#         print("waiting hour") #¦timing for the specified hour
#         await asyncio.sleep(1)       #¦




@tasks.loop(hours=24)
async def send_daily_message():
    now = datetime.utcnow() #this is depreciated we should probably replace it
    formatted_date = now.strftime("%Y/%m/%d")
    imgsrc = await webRequest(formatted_date, "EN")
    print("obtained source within the 24 hour loop")

    for guild_id, channel_id in channel_data.items():
        channel = bot.get_channel(channel_id)
        
        if channel is None:
            print(f"Invalid channel ID for guild {guild_id}. Please set a valid channel.")
            continue  # Skip to the next iteration if the channel is invalid

        role_id = role_data.get(str(guild_id))  # Get the role ID for the guild

        try:
            await channel.send(imgsrc)
            print(f'Sent daily message to {channel.mention}: {imgsrc}, from {formatted_date}')
            if role_id:
                await channel.send(f"<@&{role_id}>")
        except Exception as e:
            print(f"Failed to send message to {channel.mention}: {e}")


@bot.event
async def on_ready():
    print(f"{bot.user.name} has logged in successfully")
    await bot.tree.sync()
    #define target time as 12:00:00 (noon) today
    now = datetime.now()
    target = now.replace(hour=12, minute=0, second=0, microsecond=0)
    #if it is already past noon today, target noon tomorrow
    if now >= target:
        target += timedelta(days=1)
    #calculate how many seconds to sleep
    sleep_duration = (target - now).total_seconds()
    print(f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Sleeping until: {target.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total sleep duration: {sleep_duration:.2f} seconds")
    time.sleep(sleep_duration)
    send_daily_message.start()

@bot.tree.command(name='ping', description='What do you think will happen')
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message('Pong!', ephemeral=True)

#@bot.tree.command(name='time-til-hour', description='Shameless debug command')
#async def hourcheck(interaction: discord.Interaction):
#    # Get the current time
#    now = datetime.now()
#
#    # Calculate the next hour
#    next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
#
#    # Calculate the time difference
#    time_until_next_hour = next_hour - now
#    await interaction.response.send_message(f"Time until next hour: {time_until_next_hour}", ephemeral=True)

@bot.tree.command(name='set-channel', description='Use it to set where the comic is sent daily')
@app_commands.checks.has_permissions(manage_channels=True)
async def channel(interaction: discord.Interaction, channel: discord.TextChannel):
    global channel_data
    channel_data[str(interaction.guild.id)] = channel.id  # Store the channel ID
    save_channel_data(channel_data)  # Save the channel data
    await interaction.response.send_message(f'Channel set to: {channel.mention}', ephemeral=True)

@bot.tree.command(name='set-role', description='Use it to set where the role to ping for the daily comic')
@app_commands.checks.has_permissions(manage_channels=True)
async def role(interaction: discord.Interaction, role: discord.Role):
    if role is None:
        await interaction.response.send_message("The selected role is invalid.", ephemeral=True)
        return

    print(f"Selected role: {role.name} (ID: {role.id})")  # Debugging line
    global role_data
    role_data[str(interaction.guild.id)] = role.id  # Store the role ID
    save_role_data(role_data)  # Save the updated role data
    await interaction.response.send_message(f'Role set to: {role.mention}', ephemeral=True)

@bot.tree.command(name='reset-role', description='Use it to reset the ping role for the bot (meaning it won\'t send a ping message)')
@app_commands.checks.has_permissions(manage_channels=True)
async def resetrole(interaction: discord.Interaction):
    # Reset the role for the current guild
    guild_id = str(interaction.guild.id)
    
    if guild_id in role_data:
        del role_data[guild_id]  # Remove the role entry for the guild
        save_role_data(role_data)  # Save the updated role data
        await interaction.response.send_message("The role has been reset for this server.", ephemeral=True)
    else:
        await interaction.response.send_message("No role has been set for this server to reset.", ephemeral=True)

@bot.tree.command(name='send-now', description='Use it to send Heathcliff comic (Defaults to today) YYYY/MM/DD')
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True) # all allowed
@app_commands.checks.has_permissions()
@app_commands.choices(lang=[app_commands.Choice(name="EN", value="EN"), app_commands.Choice(name="ES", value="ES")])
async def sendnow(interaction: discord.Interaction, date: str = None, lang: str = "EN"):
    # Check for date parameter; default to today if not provided
    if date is None:
        now = datetime.utcnow()
        if lang == "ES":
            formatted_date = (now - timedelta(days=1)).strftime("%Y/%m/%d")
            await interaction.response.send_message("¡Enviando a Heathcliff!")
        else:
            formatted_date = now.strftime("%Y/%m/%d")
            await interaction.response.send_message("Sending Heathcliff!")
        
    else:
        try:
            # Try to parse the provided date
            formatted_date = datetime.strptime(date, "%Y/%m/%d").strftime("%Y/%m/%d")
            parsed_date = datetime.strptime(date, "%Y/%m/%d")
          
            

            # Check if the date is prior to the minimum date, since otherwise it will get stuck in a loop
            if parsed_date.year < 2002:
                await interaction.response.send_message("The year must be 2002 or later. Please use a later date.", ephemeral=True)
                return

            # Spanish archive starts later — enforce minimum for ES
            if lang == "ES" and parsed_date < datetime(2012, 5, 21):
                await interaction.response.send_message("Los archivos españoles solo llegan hasta el 21/05/2012. Por favor, utilice una fecha posterior.", ephemeral=True)
                return
            
            
        except ValueError:
            await interaction.response.send_message("Invalid date format. Please use YYYY/MM/DD.")
            return
        await interaction.response.send_message("Sending Heathcliff!")
    
    # Obtain the image source using the formatted date
    imgsrc = await obtainHeathcliffSource(formatted_date, lang)
    print(imgsrc)
    
    # Send the image source in a message
    await interaction.followup.send(imgsrc)
    print(f'Sent message for date: {formatted_date}')

@bot.tree.command(name='see-channel', description='Shows currently assigned channel')
@app_commands.checks.has_permissions(manage_channels=True)
async def ping_channel(interaction: discord.Interaction):
    # Retrieve the role ID from the role_data dictionary
    channel_id = channel_data.get(str(interaction.guild.id))  
    
    if channel_id:
        channel = interaction.guild.get_channel(channel_id)  
        if role:
            await interaction.response.send_message(f'Here is the channel: {channel.mention}', ephemeral=True)  
        else:
            await interaction.response.send_message("The channel set for this server no longer exists.", ephemeral=True)
    else:
        await interaction.response.send_message("No channel has been set for this server.", ephemeral=True)

bot.run(TOKEN)

if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        print("Bot has been stopped.")

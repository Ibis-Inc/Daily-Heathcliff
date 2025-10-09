import discord
from discord import app_commands
from discord.ext import tasks, commands
import os
from dotenv import load_dotenv
from datetime import datetime
import json
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from webdriver_manager.firefox import GeckoDriverManager
from lxml import html


load_dotenv()

TOKEN = os.getenv('BETA_TOKEN')  # Use environment variable for the token

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

if os.path.exists(IMAGE_SOURCE_FILE):
    with open(IMAGE_SOURCE_FILE, 'r') as f:
        image_sources = json.load(f)
else:
    image_sources = {}

def webRequest(formatted_date):
        
        url = f"https://www.gocomics.com/heathcliff/{formatted_date}" #forms the correct url to the page based upon the day

        print("beginning process to obtain image source")
        firefox_options = Options()
        firefox_options.add_argument("--headless")

        driver = webdriver.Firefox(service=Service(GeckoDriverManager().install()), options=firefox_options)
        print("started driver in headless mode")

        webelements = []
        src = ''

        while src == '':
            driver.get(url)
            print("driver got the url")
            #obtain tree and search for the source which contains the source and filters for it
            tree = html.fromstring(driver.page_source)
            print("obtained source")
            webelements = tree.xpath('/html/body/div/div/div/main/section[2]/div[2]/div/div/div/div/div/div/div/button/img/@src')
            print("requested to obtain source")
            if webelements:
                src = webelements[0]  # Assuming there's at least one result
                print("Source obtained!")
                
                # Write date and source URL to the dictionary
                image_sources[formatted_date] = src
                
                # Save the updated dictionary to the JSON file
                with open(IMAGE_SOURCE_FILE, 'w') as json_file:
                    json.dump(image_sources, json_file)
                print("Updated image sources saved to JSON file.")
            else:
                print("Failed to obtain source.")
        #write date and source url to dictionary

        print("exited while loop successfully")

        return src


def obtainHeathcliffSource(formatted_date):

    # Check if the date requested is stored in the dictionary
    datesrc = image_sources.get(formatted_date)

    if datesrc:
        src = datesrc  # Obtain source URL from the dictionary for the date
        print("Image source obtained from the dictionary.")
    else:
        src = webRequest(formatted_date)
    return src




@tasks.loop(hours=24)
async def send_daily_message():
    now = datetime.utcnow() #this is depreciated we should probably replace it
    formatted_date = now.strftime("%Y/%m/%d")
    imgsrc = webRequest(formatted_date)
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
    send_daily_message.start()

@bot.tree.command(name='ping', description='What do you think will happen')
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message('Pong!', ephemeral=True)

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
async def sendnow(interaction: discord.Interaction, date: str = None):
    # Check for date parameter; default to today if not provided
    if date is None:
        now = datetime.utcnow()
        formatted_date = now.strftime("%Y/%m/%d")
        await interaction.response.send_message("Sending Heathcliff!")
    else:
        try:
            # Try to parse the provided date
            formatted_date = datetime.strptime(date, "%Y/%m/%d").strftime("%Y/%m/%d")
            parsed_date = datetime.strptime(date, "%Y/%m/%d")

            # Check if the date is prior to the minimum date, since otherwise it will get stuck in a loop
            if parsed_date.year < 2002:
                await interaction.response.send_message("The year must be 2002 or later. Please use a valid date.", ephemeral=True)
                return
            
        except ValueError:
            await interaction.response.send_message("Invalid date format. Please use YYYY/MM/DD.")
            return
        await interaction.response.send_message("Sending Heathcliff!")
    
    # Obtain the image source using the formatted date
    imgsrc = obtainHeathcliffSource(formatted_date)
    
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

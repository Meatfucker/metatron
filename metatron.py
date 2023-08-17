from typing import Optional
import discord
from discord import app_commands
import aiohttp
import json
import asyncio
import io
import base64
from PIL import Image
import math
import re
from discord.ext import commands
from discord.ext.commands import Context
from datetime import datetime
import requests

MY_GUILD = []
SETTINGS = {}

with open("settings.cfg", "r") as settings_file:
    for line in settings_file:
        if "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key in SETTINGS:             # Check if the key already exists in SETTINGS
                if isinstance(SETTINGS[key], list):
                    SETTINGS[key].append(value)
                else:
                    SETTINGS[key] = [SETTINGS[key], value]
            else:
                SETTINGS[key] = [value]  # Always store values as a list
    #print(SETTINGS["imagesettings"][0])     #Uncomment for settings debugging.    
    
    for guild_id in SETTINGS["servers"]:
        MY_GUILD.append(discord.Object(id=guild_id))
        
class MyClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.defaultimage_payload = json.loads(SETTINGS["imagesettings"][0])
        self.defaultword_payload = json.loads(SETTINGS["wordsettings"][0])
        self.user_interaction_history = {} #Set up user LLM history variable.
    
    async def setup_hook(self): #Sync slash commands with discord servers Im on.
        for guild_obj in MY_GUILD:
            self.tree.copy_global_to(guild=guild_obj)
            await self.tree.sync(guild=guild_obj)
    
    def load_models(self): #Get list of models for user interface
        models = []
        for line in SETTINGS["models"]:
            model = line.strip().split("|")[0]
            models.append(app_commands.Choice(name=model, value=model))
        return models
    
    async def on_message(self, message): #Function that watches if bot is tagged and if it is makes a request to ooba and posts response
        if message.author == self.user: #ignores messages from ourselves for the odd edge case where the bot somehow tags or replies to itself.
            return
        if not self.user_interaction_history.get(message.author.id): #Creates a blank interaction history if it doesnt already exist.
            self.user_interaction_history[message.author.id] = []
        if self.user.mentioned_in(message):
            if "request" not in locals(): #sets up a default payload if one doesnt already exist
                request = self.defaultword_payload
            taggedmessage = re.sub(r'<[^>]+>', '', message.content) #strips The discord name from the users prompt.
            taggedmessage = taggedmessage.lstrip() #strip leading whitespace.
            request["user_input"] = taggedmessage #load the user prompt into the api payload
            user_interaction_history = self.user_interaction_history[message.author.id] # Use user-specific interaction history
            request["history"]["internal"] = user_interaction_history #Load the unique history into api payload
            request["history"]["visible"] = user_interaction_history #Load the unique history into api payload
            async with aiohttp.ClientSession() as session: #make the api request
                async with session.post(f'{SETTINGS["wordapi"][0]}/api/v1/chat', json=request) as response:
                    if response.status == 200:
                        result = await response.json()
                        #print(json.dumps(result, indent=1)) #uncomment for debugging console data
                        last_visible_index = len(result["results"][0]["history"]["visible"]) - 1 #find how long the history is and get the place of the last message in it, which is our reply
                        processedreply = result["results"][0]["history"]["visible"][last_visible_index][1] #load said reply
                        new_entry = [taggedmessage, processedreply] #prepare entry to be placed into the users history
                        await message.channel.send(f"{message.author.mention} {processedreply}") #send message to channel
                        user_interaction_history.append(new_entry) #update user history
                        if len(user_interaction_history) > 6: #if history is at max size, dump oldest result
                            user_interaction_history.pop(0)
            print(f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | wordgen  | {message.author.name}:{message.author.id} | {message.guild}:{message.channel} | {taggedmessage}') #print to console for logging
                
    async def generate_image(self, payload): #image generation api call
            async with aiohttp.ClientSession() as session:
                async with session.post(f'{SETTINGS["imageapi"][0]}/sdapi/v1/txt2img', json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        if "images" in data: #Tile and compile images into grid.
                            image_list = []
                            for i in data['images']:
                                image_bytes = io.BytesIO(base64.b64decode(i.split(",", 1)[0])) #decode base64 into images
                                image = Image.open(image_bytes)
                                image_list.append(image)
                            width, height = image_list[0].size
                            num_images_per_row = math.ceil(math.sqrt(len(image_list))) #math stuff I googled, fuck if I know, it works.
                            num_rows = math.ceil(len(image_list) / num_images_per_row) #figure out how many rows
                            composite_width = num_images_per_row * width #find exact width of final image
                            composite_height = num_rows * height #find exact height of final image
                            composite_image = Image.new('RGB', (composite_width, composite_height)) #make blank canvas the side of our grid
                            for idx, image in enumerate(image_list): #place images in grid
                                row = idx // num_images_per_row
                                col = idx % num_images_per_row
                                composite_image.paste(image, (col * width, row * height))
                            composite_image_bytes = io.BytesIO() # Convert the composite image to bytes and encode to base64
                            composite_image.save(composite_image_bytes, format='PNG') #this makes it bytes
                            composite_image_base64 = base64.b64encode(composite_image_bytes.getvalue()).decode() #this makes it base64 
                            png_payload = {"image": "data:image/png;base64," + composite_image_base64} #prepare image for posting to discord
                            composite_image_bytes.seek(0) #go to the beginning of your bytes
                            return composite_image_bytes
                    else:
                        return None
    
intents = discord.Intents.all() #discord intents
client = MyClient(intents=intents) #client intents
class Imagegenbuttons(discord.ui.View): #class for the ui buttons on the image gens
    
    def __init__(self, payload, user_id, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.payload = payload
            self.userid = user_id
    
    @discord.ui.button(label='Reroll', emoji="🎲", style=discord.ButtonStyle.grey)
    async def reroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer() #this makes it not say "interaction failed" when things take a long time
        async with aiohttp.ClientSession() as session: #Check what the currently loaded model is, and then load the appropriate default prompt and negatives.
            async with session.get(f'{SETTINGS["imageapi"][0]}/sdapi/v1/options') as response: #Api request to get the current model.
                response_data = await response.json()
                currentmodel = response_data.get("sd_model_checkpoint", "")  # Extract current model checkpoint value
        composite_image_bytes = await client.generate_image(self.payload) #generate image and place it into composite_image_bytes
        await interaction.followup.send(content=f"Prompt: **`{self.payload['prompt']}`**, Negatives: `{self.payload['negative_prompt']}` Model: `{currentmodel}`", file=discord.File(composite_image_bytes, filename='composite_image.png'), view=Imagegenbuttons(self.payload, interaction.user.id))
        print(f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | Reroll   | {interaction.user.name}:{interaction.user.id} | {interaction.guild}:{interaction.channel} | P={self.payload["prompt"]} | N={self.payload["negative_prompt"]} | M={currentmodel}')
    
    @discord.ui.button(label='Mail', emoji="✉", style=discord.ButtonStyle.grey)
    async def dmimage(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer() #ensure we dont get the interaction failed message if it takes too long to respond
        async with aiohttp.ClientSession() as session:
            async with session.get(interaction.message.attachments[0].url) as response:
                if response.status == 200:
                    image_bytes = await response.read()
                    dm_channel = await interaction.user.create_dm()
                    await dm_channel.send(file=discord.File(io.BytesIO(image_bytes), filename='composite_image.png'))
                    print(f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | DM Image | {interaction.user.name}:{interaction.user.id} | {interaction.guild}:{interaction.channel} | {interaction.message.attachments[0].url}') 
                else:
                    await interaction.response.send_message("Failed to fetch the image.")
    
    @discord.ui.button(label='Delete', emoji="❌", style=discord.ButtonStyle.grey)
    async def delete_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.userid == interaction.user.id:
            await interaction.response.defer()
            await interaction.message.delete()
            print(f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | Delete   | {interaction.user.name}:{interaction.user.id} | {interaction.guild}:{interaction.channel} | {interaction.id}')

@client.event
async def on_ready():
    print(f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | Logged in as {client.user} (ID: {client.user.id})') #Tell console login was successful

@client.tree.command() #Begins imagen slash command stuff 
@app_commands.describe(usermodel="Choose the model")
@app_commands.describe(userprompt="Describe what you want to gen")
@app_commands.describe(usernegative="Enter things you dont want in the gen")
@app_commands.choices(usermodel=client.load_models())  # Use the loaded models as choices

async def imagegen(interaction: discord.Interaction, userprompt: str, usernegative: Optional[str] = None, usermodel: Optional[app_commands.Choice[str]] = None):
    await interaction.response.send_message("Nightmare incoming...", ephemeral=True, delete_after=10) #respond so discord doesnt get mad it takes a long time to actually respond to the message
    payload = client.defaultimage_payload.copy() #set up default payload 
    negative_values = [neg.strip() for neg in payload["negative_prompt"].split(",")] # Split negative values into a list
    for neg in negative_values: # Remove negative values from userprompt if they match
        userprompt = userprompt.replace(neg, '')
    payload["prompt"] = userprompt.strip() #put the prompt into the payload
    if usernegative is not None:
        payload["negative_prompt"] += usernegative #Add the user negative to the existing negative payload
    if usermodel is not None: #Check the user models choice if present
        pattern = r"value='(.*?)'" #regex to strip unneed chars
        matches = re.findall(pattern, str(usermodel)) #convert the data to string and then run the regex on it
        model_payload = {"sd_model_checkpoint": matches[0]} #put model choice into payload
        async with aiohttp.ClientSession() as session: #make the api request to change to the requested model
            async with session.post(f'{SETTINGS["imageapi"][0]}/sdapi/v1/options', json=model_payload) as response:
                response_data = await response.json()
    async with aiohttp.ClientSession() as session: #Check what the currently loaded model is, and then load the appropriate default prompt and negatives.
        async with session.get(f'{SETTINGS["imageapi"][0]}/sdapi/v1/options', json=payload) as response: #Api request to get the current model.
            response_data = await response.json()
            currentmodel = response_data.get("sd_model_checkpoint", "")  # Extract current model checkpoint value
            for line in SETTINGS["models"]:
                model, modeltemp, modelnegtemp = line.strip().split("|", 2)  #grab the second and third values and put them into variables
                if model == currentmodel: #find the matching model and load the model default positive and negative prompts
                    modelprompt = modeltemp
                    modelnegative = modelnegtemp
            if modelprompt: #Combine the model defaults with the user choices and update payload
                payload["prompt"] = f"{modelprompt},{payload['prompt']}"
            if modelnegative:
                payload["negative_prompt"] = f"{modelnegative},{payload['negative_prompt']}"
    composite_image_bytes = await client.generate_image(payload) #generate image and place it into composite_image_bytes
    if composite_image_bytes is not None:
        view = Imagegenbuttons(payload, interaction.user.id)
        await interaction.followup.send(content=f"Prompt: **`{userprompt}`**, Negatives: `{usernegative}` Model: `{currentmodel}`", file=discord.File(composite_image_bytes, filename='composite_image.png'), view=Imagegenbuttons(payload, interaction.user.id)) #Send message to discord with the image and request parameters
    else:
        await interaction.followup.send("API failed")
    print(f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | imagegen | {interaction.user.name}:{interaction.user.id} | {interaction.guild}:{interaction.channel} | P={payload["prompt"]}, N={payload["negative_prompt"]}, M={currentmodel}') #Print request to console

client.run(SETTINGS["token"][0]) #run bot.
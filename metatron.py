from typing import Optional
import discord
from discord import app_commands
from discord import ui
import aiohttp
import json
import asyncio
import io
import base64
from PIL import Image
import math
import re
from datetime import datetime
import requests
from sumy.parsers.html import HtmlParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lex_rank import LexRankSummarizer as Summarizer
from sumy.nlp.stemmers import Stemmer
from sumy.utils import get_stop_words
import logging
import sys
import random
import os
logging.getLogger('PIL').setLevel(logging.WARNING) #This fixes a bug in PIL thatll fill the logging full of trash otherwise
logging.basicConfig(filename='bot.log', level=logging.DEBUG, format='%(message)s') #log to this file.
console_handler = logging.StreamHandler(sys.stdout) 
console_handler.setLevel(logging.DEBUG)
console_formatter = logging.Formatter('%(message)s')
console_handler.setFormatter(console_formatter)
logging.getLogger().addHandler(console_handler)

MY_GUILD = []
SETTINGS = {}

with open("settings.cfg", "r") as settings_file: #this builds the SETTINGS variable.
    for line in settings_file:
        if "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key in SETTINGS:             # Check if the key already exists in SETTINGS
                if isinstance(SETTINGS[key], list): SETTINGS[key].append(value)
                else: SETTINGS[key] = [SETTINGS[key], value]
            else: SETTINGS[key] = [value]  # Always store values as a list
    logging.debug(f'DEBUG SETTINGS BEGIN: {SETTINGS}') if SETTINGS["debug"][0] == "True" else None
    for guild_id in SETTINGS["servers"]:
        MY_GUILD.append(discord.Object(id=guild_id))
        
class MyClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.defaultimage_payload = json.loads(SETTINGS["imagesettings"][0])
        self.defaultword_payload = json.loads(SETTINGS["wordsettings"][0])
        self.user_interaction_history = {} #Set up user LLM history variable.
        self.models = []
        self.loras = []
            
    async def setup_hook(self): #Sync slash commands with discord servers Im on.
        await client.load_models()
        await client.load_loras()
        for guild_obj in MY_GUILD:
            self.tree.copy_global_to(guild=guild_obj)
            await self.tree.sync(guild=guild_obj)
    
    async def load_models(self): #Get list of models for user interface
        async with aiohttp.ClientSession() as session: 
            async with session.get(f'{SETTINGS["imageapi"][0]}/sdapi/v1/sd-models') as response:
                response_data = await response.json()
                for title in response_data:
                    self.models.append(app_commands.Choice(name=title["title"], value=title["title"]))
        return self.models
        
    async def load_loras(self): #Get list of loras for user interface
        async with aiohttp.ClientSession() as session: 
            async with session.get(f'{SETTINGS["imageapi"][0]}/sdapi/v1/loras') as response:
                response_data = await response.json()
                for name in response_data:
                    self.loras.append(app_commands.Choice(name=name["name"], value=name["name"]))
        return self.loras
    
    async def on_message(self, message): #Function that watches if bot is tagged and if it is makes a request to ooba and posts response
        if message.author == self.user: return #ignores messages from ourselves for the odd edge case where the bot somehow tags or replies to itself.
        banned_users = SETTINGS["bannedusers"][0].split(',')
        if str(message.author.id) in banned_users:
            return  # Exit the function if the author is banned
        if not self.user_interaction_history.get(message.author.id): self.user_interaction_history[message.author.id] = [] #Creates a blank interaction history if it doesnt already exist.
        if self.user.mentioned_in(message):
            if SETTINGS["enableword"][0] != "True":
                await message.channel.send("LLM generation is currently disabled.")
                return
            async with message.channel.typing():
                if "request" not in locals(): #sets up a default payload if one doesnt already exist
                    request = self.defaultword_payload
                taggedmessage = re.sub(r'<[^>]+>', '', message.content) #strips The discord name from the users prompt.
                taggedmessage = taggedmessage.lstrip() #strip leading whitespace.
                url_pattern = r'(https?://[^\s]+)'
                urls = re.findall(url_pattern, taggedmessage) #check messages for urls.
                if SETTINGS["enableurls"][0] == "True":
                    for url in urls:
                        extracted_text = await self.extract_text_from_url(url)
                        taggedmessage = (f'{taggedmessage}. {extracted_text}')
                    if message.attachments:
                        url = message.attachments[0].url
                        extracted_text = await self.extract_text_from_url(url)
                        taggedmessage = (f'{taggedmessage}. {extracted_text}')
                request["user_input"] = taggedmessage #load the user prompt into the api payload
                user_interaction_history = self.user_interaction_history[message.author.id] # Use user-specific interaction history
                request["history"]["internal"] = user_interaction_history #Load the unique history into api payload
                request["history"]["visible"] = user_interaction_history #Load the unique history into api payload
                logging.debug(f'DEBUG WORD PAYLOAD BEGIN: {json.dumps(request, indent=1)}') if SETTINGS["debug"][0] == "True" else None
                async with aiohttp.ClientSession() as session: #make the api request
                    async with session.post(f'{SETTINGS["wordapi"][0]}/api/v1/chat', json=request) as response:
                        if response.status == 200:
                            #async with message.channel.typing():
                                result = await response.json()
                                logging.debug(f'DEBUG WORD PAYLOAD RESPONSE BEGIN: {json.dumps(result, indent=1)}') if SETTINGS["debug"][0] == "True" else None
                                last_visible_index = len(result["results"][0]["history"]["internal"]) - 1 #find how long the history is and get the place of the last message in it, which is our reply
                                processedreply = result["results"][0]["history"]["internal"][last_visible_index][1] #load said reply
                                new_entry = [taggedmessage, processedreply] #prepare entry to be placed into the users history
                                await message.channel.send(f"{message.author.mention} {processedreply}") #send message to channel
                                user_interaction_history.append(new_entry) #update user history
                                if len(user_interaction_history) > 10: #if history is at max size, dump oldest result
                                    user_interaction_history.pop(0)
            logging.info(f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | wordgen  | {message.author.name}:{message.author.id} | {message.guild}:{message.channel} | {taggedmessage}') 
                
    async def generate_image(self, payload): #image generation api call
            logging.debug(f'DEBUG IMAGE PAYLOAD BEGIN: {payload}') if SETTINGS["debug"][0] == "True" else None
            async with aiohttp.ClientSession() as session:
                async with session.post(f'{SETTINGS["imageapi"][0]}/sdapi/v1/txt2img', json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        logging.debug(f'DEBUG IMAGE RESPONSE BEGIN: {response}') if SETTINGS["debug"][0] == "True" else None
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
                            composite_image_bytes = io.BytesIO() # load the composite image from bytes
                            composite_image.save(composite_image_bytes, format='PNG') #this turns the bytes into png
                            if SETTINGS["saveimages"][0] == "True": 
                                current_datetime = datetime.now()
                                current_datetime_str = current_datetime.strftime("%Y-%m-%d_%H-%M-%S") #This removes chars that cant be filenames
                                pattern = r'[\/:*?"<>|]'
                                sanitized_prompt = re.sub(pattern, '', payload["prompt"]) #this removes chars that cant be filenames
                                basepath = f'{SETTINGS["savepath"][0]}/{current_datetime_str}-{sanitized_prompt}'
                                truncatedpath = basepath[:200]
                                imagesavepath = f'{truncatedpath}.png'
                                with open(imagesavepath, "wb") as output_file:
                                    output_file.write(composite_image_bytes.getvalue()) #saves the gen to disk
                            composite_image_bytes.seek(0) #go to the beginning of your bytes
                            return composite_image_bytes
                    else: return None
                   
    async def extract_text_from_url(self, url): #This function takes a url and returns a description of either the webpage or the picture.
        response = requests.head(url)
        if 'image' in response.headers.get('content-type'):
            image_response = requests.get(url)
            if image_response.status_code == 200:
                image = Image.open(io.BytesIO(image_response.content)) # Convert the image to PNG
                png_image = io.BytesIO()
                image.save(png_image, format='PNG')
                png_image_base64 = base64.b64encode(png_image.getvalue()).decode('utf-8') # Convert the image to base64
                png_payload = {"image": "data:image/png;base64," + png_image_base64}
                async with aiohttp.ClientSession() as session: #make the BLIP interrogate API call
                    async with session.post(f'{SETTINGS["imageapi"][0]}/sdapi/v1/interrogate', json=png_payload) as response:
                        if response.status == 200:
                            data = await response.json()
                            cleaneddescription = data["caption"].split(",")[0].strip()
                            photodescription = (f'The URL is a picture of the following topics: {cleaneddescription}')
                            return photodescription
        else:
            parser = HtmlParser.from_url(url, Tokenizer("english")) 
            stemmer = Stemmer("english")
            summarizer = Summarizer(stemmer)
            summarizer.stop_words = get_stop_words("english") #sumy summarizer setup stuff
            compileddescription = ""
            for sentence in summarizer(parser.document, 4):
                compileddescription = (f' {compileddescription} {sentence}')
            sitedescription = (f'The URL is a website about the following:{compileddescription}')
            return sitedescription
 
intents = discord.Intents.all() #discord intents
client = MyClient(intents=intents) #client intents

class Imagegenbuttons(discord.ui.View): #class for the ui buttons on the image gens
    
    def __init__(self, payload, user_id, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.payload = payload
            self.userid = user_id
            self.timeout = None
    
    @discord.ui.button(label='Edit', emoji="✏️", style=discord.ButtonStyle.grey)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(Editpromptmodal(self.payload)) #calls the edit modal
        
    @discord.ui.button(label='Reroll', emoji="🎲", style=discord.ButtonStyle.grey)
    async def reroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer() #this makes it not say "interaction failed" when things take a long time
        composite_image_bytes = await client.generate_image(self.payload) #generate image and place it into composite_image_bytes
        await interaction.followup.send(content=f"Reroll", file=discord.File(composite_image_bytes, filename='composite_image.png'), view=Imagegenbuttons(self.payload, interaction.user.id))
        logging.info(f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | Reroll   | {interaction.user.name}:{interaction.user.id} | {interaction.guild}:{interaction.channel} | P={self.payload["prompt"]}')
    
    @discord.ui.button(label='Mail', emoji="✉", style=discord.ButtonStyle.grey)
    async def dmimage(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer() #ensure we dont get the interaction failed message if it takes too long to respond
        async with aiohttp.ClientSession() as session:
            async with session.get(interaction.message.attachments[0].url) as response:
                if response.status == 200:
                    image_bytes = await response.read()
                    dm_channel = await interaction.user.create_dm()
                    await dm_channel.send(file=discord.File(io.BytesIO(image_bytes), filename='composite_image.png'))
                    logging.info(f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | DM Image | {interaction.user.name}:{interaction.user.id} | {interaction.guild}:{interaction.channel} | {interaction.message.attachments[0].url}') 
                else: await interaction.response.send_message("Failed to fetch the image.")
    
    @discord.ui.button(label='Delete', emoji="❌", style=discord.ButtonStyle.grey)
    async def delete_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.userid == interaction.user.id:
            await interaction.message.delete()
            logging.info(f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | Delete   | {interaction.user.name}:{interaction.user.id} | {interaction.guild}:{interaction.channel} | {interaction.id}')

class Editpromptmodal(discord.ui.Modal, title='Edit Prompt'): #prompt editing modal.
    def __init__(self, payload, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.payload = payload
        self.timeout = None
        self.add_item(discord.ui.TextInput(label="Prompt", default=self.payload["prompt"], required=True, style=discord.TextStyle.long))
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        newprompt = str(self.children[0])
        negative_values = [neg.strip() for neg in self.payload["negative_prompt"].split(",")] # Split negative values into a list
        for neg in negative_values: # Remove negative values from userprompt if they match
            newprompt = newprompt.replace(neg, '')
        self.payload["prompt"] = newprompt
        logging.debug(f'DEBUG EDIT PAYLOAD BEGIN: {self.payload}') if SETTINGS["debug"][0] == "True" else None
        composite_image_bytes = await client.generate_image(self.payload) #make the api call to generate the new image
        await interaction.followup.send(content=f'Edit: New prompt `{newprompt}`', file=discord.File(composite_image_bytes, filename='composite_image.png'), view=Imagegenbuttons(self.payload, interaction.user.id))
        logging.info(f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | Edit     | {interaction.user.name}:{interaction.user.id} | {interaction.guild}:{interaction.channel} | P={self.payload["prompt"]}')
     
@client.event
async def on_ready():
    logging.info(f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | Logged in as {client.user} (ID: {client.user.id})') #Tell console login was successful

@client.tree.command() #Begins imagen slash command stuff 
@app_commands.describe(usermodel="Choose the model", userprompt="Describe what you want to gen", userbatch="Batch Size", usernegative="Enter things you dont want in the gen", userseed="Seed", usersteps="Number of steps", userlora="Pick a LORA", userwidth="Image width", userheight="Image height")
@app_commands.choices(usermodel=client.models)  # Use the loaded models as choices
@app_commands.choices(userlora=client.loras)
async def imagegen(interaction: discord.Interaction, userprompt: str, usernegative: Optional[str] = None, usermodel: Optional[app_commands.Choice[str]] = None, userlora: Optional[app_commands.Choice[str]] = None, userbatch: Optional[int] = None, userseed: Optional[int] = None, usersteps: Optional[int] = None, userheight: Optional[int] = None, userwidth: Optional[int] = None):
    if SETTINGS["enableimage"][0] != "True":
            await interaction.response.send_message("Image generation is currently disabled.")
            return
    banned_users = SETTINGS["bannedusers"][0].split(',')
    if str(interaction.user.id) in banned_users:
            return  # Exit the function if the author is banned
    await interaction.response.defer() #respond so discord doesnt get mad it takes a long time to actually respond to the message
    payload = client.defaultimage_payload.copy() #set up default payload 
    negative_values = [neg.strip() for neg in payload["negative_prompt"].split(",")] # Split negative values into a list
    ignore_fields = [field.strip() for field in SETTINGS["ignorefields"][0].split(",")]  # Split ignored fields into a list
    for neg in negative_values: # Remove negative values from userprompt if they match
        userprompt = userprompt.replace(neg, '')
    payload["prompt"] = userprompt.strip() #put the prompt into the payload
    if usernegative is not None:
        if "usernegative" not in ignore_fields: payload["negative_prompt"] = f"{usernegative},{payload['negative_prompt']}" 
        else: usernegative = None #These checks allow us to ignore fields if we wish.
    if userbatch is not None:
        if "userbatch" not in ignore_fields:
             if userbatch <= int(SETTINGS["maxbatch"][0]):
                payload["batch_size"] = userbatch
        else: userbatch = None
    if userseed is not None:
        if "userseed" not in ignore_fields: payload["seed"] = userseed
        else: userseed = None
    if usersteps is not None:
        if "usersteps" not in ignore_fields: payload["steps"] = usersteps
        else: usersteps = None
    if userwidth is not None:
        if "userwidth" not in ignore_fields: 
            if userwidth <= int(SETTINGS["maxwidth"][0]):
                payload["width"] = userwidth
    if userheight is not None:
        if "userheight" not in ignore_fields: 
            if userheight <= int(SETTINGS["maxheight"][0]):
                payload["height"] = userheight
    if userlora is not None:
        if "userlora" not in ignore_fields:
            pattern = r"value='(.*?)'" #regex to strip unneed chars
            matches = re.findall(pattern, str(userlora))
            currentlora = matches[0]
            payload["prompt"] = f"<lora:{matches[0]}:1>,{payload['prompt']}"
        else: 
            userlora = None
    else: currentlora = None
    if usermodel is not None: #Check the user models choice if present
        if "usermodel" not in ignore_fields:  
            pattern = r"value='(.*?)'" #regex to strip unneed chars
            matches = re.findall(pattern, str(usermodel)) #convert the data to string and then run the regex on it
            model_payload = {"sd_model_checkpoint": matches[0]} #put model choice into payload
            async with aiohttp.ClientSession() as session: #make the api request to change to the requested model
                async with session.post(f'{SETTINGS["imageapi"][0]}/sdapi/v1/options', json=model_payload) as response:
                    response_data = await response.json()
                    logging.debug(f'USERMODEL DEBUG RESPONSE: {response_data}') if SETTINGS["debug"][0] == "True" else None
        else: usermodel = None
    else:
        model_payload = None
        for default_model in SETTINGS["defaultmodel"]: #This loads the server specific default model if it exists
            #checkid, default_model_values = default_model.split(',', 2)
            checkid, defaultmodelname, defaultmodelprompt, defaultmodelneg = default_model.strip().split("|", 3)  #grab the second and third values and put them into variables
            if str(interaction.channel.id) == checkid:
                model_payload = {"sd_model_checkpoint": defaultmodelname}
                payload["prompt"] = f"{defaultmodelprompt},{payload['prompt']}"
                payload["negative_prompt"] = f"{defaultmodelneg},{payload['negative_prompt']}"
                break
            elif str(interaction.guild.id) == checkid:
                model_payload = {"sd_model_checkpoint": defaultmodelname}
                payload["prompt"] = f"{defaultmodelprompt},{payload['prompt']}"
                payload["negative_prompt"] = f"{defaultmodelneg},{payload['negative_prompt']}"
        if model_payload:
            async with aiohttp.ClientSession() as session: #make the api request to change to the requested model
                async with session.post(f'{SETTINGS["imageapi"][0]}/sdapi/v1/options', json=model_payload) as response:
                    response_data = await response.json()
                    logging.debug(f'DEFAULTMODEL DEBUG RESPONSE: {response_data}') if SETTINGS["debug"][0] == "True" else None
    
    async with aiohttp.ClientSession() as session: #Check what the currently loaded model is, and then load the appropriate default prompt and negatives.
        async with session.get(f'{SETTINGS["imageapi"][0]}/sdapi/v1/options', json=payload) as response: #Api request to get the current model.
            response_data = await response.json()
            currentmodel = response_data.get("sd_model_checkpoint", "")  # Extract current model checkpoint value
            modelprompt = ""
            modelnegative = ""
            for line in SETTINGS["models"]:
                model, modeltemp, modelnegtemp = line.strip().split("|", 2)  #grab the second and third values and put them into variables
                if model == currentmodel: #find the matching model and load the model default positive and negative prompts
                    modelprompt = modeltemp
                    modelnegative = modelnegtemp
            if modelprompt: payload["prompt"] = f"{modelprompt},{payload['prompt']}" #Combine the model defaults with the user choices and update payload
            if modelnegative: payload["negative_prompt"] = f"{modelnegative},{payload['negative_prompt']}"
    composite_image_bytes = await client.generate_image(payload) #generate image and place it into composite_image_bytes
    if composite_image_bytes is not None:
        view = Imagegenbuttons(payload, interaction.user.id)
        await interaction.followup.send(content=f"Prompt: **`{userprompt}`**, Negatives: `{usernegative}` Model: `{currentmodel}` Lora: `{currentlora}` Seed `{userseed}` Batch Size `{userbatch}` Steps `{usersteps}`", file=discord.File(composite_image_bytes, filename='composite_image.png'), view=Imagegenbuttons(payload, interaction.user.id)) #Send message to discord with the image and request parameters
    else: await interaction.followup.send("API failed")
    logging.info(f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | imagegen | {interaction.user.name}:{interaction.user.id} | {interaction.guild}:{interaction.channel} | P={payload["prompt"]}, N={usernegative}, M={currentmodel} L={currentlora}') 

@client.tree.command()
async def speakgen(interaction: discord.Interaction, userprompt: str):
    await interaction.response.defer()
    async with aiohttp.ClientSession() as session: 
        params = {'inputstring': userprompt}
        async with session.get(f'{SETTINGS["speakapi"][0]}/txt2wav', params=params) as response: 
            response_data = await response.read()
            
            if response_data:
                wav_bytes_io = io.BytesIO(response_data)
                await interaction.followup.send(file=discord.File(wav_bytes_io, filename=f"{userprompt}.wav"))
                logging.info(f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | speakgen | {interaction.user.name}:{interaction.user.id} | {interaction.guild}:{interaction.channel} | P={userprompt}') 
client.run(SETTINGS["token"][0]) #run bot.

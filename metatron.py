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
import coloredlogs
from termcolor import colored

class CustomLogFormatter(logging.Formatter):
    def format(self, record):
        message = super().format(record)
        return re.sub(r'\x1b\[[0-9;]*[mK]', '', message)
        
coloredlogs.install(level='DEBUG', fmt='%(message)s', logger=logging.getLogger())
logging.getLogger('PIL').setLevel(logging.WARNING) #Suppress noisy PIL logging
logging.getLogger('urllib3').setLevel(logging.WARNING) #same but for urllib
logging.getLogger('discord').setLevel(logging.INFO)
logging.getLogger('asyncio').setLevel(logging.WARNING)
file_handler = logging.FileHandler('bot.log')
file_handler.setLevel(logging.DEBUG)
file_formatter = CustomLogFormatter('%(message)s')
file_handler.setFormatter(file_formatter)
logging.getLogger().addHandler(file_handler)

SETTINGS = {}
concurrent_requests_per_user = {}

with open("settings.cfg", "r") as settings_file: #this builds the SETTINGS variable.
    for line in settings_file:
        if "=" in line:
            key, value = (line.split("=", 1)[0].strip(), line.split("=", 1)[1].strip())
            if key in SETTINGS:             # Check if the key already exists in SETTINGS
                if isinstance(SETTINGS[key], list): SETTINGS[key].append(value)
                else: SETTINGS[key] = [SETTINGS[key], value]
            else: SETTINGS[key] = [value]  # Always store values as a list
    logging.debug(f'DEBUG SETTINGS BEGIN: {colored(json.dumps(SETTINGS, indent=1), "light_blue")}') if SETTINGS["debug"][0] == "True" else None
          
class MyClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.defaultimage_payload = json.loads(SETTINGS["imagesettings"][0])
        self.defaultword_payload = json.loads(SETTINGS["wordsettings"][0])
        self.user_interaction_history = {} #Set up user LLM history variable.
        self.models = []
        self.loras = []
        self.voices = []
            
    async def setup_hook(self): #Sync slash commands with discord servers Im on.
        await client.load_models()
        await client.load_loras()
        await client.load_voices()
        await self.tree.sync()
        
    async def on_ready(self):
        logging.info(f'{colored(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "dark_grey")} | {colored("login", "cyan")}    | {colored(client.user, "yellow")}, {colored(client.user.id, "light_yellow")}') #Tell console login was successful
    
    async def load_models(self): #Get list of models for user interface
        if SETTINGS["enableimage"][0] == "True":
            async with aiohttp.ClientSession() as session: 
                async with session.get(f'{SETTINGS["imageapi"][0]}/sdapi/v1/sd-models') as response:
                    response_data = await response.json()
                    for title in response_data:
                        self.models.append(app_commands.Choice(name=title["title"], value=title["title"]))
            return self.models
           
    async def load_loras(self): #Get list of loras for user interface
        if SETTINGS["enableimage"][0] == "True":
            async with aiohttp.ClientSession() as session: 
                async with session.get(f'{SETTINGS["imageapi"][0]}/sdapi/v1/loras') as response:
                    response_data = await response.json()
                    for name in response_data:
                        self.loras.append(app_commands.Choice(name=name["name"], value=name["name"]))
            return self.loras
    
    async def load_voices(self): #Get list of voices for user interface
        if SETTINGS["enablespeak"][0] == "True":
            async with aiohttp.ClientSession() as session: 
                async with session.get(f'{SETTINGS["speakapi"][0]}/voices') as response:
                    response_data = await response.json()
                    voices_list = response_data.get('voices', [])
                    for voice in voices_list:
                        self.voices.append(app_commands.Choice(name=voice, value=voice))
                    self.voices.append(app_commands.Choice(name="Base voice", value="None"))
            return self.voices
    
    async def on_message(self, message): #Function that watches if bot is tagged and if it is makes a request to ooba and posts response
        if message.author == self.user: return #ignores messages from ourselves for the odd edge case where the bot somehow tags or replies to itself.
        if str(message.author.id) in SETTINGS.get("bannedusers", [""])[0].split(','): return  # Exit the function if the author is banned
        if not self.user_interaction_history.get(message.author.id): self.user_interaction_history[message.author.id] = [] #Creates a blank interaction history if it doesnt already exist.
        user_interaction_history = self.user_interaction_history[message.author.id] # Use user-specific interaction history
        if self.user.mentioned_in(message):
            if SETTINGS["enableword"][0] != "True": await message.channel.send("LLM generation is currently disabled."); return #check if LLM generation is enabled
            async with message.channel.typing(): #Put the "typing...." discord status up
                request = request if "request" in locals() else self.defaultword_payload #set up default payload request if it doesnt exist
                request["history"]["internal"] = request["history"]["visible"] = user_interaction_history #Load user interaction history into payload
                taggedmessage = re.sub(r'<[^>]+>', '', message.content).lstrip() #strips The discord name from the users prompt.
                processedmessage = taggedmessage
                if processedmessage == "forget":
                    self.user_interaction_history[message.author.id] = []
                    await message.channel.send("History wiped")
                    logging.info(f'{colored(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "dark_grey")} | {colored("forget", "cyan")}   | {colored(message.author.name, "yellow")}:{colored(message.author.id, "light_yellow")} | {colored(message.guild, "red")}:{colored(message.channel, "light_red")}') 
                    return
                if SETTINGS["enableurls"][0] == "True":
                    urls = re.findall(r'(https?://[^\s]+)', processedmessage)  # Check messages for URLs.
                    for url in urls:
                        extracted_text = await self.extract_text_from_url(url)
                        processedmessage = (f'{processedmessage}. {extracted_text}')
                    for attachment in message.attachments:
                        extracted_text = await self.extract_text_from_url(attachment.url)
                        processedmessage = f'{processedmessage}. {extracted_text}'
                    request["user_input"] = processedmessage #load the user prompt into the api payload
                else: request["user_input"] = taggedmessage #load the user prompt into the api payload
                logging.debug(f'DEBUG WORD PAYLOAD BEGIN: {colored(json.dumps(request, indent=1), "light_blue")}') if SETTINGS["debug"][0] == "True" else None
                async with aiohttp.ClientSession() as session: #make the api request
                    async with session.post(f'{SETTINGS["wordapi"][0]}/api/v1/chat', json=request) as response:
                        if response.status == 200:
                                result = await response.json()
                                logging.debug(f'DEBUG WORD PAYLOAD RESPONSE BEGIN: {colored(json.dumps(result, indent=1), "light_blue")}') if SETTINGS["debug"][0] == "True" else None
                                processedreply = result["results"][0]["history"]["internal"][-1][1] #load said reply
                                new_entry = [taggedmessage, processedreply] #prepare entry to be placed into the users history
                                user_interaction_history.append(new_entry) #update user history
                                if len(user_interaction_history) > 10: user_interaction_history.pop(0) #remove oldest result in history once maximum is reached
                                await message.channel.send(f"{message.author.mention} {processedreply}") #send message to channel                                
            logging.info(f'{colored(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "dark_grey")} | {colored("wordgen", "cyan")}  | {colored(message.author.name, "yellow")}:{colored(message.author.id, "light_yellow")} | {colored(message.guild, "red")}:{colored(message.channel, "light_red")} | {colored(taggedmessage, "light_magenta")}') 
                
    async def generate_image(self, payload, user_id): #image generation api call
            if user_id in concurrent_requests_per_user and concurrent_requests_per_user[user_id] >= int(SETTINGS["maxrequests"][0]): return None  # User has reached the limit, do not allow another request
            concurrent_requests_per_user[user_id] = concurrent_requests_per_user.get(user_id, 0) + 1    
            try:
                logging.debug(f'DEBUG IMAGE PAYLOAD BEGIN: {colored(json.dumps(payload, indent=1), "light_blue")}') if SETTINGS["debug"][0] == "True" else None
                async with aiohttp.ClientSession() as session:
                    async with session.post(f'{SETTINGS["imageapi"][0]}/sdapi/v1/txt2img', json=payload) as response:
                        if response.status == 200:
                            data = await response.json()
                            logging.debug(f'DEBUG IMAGE RESPONSE BEGIN: {colored(response, "light_blue")}') if SETTINGS["debug"][0] == "True" else None
                            if "images" in data: # Tile and compile images into a grid
                                image_list = [Image.open(io.BytesIO(base64.b64decode(i.split(",", 1)[0])) ) for i in data['images']]
                                width, height = image_list[0].size
                                num_images_per_row = math.ceil(math.sqrt(len(image_list)))
                                num_rows = math.ceil(len(image_list) / num_images_per_row)
                                composite_width = num_images_per_row * width
                                composite_height = num_rows * height
                                composite_image = Image.new('RGB', (composite_width, composite_height))
                                for idx, image in enumerate(image_list):
                                    row, col = divmod(idx, num_images_per_row)
                                    composite_image.paste(image, (col * width, row * height))
                                composite_image_bytes = io.BytesIO()
                                composite_image.save(composite_image_bytes, format='PNG')
                                if SETTINGS["saveimages"][0] == "True": 
                                    current_datetime_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                                    sanitized_prompt = re.sub(r'[\/:*?"<>|]', '', payload["prompt"])
                                    basepath = f'{SETTINGS["savepath"][0]}/{current_datetime_str}-{sanitized_prompt}'
                                    truncatedpath = basepath[:200]
                                    imagesavepath = f'{truncatedpath}.png'
                                    with open(imagesavepath, "wb") as output_file:
                                        output_file.write(composite_image_bytes.getvalue())
                                composite_image_bytes.seek(0)
                        else: return None
            finally: # Decrement the count of concurrent requests for the user
                if user_id in concurrent_requests_per_user: concurrent_requests_per_user[user_id] -= 1
            return composite_image_bytes
                   
    async def extract_text_from_url(self, url): #This function takes a url and returns a description of either the webpage or the picture.
        response = requests.head(url)
        if 'content-type' in response.headers:
            if 'image' in response.headers.get('content-type'):
                image_response = requests.get(url)
                if image_response.status_code == 200:
                    image = Image.open(io.BytesIO(image_response.content))
                    if SETTINGS["multimodal"][0] == "True":
                        image = image.convert('RGB')
                        jpg_buffer = io.BytesIO()
                        image.save(jpg_buffer, format='JPEG')
                        jpg_base64 = base64.b64encode(jpg_buffer.getvalue()).decode('utf-8')
                        photodescription = f'\n<img src="data:image/jpeg;base64,{jpg_base64}">'
                        return photodescription
                    else:
                        png_payload = {"image": "data:image/png;base64," + base64.b64encode(io.BytesIO(image_response.content).read()).decode('utf-8')}
                        async with aiohttp.ClientSession() as session: #make the BLIP interrogate API call
                            async with session.post(f'{SETTINGS["imageapi"][0]}/sdapi/v1/interrogate', json=png_payload) as response:
                                if response.status == 200:
                                    data = await response.json()
                                    cleaneddescription = data["caption"].split(",")[0].strip()
                                    photodescription = (f'The URL is a picture of the following topics: {cleaneddescription}')
                                    return photodescription
                else: return "There was an error with the link"
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
            
    async def moderate_prompt(self, prompt):
        negative_values = [neg.strip() for neg in self.defaultimage_payload["negative_prompt"].split(",")] # Split negative values into a list
        for neg in negative_values:
            prompt = re.sub(r'\b' + re.escape(neg) + r'\b', '', prompt)
        return prompt

intents = discord.Intents.all() #discord intents
client = MyClient(intents=intents) #client intents

class Speakgenbuttons(discord.ui.View): #Class for the ui buttons on speakgen

    def __init__(self, params, user_id, userprompt, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.params = params
            self.userid = user_id
            self.userprompt = userprompt
            self.timeout = None
            
    @discord.ui.button(label='Reroll', emoji="🎲", style=discord.ButtonStyle.grey)
    async def reroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer() #this makes it not say "interaction failed" when things take a long time
        async with aiohttp.ClientSession() as session:
            async with session.get(f'{SETTINGS["speakapi"][0]}/txt2wav', params=self.params) as response: 
                response_data = await response.read()
                if response_data:
                    wav_bytes_io = io.BytesIO(response_data)
                    truncatedfilename = self.userprompt[:1000]
                    await interaction.followup.send(file=discord.File(wav_bytes_io, filename=f"{truncatedfilename}.wav"), view=Speakgenbuttons(self.params, interaction.user.id, self.userprompt))
                    logging.info(f'{colored(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "dark_grey")} | {colored("speakgen", "cyan")} | {colored(interaction.user.name, "yellow")}:{colored(interaction.user.id, "light_yellow")} | {colored(interaction.guild, "red")}:{colored(interaction.channel, "light_red")} | P={colored(self.userprompt, "light_magenta")}') 
    
    @discord.ui.button(label='Mail', emoji="✉", style=discord.ButtonStyle.grey)
    async def dmimage(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer() #ensure we dont get the interaction failed message if it takes too long to respond
        async with aiohttp.ClientSession() as session:
            async with session.get(interaction.message.attachments[0].url) as response:
                if response.status == 200:
                    sound_bytes = await response.read()
                    dm_channel = await interaction.user.create_dm()
                    truncatedfilename = self.userprompt[:1000]
                    await dm_channel.send(file=discord.File(io.BytesIO(sound_bytes), filename=f'{truncatedfilename}.wav'))
                    logging.info(f'{colored(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "dark_grey")} | {colored("DM Speak", "cyan")} | {colored(interaction.user.name, "yellow")}:{colored(interaction.user.id, "light_yellow")} | {colored(interaction.guild, "red")}:{colored(interaction.channel, "light_red")} | {colored(interaction.message.attachments[0].url, "light_magenta")}') 
                else: await interaction.response.send_message("Failed to fetch the speak.")
    
    @discord.ui.button(label='Delete', emoji="❌", style=discord.ButtonStyle.grey)
    async def delete_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.userid == interaction.user.id:
            await interaction.message.delete()
            logging.info(f'{colored(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "dark_grey")} | {colored("Delete", "cyan")}   | {colored(interaction.user.name, "yellow")}:{colored(interaction.user.id, "light_yellow")} | {colored(interaction.guild, "red")}:{colored(interaction.channel, "light_red")} | {colored(interaction.id, "light_magenta")}')

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
        composite_image_bytes = await client.generate_image(self.payload, interaction.user.id) #generate image and place it into composite_image_bytes
        if composite_image_bytes is not None:
            await interaction.followup.send(content=f"Reroll", file=discord.File(composite_image_bytes, filename='composite_image.png'), view=Imagegenbuttons(self.payload, interaction.user.id))
            logging.info(f'{colored(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "dark_grey")} | {colored("Reroll", "cyan")}   | {colored(interaction.user.name, "yellow")}:{colored(interaction.user.id, "light_yellow")} | {colored(interaction.guild, "red")}:{colored(interaction.channel, "light_red")} | P={colored(self.payload["prompt"], "light_magenta")}')
        else:
            await interaction.followup.send(content="Image generation failed.")  # Handle the case when composite_image_bytes is None
            
    @discord.ui.button(label='Mail', emoji="✉", style=discord.ButtonStyle.grey)
    async def dmimage(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer() #ensure we dont get the interaction failed message if it takes too long to respond
        async with aiohttp.ClientSession() as session:
            async with session.get(interaction.message.attachments[0].url) as response:
                if response.status == 200:
                    image_bytes = await response.read()
                    dm_channel = await interaction.user.create_dm()
                    await dm_channel.send(file=discord.File(io.BytesIO(image_bytes), filename='composite_image.png'))
                    logging.info(f'{colored(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "dark_grey")} | {colored("DM Image", "cyan")} | {colored(interaction.user.name, "yellow")}:{colored(interaction.user.id, "light_yellow")} | {colored(interaction.guild, "red")}:{colored(interaction.channel, "light_red")} | {colored(interaction.message.attachments[0].url, "light_magenta")}') 
                else: await interaction.response.send_message("Failed to fetch the image.")
    
    @discord.ui.button(label='Delete', emoji="❌", style=discord.ButtonStyle.grey)
    async def delete_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.userid == interaction.user.id:
            await interaction.message.delete()
            logging.info(f'{colored(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "dark_grey")} | {colored("Delete", "cyan")}   | {colored(interaction.user.name, "yellow")}:{colored(interaction.user.id, "light_yellow")} | {colored(interaction.guild, "red")}:{colored(interaction.channel, "light_red")} | {colored(interaction.id, "light_magenta")}')

class Editpromptmodal(discord.ui.Modal, title='Edit Prompt'): #prompt editing modal.
    def __init__(self, payload, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.payload = payload
        self.timeout = None
        self.add_item(discord.ui.TextInput(label="Prompt", default=self.payload["prompt"], required=True, style=discord.TextStyle.long))
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        newprompt = str(self.children[0])
        moderatedprompt = await client.moderate_prompt(newprompt)
        self.payload["prompt"] = moderatedprompt.strip()
        composite_image_bytes = await client.generate_image(self.payload, interaction.user.id) #make the api call to generate the new image
        if composite_image_bytes is not None:
            truncatedprompt = moderatedprompt[:1500]
            await interaction.followup.send(content=f'Edit: New prompt `{truncatedprompt}`', file=discord.File(composite_image_bytes, filename='composite_image.png'), view=Imagegenbuttons(self.payload, interaction.user.id))
            logging.info(f'{colored(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "dark_grey")} | {colored("Edit", "cyan")}     | {colored(interaction.user.name, "yellow")}:{colored(interaction.user.id, "light_yellow")} | {colored(interaction.guild, "red")}:{colored(interaction.channel, "light_red")} | P={colored(self.payload["prompt"], "light_magenta")}')
        else: await interaction.followup.send(content="Image generation failed.")  # Handle the case when composite_image_bytes is None

@client.tree.command() #Begins imagen slash command stuff 
@app_commands.describe(usermodel="Choose the model", userprompt="Describe what you want to gen", userbatch="Batch Size", usernegative="Enter things you dont want in the gen", userseed="Seed", usersteps="Number of steps", userlora="Pick a LORA", userwidth="Image width", userheight="Image height")
@app_commands.choices(usermodel=client.models)  # Use the loaded models as choices
@app_commands.choices(userlora=client.loras)
async def imagegen(interaction: discord.Interaction, userprompt: str, usernegative: Optional[str] = None, usermodel: Optional[app_commands.Choice[str]] = None, userlora: Optional[app_commands.Choice[str]] = None, userbatch: Optional[int] = None, userseed: Optional[int] = None, usersteps: Optional[int] = None, userheight: Optional[int] = None, userwidth: Optional[int] = None):
    if SETTINGS["enableimage"][0] != "True":
            await interaction.response.send_message("Image generation is currently disabled.")
            return
    banned_users = SETTINGS["bannedusers"][0].split(',')
    if str(interaction.user.id) in banned_users: return  # Exit the function if the author is banned
    await interaction.response.defer() #respond so discord doesnt get mad it takes a long time to actually respond to the message
    payload = client.defaultimage_payload.copy() #set up default payload 
    ignore_fields = [field.strip() for field in SETTINGS["ignorefields"][0].split(",")]  # Split ignored fields into a list
    moderatedprompt = await client.moderate_prompt(userprompt)
    payload["prompt"] = moderatedprompt.strip() #put the prompt into the payload
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
            matches = re.findall(r"value='(.*?)'", str(userlora))
            currentlora = matches[0]
            payload["prompt"] = f"<lora:{matches[0]}:1>,{payload['prompt']}"
        else: userlora = None
    else: currentlora = None
    if usermodel is not None: #Check the user models choice if present
        if "usermodel" not in ignore_fields:  
            matches = re.findall(r"value='(.*?)'", str(usermodel))
            model_payload = {"sd_model_checkpoint": matches[0]} #put model choice into payload
            async with aiohttp.ClientSession() as session: #make the api request to change to the requested model
                async with session.post(f'{SETTINGS["imageapi"][0]}/sdapi/v1/options', json=model_payload) as response:
                    response_data = await response.json()
                    logging.debug(f'USERMODEL DEBUG RESPONSE: {colored(json.dumps(response_data, indent=1), "light_blue")}') if SETTINGS["debug"][0] == "True" else None
        else: usermodel = None
    else:
        model_payload = None
        for default_model in SETTINGS["defaultmodel"]: #This loads the server specific default model if it exists
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
                    logging.debug(f'DEFAULTMODEL DEBUG RESPONSE: {colored(json.dumps(response_data, indent=1), "light_blue")}') if SETTINGS["debug"][0] == "True" else None
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
    composite_image_bytes = await client.generate_image(payload, interaction.user.id) #generate image and place it into composite_image_bytes
    if composite_image_bytes is not None:
        truncatedprompt = moderatedprompt[:1500]
        await interaction.followup.send(content=f"Prompt: **`{truncatedprompt}`**, Negatives: `{usernegative}` Model: `{currentmodel}` Lora: `{currentlora}` Seed `{userseed}` Batch Size `{userbatch}` Steps `{usersteps}`", file=discord.File(composite_image_bytes, filename='composite_image.png'), view=Imagegenbuttons(payload, interaction.user.id)) #Send message to discord with the image and request parameters
    else: await interaction.followup.send("API failed")
    logging.info(f'{colored(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "dark_grey")} | {colored("imagegen", "cyan")} | {colored(interaction.user.name, "yellow")}:{colored(interaction.user.id, "light_yellow")} | {colored(interaction.guild, "red")}:{colored(interaction.channel, "light_red")} | P={colored(payload["prompt"], "light_magenta")}, N={colored(usernegative, "light_magenta")}, M={colored(currentmodel, "light_magenta")} L={colored(currentlora, "light_magenta")}') 

@client.tree.command()
@app_commands.choices(uservoice=client.voices)
async def speakgen(interaction: discord.Interaction, userprompt: str, uservoice: Optional[app_commands.Choice[str]] = None):
    if SETTINGS["enablespeak"][0] != "True": await interaction.response.send_message("Voice generation is currently disabled."); return
    await interaction.response.defer()
    async with aiohttp.ClientSession() as session:
        if uservoice is not None:
                matches = re.findall(r"value='(.*?)'", str(uservoice))
                currentvoice = matches[0]
                if currentvoice == "None": params = {'inputstring': userprompt}
                else: params = {'inputstring': userprompt, 'voicefile': currentvoice}
        else: 
            for default_voice in SETTINGS["defaultvoice"]: #This loads the server specific default model if it exists
                checkid, defaultvoicename = default_voice.strip().split("|", 1)  #grab the values and put them into variables
                if str(interaction.channel.id) == checkid: params = {'inputstring': userprompt, 'voicefile': defaultvoicename}
                elif str(interaction.guild.id) == checkid: params = {'inputstring': userprompt, 'voicefile': defaultvoicename}
                else: params = {'inputstring': userprompt}
        async with session.get(f'{SETTINGS["speakapi"][0]}/txt2wav', params=params) as response: 
            response_data = await response.read()
            if response_data:
                view = Speakgenbuttons(params, interaction.user.id, userprompt)
                wav_bytes_io = io.BytesIO(response_data)
                truncatedprompt = userprompt[:1000]
                await interaction.followup.send(file=discord.File(wav_bytes_io, filename=f"{truncatedprompt}.wav"), view=Speakgenbuttons(params, interaction.user.id, userprompt))
                logging.info(f'{colored(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "dark_grey")} | {colored("speakgen", "cyan")} | {colored(interaction.user.name, "yellow")}:{colored(interaction.user.id, "light_yellow")} | {colored(interaction.guild, "red")}:{colored(interaction.channel, "light_red")} | P={colored(userprompt, "light_magenta")}') 

@client.tree.command()
async def impersonate(interaction: discord.Interaction, userprompt: str, llmprompt: str):
    if SETTINGS["enableword"][0] != "True": await interaction.channel.send("LLM generation is currently disabled."); return #check if LLM generation is enabled
    if str(interaction.user.id) in SETTINGS.get("bannedusers", [""])[0].split(','): return  # Exit the function if the author is banned
    if not client.user_interaction_history.get(interaction.user.id): client.user_interaction_history[interaction.user.id] = [] #Creates a blank interaction history if it doesnt already exist.
    new_entry = [userprompt, llmprompt] #prepare entry to be placed into the users history
    client.user_interaction_history[interaction.user.id].append(new_entry) #update user history
    if len(client.user_interaction_history[interaction.user.id]) > 10: client.user_interaction_history[interaction.user.id].pop(0) #remove oldest result in history once maximum is reached
    await interaction.response.send_message(f'History inserted:\n User: {userprompt}\n LLM: {llmprompt}')
    logging.info(f'{colored(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "dark_grey")} | {colored("imperson", "cyan")} | {colored(interaction.user.name, "yellow")}:{colored(interaction.user.id, "light_yellow")} | {colored(interaction.guild, "red")}:{colored(interaction.channel, "light_red")} | P={colored(userprompt, "light_magenta")},{colored(llmprompt, "light_magenta")}')

client.run(SETTINGS["token"][0], log_handler=None) #run bot.
# metatron
A discord.py based machine learning bot. It provides a LLM chatbot via the oobabooga API, and a stable diffusion generation command via the AUTOMATIC1111 API.

I wanted a bot to provide LLM and Image gen stuff, but all of the ones out there were quite large and overcomplicated for what I needed. I wrote this in an attempt to provide myself a nice simple base with which to work with. 

To chat with the bot just tag it or reply to something it says. It keeps a separate chat history of 11 question/answer pairs for each user, which is lost on each restart. It can also see the contents of links and links to images. 

Image generation is handled via the /imagegen command. It provides very basic image functionality. Mandatory negatives are handled via the settings.cfg file. Any negatives in it are applied to all gens and also stripped from prompts, useful for banning unwanted keywords. It also has a reroll button, to make a new gen with the same settings and a new seed, a DM button to dm a gen to yourself, a edit button to edit the current prompt, and a delete button which can only be used by the person who made the gen.


## INSTALLATION INSTRUCTIONS

### REQUIREMENTS

A Working A1111 instance with --api enabled.

A Working oobabooga instance with --api enabled **AND A MODEL ALREADY LOADED**. Loading LLMs is somewhat complex and VERY slow so you must manually load a model via the ooba webui first.

Python

### Discord Bot Setup

Go to the Discord Developer portal and create a new bot and generate a token for it. Write this token down or else youll have to generate a new one, it only shows you once.

Go to the Bot tab on the Developer portal site and enable Privileged Gateway Intents. You need Presence, Server Members, and Message Content enabled.

Go to the URL Generator on the OAuth2 tab and select the bot scope. Then select these permissions "Read Messages/View Channels, Send Messages, Manage Messages, Attach Files, Read Message History, Use Slash Commands" then use the link to invite the bot to your server. I may have missed one, if something is missing you can enable it later in server permissions

### Conda Install (OPTIONAL) - This can be skipped if you dont mind if pip installs things globally. This can sometimes cause problems with other ML stuff so I always use conda envs.

Install miniconda if you dont already have conda.

Activate your base conda enviroment

Create a new enviroment `conda create -n metatron python`

Activate your new environment `conda activate metatron`

### Install - Start here if you dont want conda or have already activated and are in your metatron conda env.

Download the repo `git clone https://github.com/Meatfucker/metatron.git`

Install the bots requirements `pip install -r requirements.txt`

Install the nltk tokenizer for English `python -c "import nltk; nltk.download('punkt')"` URL parsing for the LLM side will not work without this, though image parsing will.

Read and edit settings-example.cfg, Make your required changes and save as settings.cfg

Run the bot, if all goes well itll say it has logged in. `python metatron.py`



## settings.cfg

settings.cfg provides all of the settings for the bot. If the example file has more than one line with the same first value, that means you can have multiple. For example you can have multiple models= lines to list all of your model defaults.

See https://github.com/oobabooga/text-generation-webui/tree/main/api-examples For some info on Oobas API and https://github.com/AUTOMATIC1111/stable-diffusion-webui/discussions/3734 for info on the A1111 API.

| OPTION | DESCRIPTION | EXAMPLE |
|----|----|----|
| wordapi | Address and port of your ooba API endpoint | `wordapi=http://localhost:5000` |
| imageapi | Address and port of your A1111 API endpoint | `imageapi=http://localhost:7860` |
| models | Default model positive and negatives. Can have one of these lines for each model. Is the model name and hash then \| followed by a mandatory positive prompt for that model(useful for loading loras). Then another \| followed by a mandatory negative prompt. | `models=Binglerv5-1.safetensors [a532e5bb]\|positive prompt here\|negative prompt here` |
| servers | Discord server id of the servers youll want the imagegen command to work on. Youll want one of these lines for each server. | `servers=34534523663` |
| token | Bots Discord token. | `token=90A8DF0G8907ASD7F097ADFQ98WE7` |
| imagesettings | Default payload it sends to the A1111 API. Any value accepted by the API can be placed here but if you mess up the structure itll definitely crash. | See settings-example.cfg |
| wordsettings | Default payload it sends to the Ooba API. Any value accepted by the API can be placed here but if you mess up the structure itll definitely crash. | See settings-example.cfg |
| debug | Turns on debug information. | `debug=True` |
| ignorefields | This is a comma separated list of /imagegen fields you want the user to be unable to change. They will still be able to write whatever they like but itll be ignored and the defaults used. | `ignorefields=userbatch,userwidth,userheight` |
| defaultmodel | This lets you set a default model per server or channel. Channel default will take precedence over server default. The defaults here will be combined with the global models= defaults. It is the server or channel id then a \| then the exact model name, another \| followed by a positive prompt, and then another \| followed by a negative prompt (same as you use for *models*) You can have one of these for each server or channel. | `defaultmodel=345664623455\|Goobs-v34.ckpt [a67efe20]\|goobs are good\|no bad goobs`
| enableimage | If set to anything besides True, image generation will be disabled. | `enableimage=True` |
| enableword | If set to anything besides True, LLM generation will be disabled. | `enableword=True` |
| enableurls | If set to anything besides True, URL and Image parsing for the LLM will be disabled. | `enableurls=True` |
| maxbatch | The maximum batch size the bot can gen. | `maxbatch=4` |
| maxwidth | The maximum horizontal resolution the bot can gen. | `maxwidth=512` |
| maxheight | The maximum vertical resolution the bot can gen. | `maxheight=512` |
| bannedusers | Comma separated list of discord user ids to ignore. | `bannedusers=34524353425346,12341246577` |
| saveimages | If set to True, will save generated images | `saveimages=True` |
| savepath | The path where you want the images saved | `savepath=outputs` |

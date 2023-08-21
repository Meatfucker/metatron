# metatron
A discord.py based machine learning bot. It provides a LLM chatbot via the oobabooga API, and a stable diffusion generation command via the AUTOMATIC1111 API.

I wanted a bot to provide LLM and Image gen stuff, but all of the ones out there were quite large and overcomplicated for what I needed. I wrote this in an attempt to provide myself a nice simple base with which to work with. 

To chat with the bot just tag it or reply to something it says. It keeps a separate chat history of 11 question/answer pairs for each user, which is lost on each restart. It can also see the contents of links and links to images. 

Image generation is handled via the /imagegen command. It provides very basic image functionality. Mandatory negatives are handled via the settings.cfg file. Any negatives in it are applied to all gens and also stripped from prompts, useful for banning unwanted keywords. It also has a reroll button, to make a new gen with the same settings and a new seed, a DM button to dm a gen to yourself, a edit button to edit the current promtp, and a delete button which can only be used by the person who made the gen.


# INSTALLATION INSTRUCTIONS

-Go to the Discord Developer portal and create a new bot and generate a token for it. Write this token down or else youll have to generate a new one, it only shows you once.

-Go to the Bot tab on the Developer portal site and enable Privileged Gateway Intents. You need Presence, Server Members, and Message Content enabled.

-Go to the URL Generator on the OAuth2 tab and select the bot scope. Then select these permissions "Read Messages/View Channels, Send Messages, Manage Messages, Attach Files, Read Message History, Use Slash Commands" then use the link to invite the bot to your server. I may have missed one, if something is missing you can enable it later in server permissions

**Conda Install - This can be skipped if you dont mind if pip installs things globally. This can sometimes cause problems with other ML stuff so I always use conda envs.**

-Install miniconda if you dont already have conda.

-Activate your base conda enviroment

-Create a new enviroment `conda create -n metatron python`

-Activate your new environment `conda activate metatron`

**Global Install - Start here if you dont want conda**

-Download the repo `git clone https://github.com/Meatfucker/metatron.git`

-Install the bots requirements `pip install -r requirements.txt`

-Install the nltk tokenizer for English `python -c "import nltk; nltk.download('punkt')"` URL parsing for the LLM side will not work without this, though image parsing will.

-Read and edit settings-example.cfg, Make your required changes and save as settings.cfg






-Run the bot, if all goes well itll say it has logged in. `python metatron.py`


You can add any key you like to the settings,cfg imagesettings and wordsettings options as long as the API recognizes them. See https://github.com/oobabooga/text-generation-webui/tree/main/api-examples For some info on Oobas API and https://github.com/AUTOMATIC1111/stable-diffusion-webui/discussions/3734 for info on the A1111 API.

# settings.cfg

settings.cfg provides all of the settings for the bot. If the example file has more than one line with the same first value, that means you can have multiple. For example you can have multiple models= lines to list all of your models.

**wordapi** is the address and port of your ooba API endpoint

**imageapi** is the same but for A1111

**models** is the exact name as it appears in the webui including the hash, then a | followed by a mandatory positive prompt for that model(useful for loading loras). Then another | followed by a mandatory negative prompt. Youll want one of these lines for each model you want to have model defaults for. The final line will look like this.`models=modelname [hashcode]|positive prompt here|negative prompt here`

**servers** is the Discord server id of the servers youll want the imagegen command to work on. Youll want one of these lines for each server.

**token** is your bots Discord token.

**imagesettings** is the default payload it sends to the A111 API. Any value accepted by the API can be placed here but if you mess up the structure itll definitely crash.

**wordsettings** same but for Ooba

**debug** When set to True this turns on debug info like raw API json responses and a few other things. Mostly only of use if you are debugging, hence the name.

**ignorefields** This is a comma separated list of /imagegen fields you want the user to be unable to change. They will still be able to write whatever they like in the command but itll be ignored and the defaults used.

**defaultmodel** This lets you set a default model per server. It is the server id(same as the one you use for *servers*)then a comma, then the exact model name(same as you use for *models* but without the | and things after) You can have one of these for each server.

**enableimage** If this is set to anything besides True, image generation will be disabled.

**enableword** Same but for the chatbot LLM

**enableurls** When set to True, enable the ability to see image links and websites.

**maxbatch** The maximum batch size the bot can gen.

**maxwidth** The maximum horizontal resolution the bot can gen.

**maxheight** same but vertical.

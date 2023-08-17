# metatron
A discord.py based machine learning bot. It provides a LLM chatbot via the oobabooga API, and a stable diffusion generation bot via the AUTOMATIC1111 API.

I wanted a bot to provide LLM and Image gen stuff, but all of the ones out there were quite large and overcomplicated for what I needed. I wrote this in an attempt to provide myself a nice simple base with which to work with. 

To chat with the bot just tag it or reply to something it says. It keeps a separate chat history of 7 question/answer pairs for each user, which is lost on each restart. 

Image generation is handled via the /imagegen command. It provides very basic image functionality. Mandatory negatives are handled via the settings.cfg file. Any negatives in it are applied to all gens. Useful for banning unwanted keywords. It also has a reroll button, to make a new gen with the same settings and a new seed, a DM button to dm a gen to yourself, and a delete button which can only be used by the person who made the gen.


*INSTALLATION INSTRUCTIONS*

-Go to the Discord Developer portal and create a new bot and generate a token for it. Write this token down or else youll have to generate a new one, it only shows you once.

-Go to the Bot tab on the Developer portal site and enable Privileged Gateway Intents. You need Presence, Server Members, and Message Content enabled.

-Go to the URL Generator on the OAuth2 tab and select the bot scope. Then select these permissions "Read Messages/View Channels, Send Messages, Manage Messages, Attach Files, Read Message History, Use Slash Commands" then use the link to invite the bot to your server. I may have missed one, if something is missing you can enable it later in server permissions

-Install miniconda if you dont already have conda.

-Activate your base conda enviroment

-Create a new enviroment `conda create -n metatron python`

-Activate your new environment `conda activate metatron`

-Download the repo `git clone https://github.com/Meatfucker/metatron.git`

-Install the bots requirements `pip install -r requirements.txt`

-Read and edit settings-example.cfg, Make your required changes and save as settings.cfg




-Run the bot, if all goes well itll say it has logged in. `python metatron.py`


You can add any key to them you like to the settings,cfg imagesettings and wordsettings options as long as the API recognizes them. See https://github.com/oobabooga/text-generation-webui/tree/main/api-examples For some info on Oobas API and https://github.com/AUTOMATIC1111/stable-diffusion-webui/discussions/3734 for info on the A1111 API.

# vigilant-pancake
A simple music bot for Discord using yt-dlp.

## Description
This is an example project for how to implement a basic music bot. It inclides the option of playing music from any online service supported by yt-dlp. It can also queue songs and skip them.

Please note that it does not implement any permissions and rate-limiting options. Add this bot to your server at your own peril. 

## Getting Started
### Dependencies
* Python 3.11+
* Requirements in requirements.txt

### Installation and setup
* Download project directory: `git clone https://github.com/Cutipus/vigilant-pancake`
* Install dependencies: `python -m pip install -r requirements.txt`
* Create a new file called config.yaml inside, and add the following line: `secret_token: "<token>"`. Replace `<token>` with your discord bot's secret token.

### Executing program
* To run the bot simply execute the bot.py file: `python bot.py`
* When first running the bot it is necessary to update the commands tree with Discord. Simply type `$sync` in a Discord server with the bot, and it will begin syncing. This process can take a while. Run this command manually when adding, removing or updating bot commands.
* To play a song, join a voice channel in Discord and type `/play url:<url>` and the bot will join the channel and immediately start playing the song.
* Using `/play` while the bot is already playing a song will queue it to be played after the first one finishes.
* Use `/skip` to stop currently playing song and start playing the next one in queue.
* Use `/stop` to make the bot stop playing music and return to idle.

## Help
Please forward any questions or problems regarding the bot to Cutipus@protonmail.me

import asyncio
import tomllib
import sys
import logging

from tampermint.bot import Bot


logger = logging.getLogger(__name__)


async def main():
    logging.basicConfig(filename='bot.log', encoding='utf-8', level=logging.DEBUG)
    logger.info("Starting main.")
    try:
        config_file = sys.argv[1]
    except IndexError:
        config_file = "config.toml"
    with open(config_file, 'rb') as config_file:
        config = tomllib.load(config_file)
    logger.info("Configuration file loaded.")
    bot = Bot()
    logger.info("Bot created.")
    await bot.start(config["secret_token"])


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.critical("Interrupted. Shutting down.")
        quit()

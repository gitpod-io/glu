import openai
from glu.config_loader import config

openai.api_key = config["openai"]["api_key"]

openai = openai

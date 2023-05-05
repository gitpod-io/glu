from .config_loader import config
from slack_sdk.web.async_client import AsyncWebClient
# for team in config["slack"]["automations"]["watch_github_lables"]:
#     print(team["github_label_name_or_id"])

slack_client = AsyncWebClient(token=config["slack"]["api_token"])


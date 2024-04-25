from os import environ
import requests
from typing import Any
from tomllib import load as toml_load
from pathlib import Path
from gidgethub.sansio import Event
from gidgethub.abc import GitHubAPI

# from typing import Tuple

# Some bots use a normal personal GitHub account to operate
bot_users = frozenset(
    {
        "roboquat",
        "incident-io[bot]",
        "werft-gitpod-dev-com[bot]",
        "autofix-bot",
        "dependabot[bot]",
    }
)


def load_config(path: Path) -> dict[str, Any]:
    config_file = open(path, "rb")
    config = toml_load(config_file)
    config_file.close()
    return config


def is_self(event: Event) -> bool:
    from glu import runtime_constants

    sender = str(event.data["sender"]["login"])
    sender_type = str(event.data["sender"]["type"]).lower()

    if runtime_constants.app_obj is None:
        return False

    app_username = str(runtime_constants.app_obj["slug"])

    if sender_type == "bot":
        app_username += "[bot]"

    if app_username == sender:
        return True
    else:
        return False


def is_bot(event: Event) -> bool:
    sender = str(event.data["sender"]["login"])
    sender_type = str(event.data["sender"]["type"])

    if sender_type == "Bot" or sender in bot_users:
        return True
    else:
        return False


async def is_non_org_and_bot_user(event: Event, gh: GitHubAPI) -> bool:
    # ) -> Tuple[bool, str | None]:

    # Only respond to real Users
    if is_bot(event):
        return False

    # Get org members
    organization = event.data["organization"]["login"]
    endpoint = f"/orgs/{organization}/members?per_page=100"
    members = []
    async for member in gh.getiter(endpoint):
        members.append(member["login"])

    # Only send when sender is not one of the org members
    sender = event.data["sender"]["login"]

    if environ.get("GLU_DEBUG"):
        return True
    elif sender not in members:
        # return (True, sender)
        return True
    else:
        # return (False, None)
        return False


def download_file(url, local_filename):
    # Send a GET request to the URL
    r = requests.get(url, allow_redirects=True, stream=True)
    # Open a local file with write-binary mode
    with open(local_filename, "wb") as f:
        # Write the content to the local file
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)

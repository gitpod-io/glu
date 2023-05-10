from os import environ
from typing import Any
from tomllib import load as toml_load
from pathlib import Path
from gidgethub.sansio import Event
from gidgethub.abc import GitHubAPI
# from typing import Tuple


def load_config(path: Path) -> dict[str, Any]:
    config_file = open(path, "rb")
    config = toml_load(config_file)
    config_file.close()
    return config


async def is_non_org_user(
    event: Event, gh: GitHubAPI
) -> bool:
    # ) -> Tuple[bool, str | None]:

    # Only respond to real Users
    if event.data["sender"]["type"] != "User":
        # return (False, None)
        return False

    # Get org members
    organization = event.data["organization"]["login"]
    endpoint = f'/orgs/{organization}/members?per_page=100'
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

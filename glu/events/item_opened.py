"""Send newly created issues and pull requests to slack channels.
And auto triage them with GPT"""

import gidgethub.routing
from aiohttp import ClientSession
from gidgethub.sansio import Event
from gidgethub.abc import GitHubAPI
from glu.config_loader import config
from glu.utils import is_non_org_and_bot_user
import glu.slack_client as slack
router = gidgethub.routing.Router()


@router.register("issues", action="opened")
@router.register("pull_request", action="opened")
async def item_opened(
    event: Event,
    gh: GitHubAPI,
    session: ClientSession,
    *args, **kwargs
) -> None:
    """TODO
    """
    if await is_non_org_and_bot_user(event, gh):
        await slack.send_github_issue(
            event,
            gh,
            config["github"]["user_activity"]["to_slack"]["all_channel_id"],
            "created"
        )

"""Send labeled issues and pull requests to slack channels."""

import gidgethub.routing
from aiohttp import ClientSession
from gidgethub.sansio import Event
from gidgethub.abc import GitHubAPI
from glu.config_loader import config
from glu.utils import is_non_org_user
import glu.slack_client as slack
router = gidgethub.routing.Router()


@router.register("issues", action="labeled")
@router.register("pull_request", action="labeled")
async def item_labeled(
    event: Event,
    gh: GitHubAPI,
    session: ClientSession,
    *args, **kwargs
) -> None:
    """TODO
    """
    if not await is_non_org_user(event, gh):
        return

    label_id = event.data["label"]["id"]
    label_name = event.data["label"]["name"]

    for team in config["github"]["to_slack"]["user_activity"]["teams"]:
        team_label = team["label_id_or_name"]

        if label_id == team_label or label_name == team_label:
            await slack.send_github_issue(
                event,
                team["channel_id"],
                "added"
            )
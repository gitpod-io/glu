"""Send labeled issues and pull requests to slack channels."""

import gidgethub.routing
from aiohttp import ClientSession
from gidgethub.sansio import Event
from gidgethub.abc import GitHubAPI
from glu.config_loader import config
from glu.utils import is_non_org_and_bot_user
import glu.slack_client as slack
from html import unescape as html_unescape
router = gidgethub.routing.Router()


@router.register("issue_comment", action="created")
async def item_labeled(
    event: Event,
    gh: GitHubAPI,
    session: ClientSession,
    *args, **kwargs
) -> None:
    """TODO
    """
    if not await is_non_org_and_bot_user(event, gh):
        return

    # Always send to team communit
    await slack.send_github_issue(
        event,
        gh,
        config["github"]["user_activity"]["to_slack"]["all_channel_id"],
        "commented on"
    )

    # Then applicable teams
    for team in config["github"]["user_activity"]["to_slack"]["teams"]:
        if "watch_comments" in team and not team["watch_comments"]:
            continue

        team_label = str(team["label_id_or_name"])
        for label in event.data["issue"]["labels"]:
            label_id = str(label["id"])
            label_name = str(label["name"])

            if label_id == team_label or label_name == team_label:
                await slack.send_github_issue(
                    event,
                    gh,
                    team["channel_id"],
                    "commented on"
                )

"""Send labeled issues and pull requests to slack channels."""

import gidgethub.routing
from aiohttp import ClientSession
from gidgethub.sansio import Event
from gidgethub.abc import GitHubAPI
from glu.config_loader import config
from glu.utils import is_non_org_user
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
    if not await is_non_org_user(event, gh):
        return

    # Always send to team communit
    await slack.send_github_issue(
        event,
        config["github"]["to_slack"]["user_activity"]["all_channel_id"],
        "commented on"
    )

    # Then applicable teams
    for team in config["github"]["to_slack"]["user_activity"]["teams"]:
        if "watch_comments" in team and not team["watch_comments"]:
            continue

        team_label = team["label_id_or_name"]
        for label in event.data["issue"]["labels"]:
            label_id = label["id"]
            label_name = label["name"]

            if label_id == team_label or label_name == team_label:
                await slack.send_github_issue(
                    event,
                    team["channel_id"],
                    "commented on"
                )

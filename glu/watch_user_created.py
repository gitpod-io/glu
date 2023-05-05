"""Send newly created issues and pull requests to slack channels.
And auto triage them with GPT"""

import gidgethub.routing
from aiohttp import ClientSession
from gidgethub.sansio import Event
from gidgethub.abc import GitHubAPI
from .config_loader import config
from .slack_client import slack_client
from html import unescape as html_unescape
router = gidgethub.routing.Router()


@router.register("issues", action="opened")
@router.register("pull_request", action="opened")
async def watch_issue_pr(
    event: Event,
    gh: GitHubAPI,
    session: ClientSession,
    *args, **kwargs
) -> None:
    """TODO
    """

    # Get org members
    organization = config["github"]["organization"]
    endpoint = f'/orgs/{organization}/members?per_page=100'
    members = []
    async for member in gh.getiter(endpoint):
        members.append(member["login"])

    # Only send when sender is not one of the org members
    sender = event.data["sender"]["login"]

    # if sender not in members:
    if sender in members:
        item_url = (
            event.data["issue"]["html_url"]
            if event.event == "issues"
            else event.data["pull_request"]["html_url"]
        )
        item_title = html_unescape((
            event.data["issue"]["title"]
            if event.event == "issues"
            else event.data["pull_request"]["title"]
        ))
        text = f'<https://github.com/{sender}|{sender}> created <{item_url}|{item_title}>'
        channel = config["slack"]["automations"]["watch_user_created"]["target_channel_id"]

        # Main message
        main_message = await slack_client.chat_postMessage(
            channel=channel,
            text=f'{sender} created: {item_title}',
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": text,
                    }
                }
            ]
        )
        # Also send item body inside thread
        item_body: str | None = (
            event.data["issue"]["body"] if event.event == "issues"
            else event.data["pull_request"]["body"]
        )
        if item_body is not None:
            text = f'{item_body}\n\n_View it on <{item_url}|GitHub>_'
            await slack_client.chat_postMessage(
                channel=str(main_message["channel"]),
                thread_ts=main_message["ts"],
                text=f"{item_url} body",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": text,
                        }
                    }
                ]
            )

        # TODO: Auto label the issue/PR with GPT3.5

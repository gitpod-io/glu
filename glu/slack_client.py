from .config_loader import config
from gidgethub.sansio import Event
from html import unescape as html_unescape
from slack_sdk.web.async_client import AsyncWebClient


class CustomAsyncWebClient(AsyncWebClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.username: str = config["slack"]["username"]
        self.icon_emoji: str = config["slack"]["icon_emoji"]


slack_client = CustomAsyncWebClient(token=config["slack"]["api_token"])


async def send_github_issue(event: Event, channel: str, what: str) -> None:
    sender = event.data["sender"]["login"]
    item_url: str | None = None
    if event.event == "issues":
        item_url = event.data["issue"]["html_url"]
    elif event.event == "pull_request":
        item_url = event.data["pull_request"]["html_url"]
    elif event.event == "issue_comment":
        item_url = event.data["comment"]["html_url"]

    item_title = html_unescape((
        event.data["issue"]["title"]
        if event.event == "issues" or event.event == "issue_comment"
        else event.data["pull_request"]["title"]
    ))
    text = f'<https://github.com/{sender}|{sender}> {what} <{item_url}|{item_title}>'  # noqa: E501

    # Main message
    main_message = await slack_client.chat_postMessage(
        username=slack_client.username,
        icon_emoji=slack_client.icon_emoji,
        channel=channel,
        text=f'{sender} {what}: {item_title}',
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
    item_body: str | None = None
    if event.event == "issues":
        item_body = event.data["issue"]["body"]
    elif event.event == "pull_request":
        item_body = event.data["pull_request"]["body"]
    elif event.event == "issue_comment":
        item_body = event.data["comment"]["body"]

    if item_body is not None:
        text = f'{item_body}\n\n_View it on <{item_url}|GitHub>_'
        # text = f'_View it on <{item_url}|GitHub>_'
        await slack_client.chat_postMessage(
            as_user=True,
            link_names=False,
            unfurl_links=False,
            unfurl_media=False,
            username=slack_client.username,
            icon_emoji=slack_client.icon_emoji,
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

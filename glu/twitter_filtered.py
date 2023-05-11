import sys
import snscrape.modules.twitter as sntwitter
from aiohttp import web
from aiohttp.web_request import Request
from glu.config_loader import config
from glu.slack_client import slack_client as slack


async def send_msg(content: str, channel: str):
    # Main message
    await slack.chat_postMessage(
        username=slack.username,
        icon_emoji=slack.icon_emoji,
        channel=channel,
        text=content,
    )


def get_tweet(id):
    return list(sntwitter.TwitterTweetScraper(tweetId=id).get_items())[0]


# TODO: This is a bit of mess, just dumped an old pipedream workflow here, refactoring needed.
async def handler(request: Request):
    json = await request.json()
    tweet_url = json["url"]
    tweet_content: str = json["full_text"].lower()
    # from re import search
    # tweet_id = search('/([0-9]+$)', tweet_url).group(1)
    tweet_id = json["id"]
    print(f'Tweet ID: {tweet_id}', file=sys.stderr)
    tweet = get_tweet(id=tweet_id)

    filtered_channel = config["twitter"]["to_slack"]["filtered_tweets_channel"]
    all_channel = config["twitter"]["to_slack"]["all_tweets_channel"]
    await send_msg(tweet_url, all_channel)

    # Ignore retweets
    if tweet_content.startswith("rt @"):
        return web.Response(status=200)

    # First post in thread mentions @gitpod
    if tweet.inReplyToTweetId == None:
        # if not "@gitpod" in tweet.content.lower():
        if "gitpod" not in tweet_content:
            # return pd.flow.exit("Gitpod not mentioned in main tweet")
            return web.Response(status=500)
    else:
        main_tweet_content = get_tweet(
            id=tweet.inReplyToTweetId).content.lower()
        # if main_tweet_replies == 1:
        count = 0
        # for word in tweet.content.lower().split():
        for word in tweet_content.split():
            if "gitpod" in word:
                count += 1
        # Reply mentions @gitpod
        if "@gitpod" not in main_tweet_content and count >= 1:
            pass
        elif count <= 1:
            # return pd.flow.exit("Gitpod not mentioned in reply")
            return web.Response(status=500)
        # else:
        #     if not "gitpod" in tweet.content.lower():
        #         return pd.flow.exit("Gitpod not mentioned")

    await send_msg(tweet_url, filtered_channel)
    return web.Response(status=200)

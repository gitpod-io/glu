import sys
import snscrape.modules.twitter as sntwitter
from aiohttp import web
from aiohttp.web_request import Request
from glu.config_loader import config
from glu.slack_client import slack_client as slack
from glu.openai_client import openai


async def is_feedback(tweet_content: str) -> bool:
    ai_system_message = config["twitter"]["to_slack"]["feedback_detection"]["prompt"]

    ai_response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": ai_system_message},
            {"role": "user", "content": tweet_content}
        ],
        n=1,
        max_tokens=1,
    )

    if ai_response["choices"][0]["message"]["content"].lower() == "true":
        return True
    else:
        return False


async def send_msg(message: str, channel: str):
    # Main message
    await slack.chat_postMessage(
        username=slack.username,
        icon_emoji=slack.icon_emoji,
        channel=channel,
        text=message,
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
    tweet_id = str(json["id_str"])
    print(f'Tweet ID: {tweet_id}', file=sys.stderr)

    tweet = get_tweet(id=tweet_id)
    filtered_channel = config["twitter"]["to_slack"]["filtered_tweets_channel"]
    all_channel = config["twitter"]["to_slack"]["all_tweets_channel"]
    feedback_channel = config["twitter"]["to_slack"]["feedback_detection"]["channel"]

    # # ignore own tweets
    # sender_username: str = json["user"]["screen_name"]
    # if config["twitter"]["own_username"] == sender_username:
    #     return web.Response(status=200)

    # Ignore retweets
    # if tweet_content.startswith("rt @"):
    if json.get("retweeted_status") and tweet_content.startswith("rt @"):
        return web.Response(status=200)

    message = tweet_url
    send_to_feedback_channel = False

    try:
        if await is_feedback(tweet_content):
            message = f'*[Potential feedback]*: {tweet_url}'
            send_to_feedback_channel = True
    except:
        pass

    await send_msg(message, all_channel)

    # First post in thread mentions @gitpod
    if tweet.inReplyToTweetId is None:
        # if not "@gitpod" in tweet.content.lower():
        if "gitpod" not in tweet_content:
            # return pd.flow.exit("Gitpod not mentioned in main tweet")
            return web.Response(status=200)
    else:
        main_tweet_content = get_tweet(
            id=tweet.inReplyToTweetId).rawContent.lower()
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
            return web.Response(status=200)
        # else:
        #     if not "gitpod" in tweet.content.lower():
        #         return pd.flow.exit("Gitpod not mentioned")

    if send_to_feedback_channel:
        await send_msg(message, feedback_channel)

    await send_msg(message, filtered_channel)
    return web.Response(status=200)

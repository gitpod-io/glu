import sys
import snscrape.modules.twitter as sntwitter
from aiohttp import web
from aiohttp.web_request import Request
from glu.config_loader import config
from glu.slack_client import slack_client as slack
from glu.openai_client import openai


async def is_feedback(tweet_content: str) -> bool:
    ai_system_message = config["twitter"]["mentions"]["to_slack"]["feedback_detection"][
        "system_prompt"
    ]

    ai_response = openai.ChatCompletion.create(
        # model="gpt-3.5-turbo", # This also works well
        model="gpt-4",
        messages=[
            {"role": "system", "content": ai_system_message},
            {"role": "user", "content": tweet_content},
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
    print(f"Tweet ID: {tweet_id}", file=sys.stderr)

    tweet = get_tweet(id=tweet_id)
    filtered_channel = config["twitter"]["mentions"]["to_slack"][
        "filtered_tweets_channel"
    ]
    all_channel = config["twitter"]["mentions"]["to_slack"]["all_tweets_channel"]
    feedback_channel = config["twitter"]["mentions"]["to_slack"]["feedback_detection"][
        "channel"
    ]
    send_to_extra_feedback_channel: bool = config["twitter"]["mentions"]["to_slack"][
        "feedback_detection"
    ]["send_to_extra_channel"]

    # # ignore own tweets
    # sender_username: str = json["user"]["screen_name"]
    # if config["twitter"]["own_username"] == sender_username:
    #     return web.Response(status=200)

    # Ignore retweets
    # if tweet_content.startswith("rt @"):
    if json.get("retweeted_status") and tweet_content.startswith("rt @"):
        return web.Response(status=200)

    message = tweet_url
    feedback_detected = False

    try:
        if await is_feedback(tweet_content):
            message = f"*[Potential feedback]*: {tweet_url}"
            feedback_detected = True
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
        main_tweet_content = get_tweet(id=tweet.inReplyToTweetId).rawContent.lower()
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

    if send_to_extra_feedback_channel and feedback_detected:
        await send_msg(message, feedback_channel)

    await send_msg(message, filtered_channel)
    return web.Response(status=200)


# zapier below
# import re
#
# def check_gitpod_mention(tweet):
#     # Check if the tweet starts with 'RT @username:'
#     if re.match(r'^RT @[A-Za-z0-9_]+:', tweet, re.IGNORECASE):
#         return 'false'
#
#     # Extract leading mentions to simulate Twitter reply behavior
#     leading_mentions = re.findall(r'@([A-Za-z0-9_]+)\s', tweet, re.IGNORECASE)
#
#     # Count occurrences of '@gitpod' in leading mentions, case-insensitively
#     gitpod_count = sum(1 for mention in leading_mentions if mention.lower() == 'gitpod')
#
#     # Remove leading mentions from the tweet
#     tweet = re.sub(r'^(@[A-Za-z0-9_]+ )+', '', tweet)
#
#     # Check for explicit mention of 'gitpod' or '@gitpod' in the rest of the tweet
#     if re.search(r'\b(?:@?gitpod)\b', tweet, re.IGNORECASE):
#         return 'true'
#
#     # Return true only if '@gitpod' appears exactly twice in leading mentions
#     if gitpod_count == 2:
#         return 'true'
#
#     return 'false'
#
#
# tweet_text = input_data['tweet_text']
# filtered = False
# is_competitor = False
# is_retweet = False
# gitpod_mentions_channel = False
#
#
# # Avoid RTs
# if re.match(r'^RT @[A-Za-z0-9_]+:', tweet_text):
#     is_retweet = True
# else:
#     is_quote = True if input_data['quote_status'].lower() == 'true' and 'quote_tweet_text' in input_data else False
#
#     # Adjust tweet_text if a quoted tweet
#     if is_quote:
#         tweet_text = input_data['quote_tweet_text']
#
#     if 'gitpod' in tweet_text.lower():
#         gitpod_mentions_channel = True
#
#         # If a reply
#         if 'in_reply_to' in input_data:
#             filtered = check_gitpod_mention(tweet_text)
#         else:
#             filtered = True
#
#     # If a competitor tweet
#     elif int(input_data['follower_count']) > 1500:
#         is_competitor = True
#
#
# output = [{
#     'filtered': filtered,
#     'competitor': is_competitor,
#     'retweet': is_retweet,
#     'gitpod_mentions_channel': gitpod_mentions_channel,
#     'tweet_url': input_data['tweet_url'],
#     'slack_bot_name': 'Twitter',
#     'slack_bot_avatar_emoji': ':twitter:',
# }]
#
#

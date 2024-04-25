import asyncio
from glu.slack_client import slack_client as slack
from glu.config_loader import config
import requests
import aiosqlite
import re


HEADERS = {
    "Authorization": config["twitter"]["bearer_token"],
}

# Define the base URL
BASE_URL = "https://api.twitter.com/2/tweets/search/recent"

# Define the URL parameters
URL_PARAMS = {
    "query": config["twitter"]["mentions"]["to_slack"]["search_query"],
    "max_results": 100,
    "expansions": "author_id,entities.mentions.username,in_reply_to_user_id,referenced_tweets.id,referenced_tweets.id.author_id",
    "user.fields": "public_metrics",
}

filtered_channel = config["twitter"]["mentions"]["to_slack"]["filtered_tweets_channel"]
all_channel = config["twitter"]["mentions"]["to_slack"]["all_tweets_channel"]
competitor_channel = config["twitter"]["mentions"]["to_slack"][
    "competitor_tweets_channel"
]


async def send_slack_msg(message: str, channel: str):
    await slack.chat_postMessage(
        username=slack.username,
        icon_emoji=slack.icon_emoji,
        channel=channel,
        text=message,
    )


def check_gitpod_mention(tweet):
    # Check if the tweet starts with 'RT @username:'
    # if re.match(r'^RT @[A-Za-z0-9_]+:', tweet, re.IGNORECASE):
    #    return 'false'

    # Extract leading mentions to simulate Twitter reply behavior
    leading_mentions = re.findall(r"@([A-Za-z0-9_]+)\s", tweet, re.IGNORECASE)

    # Count occurrences of '@gitpod' in leading mentions, case-insensitively
    gitpod_count = sum(1 for mention in leading_mentions if mention.lower() == "gitpod")

    # Remove leading mentions from the tweet
    tweet = re.sub(r"^(@[A-Za-z0-9_]+ )+", "", tweet)

    # Check for explicit mention of 'gitpod' or '@gitpod' in the rest of the tweet
    if re.search(r"\b(?:@?gitpod)\b", tweet, re.IGNORECASE):
        return True

    # Return true only if '@gitpod' appears exactly twice in leading mentions
    if gitpod_count == 2:
        return True

    return False


async def post_on_slack(new_tweets):
    for tweet in new_tweets:
        tweet_text = tweet["text"].lower()
        filtered = False
        mentions_gitpod = "gitpod" in tweet_text

        tweet_type = "post"
        if "referenced_tweets" in tweet:
            # _, ref_tweet_id, _, tweet_type = map(
            #     str.strip, tweet["ref_tweets_data"].split()
            # )
            tweet_type = tweet["referenced_tweets"][0]["type"]
        is_retweet = tweet_type == "retweeted"

        if not is_retweet:
            if mentions_gitpod:
                await send_slack_msg(tweet["url"], all_channel)

                filtered = (
                    check_gitpod_mention(tweet_text)
                    if tweet_type == "replied_to"
                    else True
                )
                if filtered:
                    await send_slack_msg(tweet["url"], filtered_channel)
            elif int(tweet["followers_count"]) > 1500:
                await send_slack_msg(tweet["url"], competitor_channel)


async def job(db: aiosqlite.Connection, cur: aiosqlite.Cursor):
    response = requests.get(BASE_URL, headers=HEADERS, params=URL_PARAMS)

    if response.status_code == 200:
        data = response.json()

        # Get the list of tweets and users
        tweets = data["data"]
        users = {
            u["id"]: u for u in data["includes"]["users"]
        }  # Create a dict with users

        # Create a list to store new tweets
        new_tweets = []

        for tweet in tweets:
            # Insert the tweets into the sqlite3 database
            await cur.execute(
                "INSERT OR IGNORE INTO tweets (id, timestamp) VALUES (?, CURRENT_TIMESTAMP)",
                (tweet["id"],),
            )

            # If a new row was inserted (i.e., the tweet didn't already exist in the database)
            if cur.rowcount == 1:
                if tweet_user := users.get(
                    tweet["author_id"]
                ):  # Get the user using author_id
                    tweet["followers_count"] = tweet_user["public_metrics"][
                        "followers_count"
                    ]
                    tweet["username"] = tweet_user["username"]
                    tweet[
                        "url"
                    ] = f"https://twitter.com/{tweet['username']}/status/{tweet['id']}"  # Set the tweet's url
                new_tweets.append(tweet)

        # Commit the changes
        await db.commit()

        # If there are any new tweets
        if new_tweets:
            # print(new_tweets)
            await post_on_slack(new_tweets)
            pass
        else:
            print("No new tweets.")

    else:
        print(f"Request failed: {response.text}")


async def run():
    # Connect to the sqlite3 database
    db = await aiosqlite.connect("tweets.db")
    cur = await db.cursor()

    # Create a table if it doesn't exist
    await cur.execute(
        """CREATE TABLE IF NOT EXISTS tweets
                (id TEXT PRIMARY KEY, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)"""
    )
    await db.commit()

    while True:
        try:
            await job(db, cur)

            # Delete tweets older than 7 days
            await cur.execute(
                "DELETE FROM tweets WHERE timestamp <= datetime('now','-7 day')"
            )
            await db.commit()

            # Delay next run for 1.5 hours
            await asyncio.sleep(5400)
        except Exception as e:
            print(e)

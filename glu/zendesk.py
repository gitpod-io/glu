import asyncio
import ast
import json
import sys
from traceback import print_exc as traceback_print_exc
from aiohttp.web_request import Request
from aiohttp import web
from zenpy import Zenpy
from zenpy.lib.api_objects import Webhook
from glu.config_loader import config
from google.cloud import bigquery
from google.oauth2.credentials import Credentials
from datetime import datetime, timedelta, timezone

# Zenpy accepts an API token
creds = {
    "email": config["zendesk"]["api_agent_email"],
    "token": config["zendesk"]["api_key"],
    "subdomain": config["zendesk"]["subdomain"],
}
zenpy_client = Zenpy(
    **creds,
)


async def init() -> None:
    # Fetch our webhook
    var = zenpy_client.webhooks.list(filter="Glu").next()

    # Create our webhook if needed
    # if :
    # new_webhook = Webhook(
    #     endpoint="https://the-ordered-postal-display.trycloudflare.com/zendesk",
    #     http_method="POST",
    #     name="Hello Webhook",
    #     description="Webhook description",
    #     request_format="json",
    #     status="active",
    #     subscriptions=["conditional_ticket_events"],
    # )
    # zenpy_client.webhooks.create(new_webhook)


async def webhook_handler(request: Request):
    try:
        body_bytes = await request.read()
        body_str = body_bytes.decode("utf-8")
        data = ast.literal_eval(body_str)

        # Only work for specified group ids
        if data["group_id"] not in config["zendesk"]["trigger_group_ids"]:
            return web.Response(status=204)

        # service_key = json.loads(config["bigquery"]["service_key"])
        # bq_client = bigquery.Client.from_service_account_info(service_key)
        user_creds = json.loads(config["bigquery"]["adc"])
        credentials = Credentials.from_authorized_user_info(user_creds)

        # Construct a BigQuery client object with the user credentials
        bq_client = bigquery.Client(
            credentials=credentials, project=user_creds["quota_project_id"]
        )

        db_address = config["bigquery"]["db_address"]
        inner_query = config["bigquery"]["user_info_sql"]
        nn_inner_query = " ".join(inner_query.splitlines())  # remove newlines
        query = (
            f""" SELECT * FROM EXTERNAL_QUERY("{db_address}", "{nn_inner_query}"); """
        )
        rows = bq_client.query_and_wait(query)  # Make an API request.
        user = list(rows)[0]

        # Parse the lastVerificationTime string into a datetime object
        last_verification_time = datetime.fromisoformat(
            user.lastVerificationTime.rstrip("Z")
        ).replace(tzinfo=timezone.utc)

        # Get the current datetime in UTC
        current_time = datetime.now(timezone.utc)

        # Calculate the difference between the current time and the last verification time
        time_difference = current_time - last_verification_time

        # Custom msg for blocked users
        if user.blocked == 1:
            pass
        elif time_difference <= timedelta(days=10):
            pass

        # TODO: Ask to create a stripe read only api key

        # print("The query data:")
        # for row in rows:
        #     print(row.userId)

        return web.Response(status=200)

    except Exception:
        traceback_print_exc(file=sys.stderr)
        return web.Response(status=500)

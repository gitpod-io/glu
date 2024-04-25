import asyncio
import subprocess
import os
from pathlib import Path
import ast
import json
import sys
from traceback import print_exc as traceback_print_exc
from aiohttp.web_request import Request
from aiohttp import web
from zenpy import Zenpy

from glu import utils
from glu.config_loader import config
from glu.openai_client import openai
from google.cloud import bigquery
from google.oauth2.credentials import Credentials
from zenpy.lib.api_objects import Comment, CustomField
from typing import List

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
    # from zenpy.lib.api_objects import Webhook
    # Fetch our webhook
    # var = zenpy_client.webhooks.list(filter="Glu").next()

    # Create our webhook if needed
    # if not var:
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
    pass


async def post_zendesk_comment(
    body: str,
    ticket_id: str,
    public: bool = True,
    ustatus: str = "open",
    atags: List[str] = [],
    utype: str = "Problem",
    author_id: int = config["zendesk"]["community_author_id"],
) -> None:
    ticket = zenpy_client.tickets(id=ticket_id)
    ticket.status = ustatus
    ticket.tags.extend(["bot_processed"] + atags)
    ticket.custom_fields.append(
        CustomField(id=config["zendesk"]["ticket_type_custom_id"], value=utype)
    )
    ticket.comment = Comment(
        body=body,
        public=public,
        author_id=author_id,
    )
    zenpy_client.tickets.update(ticket)


async def webhook_handler(request: Request):
    try:
        body_bytes = await request.read()
        body_str = body_bytes.decode("utf-8")
        webhook_data = ast.literal_eval(body_str)
        requester_email = webhook_data["requester"]["email"]
        ticket_id = webhook_data["id"]

        # Only work for specified group ids
        if webhook_data["group_id"] not in config["zendesk"]["trigger_group_ids"]:
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
        # inner_query = config["bigquery"]["user_info_sql"]
        inner_query = f"""
SELECT
  sub.userId,
  sub.teamId,
  sub.teamName,
  cost_center.billingStrategy,
  sub.LastModified,
  sub.blocked,
  sub.markedDeleted,
  sub.lastVerificationTime,
  sub.creationDate
  
FROM (
  SELECT
    identity.userId,
    membership.teamId,
    org.name AS teamName,
    user.blocked,
    user.markedDeleted,
    user.lastVerificationTime,
    user.creationDate,
    MAX(cost_center._lastModified) AS LastModified
  FROM (
    SELECT
      userId
    FROM
      d_b_identity
    WHERE
      primaryEmail = '{requester_email}'
    LIMIT
      1) AS identity
  JOIN
    d_b_team_membership AS membership
  ON
    identity.userId = membership.userId
  JOIN
    d_b_team AS org
  ON
    membership.teamId = org.id
  JOIN
    d_b_user as user
  ON
    identity.userId = user.id
  LEFT JOIN
    d_b_cost_center AS cost_center
  ON
    CONCAT('team:', membership.teamId) = cost_center.id
  GROUP BY
    identity.userId,
    membership.teamId,
    user.id) AS sub
JOIN
  d_b_cost_center AS cost_center
ON
  CONCAT('team:', sub.teamId) = cost_center.id
  AND sub.LastModified = cost_center._lastModified
ORDER BY
  sub.LastModified DESC
"""
        nn_inner_query = " ".join(inner_query.splitlines())  # remove newlines

        # # There is an `@email` parameter in `inner_query`
        # job_config = bigquery.QueryJobConfig(
        #     query_parameters=[
        #         bigquery.ScalarQueryParameter("email", "STRING", requester_email),
        #     ]
        # )
        query = (
            f""" SELECT * FROM EXTERNAL_QUERY("{db_address}", "{nn_inner_query}"); """
        )

        rows = bq_client.query_and_wait(query)  # Make an API request.

        rows = list(rows)
        user = rows[0]
        stripe_billing_strategy_exists = any(
            row["billingStrategy"] == "stripe" for row in rows
        )
        print(user)

        if not stripe_billing_strategy_exists:
            # User is blocked
            if user.blocked == 1:
                await post_zendesk_comment(
                    body=config["zendesk"]["templates"]["blocked"],
                    ticket_id=ticket_id,
                    atags=["blocked"],
                    ustatus="pending",
                )

            # User has not verified yet
            elif not user.lastVerificationTime:
                tickets = zenpy_client.tickets.comments(ticket=ticket_id)
                comments_str = ""
                for ticket in tickets:
                    if ticket.author_id == webhook_data["requester"]["id"]:
                        comments_str += ticket.body + "\n"

                if comments_str:
                    ai_response = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {
                                "role": "system",
                                "content": "Reply with 'true' if the user input contains a phone number.",
                            },
                            {"role": "user", "content": comments_str},
                        ],
                        n=1,
                        max_tokens=1,
                    )
                    targets = ai_response["choices"][0]["message"]["content"]

                    if "true" in targets:
                        # TODO: This needs improvements
                        gpctl_path = Path(os.getcwd()) / "gpctl"
                        if not gpctl_path.exists():
                            utils.download_file(
                                config["gitpod"]["gpctl_url"], gpctl_path
                            )
                            os.chmod(gpctl_path, 0o755)

                        # await asyncio.sleep(180)
                        subprocess.run([gpctl_path, "users", "verify", user.userId])

                        await post_zendesk_comment(
                            body=config["zendesk"]["templates"]["manual_verify"],
                            ticket_id=ticket_id,
                            ustatus="solved",
                            atags=["phone_verification"],
                        )
                    else:
                        await post_zendesk_comment(
                            body=config["zendesk"]["templates"]["ask_pnumber"],
                            ticket_id=ticket_id,
                            ustatus="pending",
                            atags=["phone_verification"],
                        )

        # TODO: Ask to create a stripe read only api key

        # print("The query data:")
        # for row in rows:
        #     print(row.userId)

        return web.Response(status=200)

    except Exception:
        traceback_print_exc(file=sys.stderr)
        return web.Response(status=500)

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
from stripe import CustomerService, StripeClient

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

stripe_client = StripeClient(config["stripe"]["api_key"])

# TODO: Use a service key
# service_key = json.loads(config["bigquery"]["service_key"])
# bq_client = bigquery.Client.from_service_account_info(service_key)
user_creds = json.loads(config["bigquery"]["adc"])
credentials = Credentials.from_authorized_user_info(user_creds)

# Construct a BigQuery client object with the user credentials
bq_client = bigquery.Client(
    credentials=credentials, project=user_creds["quota_project_id"]
)

bot_processed_tag = "bot_processed"
payg_tag = "payg"
user_found_tag = "user_found"
not_found_tag = "user_not_found"
db_address = config["bigquery"]["db_address"]
blocked_tag = "blocked"
pv_tag = "phone_verification"
gitpod_admin_org_baseurl = "https://gitpod.io/admin/orgs"
gitpod_admin_user_baseurl = "https://gitpod.io/admin/users"
stripe_admin_customer_baseurl = "https://dashboard.stripe.com/customers"


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
    ticket_id: str,
    body: str = "",
    html_body: str = "",
    public: bool = True,
    ustatus: str = "open",
    atags: List[str] = [],
    utype: str = "Problem",
    author_id: int = config["zendesk"]["community_author_id"],
) -> None:
    ticket = zenpy_client.tickets(id=ticket_id)
    ticket.status = ustatus
    ticket.assignee_id = author_id
    ticket.tags.extend([bot_processed_tag] + atags)
    ticket.custom_fields.append(
        CustomField(id=config["zendesk"]["ticket_type_custom_id"], value=utype)
    )

    if body or html_body:
        comment_args = {
            "public": public,
            "author_id": author_id,
        }
        if body:
            comment_args["body"] = body
        if html_body:
            comment_args["html_body"] = html_body

        ticket.comment = Comment(**comment_args)

    zenpy_client.tickets.update(ticket)


async def webhook_handler(request: Request):
    try:
        body_bytes = await request.read()
        body_str = body_bytes.decode("utf-8")
        webhook_data = ast.literal_eval(body_str)

        ticket_id = webhook_data["id"]
        ticket_obj = zenpy_client.tickets(id=ticket_id)
        requester_id = ticket_obj.requester_id or ticket_obj.requester.id
        requester_email = (
            ticket_obj.requester.email or ticket_obj.via.source.from_["address"]
        )
        if requester_email == "support@twitter.com":
            return web.Response(status=204)
        ticket_tags = list(ticket_obj.tags)
        # requester_email = webhook_data.get("requester", {}).get(
        #     "email"
        # ) or webhook_data.get("via", {}).get("source", {}).get("from", {}).get(
        #     "address"
        # )
        # requester_id = webhook_data.get("requester", {}).get(
        #     "email"
        # ) or webhook_data.get("requester_id")

        # # Only work for specified group ids
        # if webhook_data["group_id"] not in config["zendesk"]["trigger_group_ids"]:
        #     return web.Response(status=204)

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

        rows = list(bq_client.query_and_wait(query))  # Make an API request.

        # Post stripe info
        if rows and user_found_tag not in ticket_tags:
            cmt_str = ""
            user_obj = rows[0]

            # Add admin user link
            cmt_str += f"- User: [gitpod.io/admin]({gitpod_admin_user_baseurl}/{user_obj.userId})"

            # Chunk rows and process each chunk
            # This is needed because stripe doesn't allow more than 10 filters in one go
            chunk_size = 9
            all_stripe_responses = []
            for chunk_start in range(0, len(rows), chunk_size):
                chunk_rows = rows[chunk_start : chunk_start + chunk_size]

                # Construct query string for this chunk
                stripe_query_str = " OR ".join(
                    [
                        f"metadata['attributionId']:'team:{row.get('teamId', 'none')}'"
                        for row in chunk_rows
                    ]
                )

                if not all_stripe_responses:
                    stripe_query_str += f" OR email:'{requester_email}'"

                res = stripe_client.customers.search(
                    params=CustomerService.SearchParams(
                        limit=100, query=stripe_query_str
                    )
                ).to_dict_recursive()
                all_stripe_responses.extend(res["data"])

            # Go through orgIds
            for row in rows:
                if orgId := row.get("teamId"):
                    orgName = row.get("teamName", "Undefined")

                    cmt_str += (
                        f"\n- Org: [{orgName}]({gitpod_admin_org_baseurl}/{orgId})"
                    )

                    # Find the matching ID and remove the corresponding customer from the search results
                    for customer in all_stripe_responses[:]:
                        if (
                            customer.get("metadata", {}).get("attributionId")
                            == f"team:{orgId}"
                        ):
                            cmt_str += f" | [[stripe]({stripe_admin_customer_baseurl}/{customer['id']})]"
                            all_stripe_responses.remove(customer)
                            break

            # Go through remaining stripe customerIds that didn't match with any orgIds
            for customer in all_stripe_responses:
                customerName = customer.get("name", "Undefined")
                cmt_str += f"\n- Email linked with Stripe: [{customerName}]({stripe_admin_customer_baseurl}/{customer['id']})"

            # Finally, post an internal comment
            # if cmt_str and user_found_tag not in ticket_tags:
            ticket_obj.tags.extend([user_found_tag])
            ticket_obj.comment = Comment(
                body=cmt_str,
                author_id=config["zendesk"]["community_author_id"],
                public=False,
            )
            zenpy_client.tickets.update(ticket_obj)

        # If no userdata found
        if not rows:
            if not_found_tag not in ticket_tags:
                await post_zendesk_comment(
                    html_body=config["zendesk"]["templates"][not_found_tag],
                    ticket_id=ticket_id,
                    atags=[not_found_tag],
                    ustatus="solved",
                )
            return web.Response(status=204)

        user_obj = rows[0]
        stripe_billing_strategy_exists = any(
            row["billingStrategy"] == "stripe" for row in rows
        )

        # Add payg tag
        if stripe_billing_strategy_exists:
            ticket_obj.tags.extend([payg_tag])
            zenpy_client.tickets.update(ticket_obj)

        if not stripe_billing_strategy_exists:
            # User is blocked
            if user_obj.blocked == 1:
                if blocked_tag not in ticket_tags:
                    await post_zendesk_comment(
                        body=config["zendesk"]["templates"][blocked_tag],
                        ticket_id=ticket_id,
                        atags=[blocked_tag],
                        ustatus="pending",
                    )

            # User has not verified yet
            elif not user_obj.lastVerificationTime:
                comments = zenpy_client.tickets.comments(ticket=ticket_id)
                comments_str = ""
                last_comment_author_id = None

                for comment in comments:
                    last_comment_author_id = comment.author_id

                    if comment.author_id == requester_id:
                        comments_str += comment.body + "\n"

                if last_comment_author_id == requester_id and comments_str:
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

                        # await asyncio.sleep(300)
                        subprocess.run(
                            [
                                gpctl_path,
                                "users",
                                "verify",
                                user_obj.userId,
                                "--token",
                                config["gitpod"]["token"],
                            ]
                        )

                        await post_zendesk_comment(
                            body=config["zendesk"]["templates"]["manual_verify"],
                            ticket_id=ticket_id,
                            ustatus="solved",
                            atags=[pv_tag],
                        )
                    else:
                        if pv_tag not in ticket_tags:
                            await post_zendesk_comment(
                                body=config["zendesk"]["templates"]["ask_pnumber"],
                                ticket_id=ticket_id,
                                ustatus="pending",
                                atags=[pv_tag],
                            )

        return web.Response(status=200)

    except Exception:
        traceback_print_exc(file=sys.stderr)
        return web.Response(status=500)

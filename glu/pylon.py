import asyncio
import subprocess
import os
from pathlib import Path
import ast
import json
import sys
from traceback import print_exc as traceback_print_exc
from aiohttp import web
from stripe import CustomerService, StripeClient
from glu import utils
from glu.config_loader import config
from glu.openai_client import openai
from google.cloud import bigquery
from google.oauth2.credentials import Credentials
from typing import List


stripe_client = StripeClient(config["stripe"]["api_key"])
stripe_admin_customer_baseurl = "https://dashboard.stripe.com/customers"

bot_processed_tag = "bot_processed"
payg_tag = "payg"
user_found_tag = "user_found"
not_found_tag = "user_not_found"
blocked_tag = "blocked"
pv_tag = "phone_verification"
gitpod_admin_org_baseurl = "https://gitpod.io/admin/orgs"
gitpod_admin_user_baseurl = "https://gitpod.io/admin/users"

# TODO: Use a service key
# service_key = json.loads(config["bigquery"]["service_key"])
# bq_client = bigquery.Client.from_service_account_info(service_key)
bq_user_creds = json.loads(config["bigquery"]["adc"])
bq_credentials = Credentials.from_authorized_user_info(bq_user_creds)
# Construct a BigQuery client object with the user credentials
db_address = config["bigquery"]["db_address"]
bq_client = bigquery.Client(
    credentials=bq_credentials, project=bq_user_creds["quota_project_id"]
)


async def fetch_data_from_mysql(requester_email: str):
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
    query = f""" SELECT * FROM EXTERNAL_QUERY("{db_address}", "{nn_inner_query}"); """

    rows = list(bq_client.query_and_wait(query))  # Make an API request.
    return rows


async def sidebar(request: web.Request):
    try:
        if request.query.get("request_type") == "verify":
            print(f"Verification request received: {request.query['code']}")
            return web.json_response({"code": request.query["code"]}, status=200)

        if request.query.get("request_type") != "fetch_data":
            return web.Response(status=204)

        response_data = {
            "version": "1.0.0",
            "header": {
                "title": "Gitpod.io",
                "icon_url": "https://www.gitpod.io/images/media-kit/logo-mark.png",
            },
            "components": [],
        }

        issue_id = request.query["issue_id"]
        requester_email = request.query["requester_email"]
        ticket_tags = []
        print(issue_id)

        if requester_email == "":
            return web.json_response(response_data, status=200)

        if requester_email == "support@twitter.com":
            return web.Response(status=204)

        rows = await fetch_data_from_mysql(requester_email)  # Make an API request.
        cmt_str = ""

        # Post stripe info
        if rows and user_found_tag not in ticket_tags:
            user_obj = rows[0]

            # Indicate whether the user is subscribed
            if any(row["billingStrategy"] == "stripe" for row in rows):
                response_data["components"].append(
                    {
                        "type": "badge",
                        "label": "Plan",
                        "items": [
                            {"value": "PAYG", "color": "orange"},
                        ],
                    },
                )

            # Show userId
            response_data["components"].append(
                {
                    "type": "text",
                    "label": "User ID",
                    "value": f"{user_obj.userId}",
                }
            )

            # Show userId and add admin user link
            response_data["components"].append(
                {
                    "type": "link",
                    "label": "Admin Page",
                    "url": f"{gitpod_admin_user_baseurl}/{user_obj.userId}",
                },
            )

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

            # Add devider
            response_data["components"].append({"type": "divider"})
            # Card component
            response_data["components"].append(
                {
                    "type": "card",
                    "header": {"title": "Organizations"},
                    "components": [],
                }
            )
            org_card_components = response_data["components"][-1]["components"]

            response_data["components"].append(
                {
                    "type": "card",
                    "header": {"title": "Stripe Linkage"},
                    "components": [],
                }
            )
            stripe_card_components = response_data["components"][-1]["components"]

            # Go through orgIds
            for row in rows:
                if orgId := row.get("teamId"):
                    orgName = row.get("teamName", "Undefined")

                    org_card_components.append(
                        {
                            "type": "link",
                            "label": f"{orgName}",
                            "url": f"{gitpod_admin_org_baseurl}/{orgId}",
                        }
                    )
                    cmt_str += (
                        f"\n- Org: [{orgName}]({gitpod_admin_org_baseurl}/{orgId})"
                    )

                    # Find the matching ID and remove the corresponding customer from the search results
                    for customer in all_stripe_responses[:]:
                        if (
                            customer.get("metadata", {}).get("attributionId")
                            == f"team:{orgId}"
                        ):
                            stripe_card_components.append(
                                {
                                    "type": "link",
                                    "label": f"{orgName}",
                                    "url": f"{stripe_admin_customer_baseurl}/{customer['id']}",
                                }
                            )
                            cmt_str += f" | [[stripe]({stripe_admin_customer_baseurl}/{customer['id']})]"
                            all_stripe_responses.remove(customer)
                            break

            # Go through remaining stripe customerIds that didn't match with any orgIds
            for customer in all_stripe_responses:
                customerName = customer.get("name", "Undefined")
                stripe_card_components.append(
                    {
                        "type": "link",
                        "label": f"DELETED: {customerName}",
                        "url": f"{stripe_admin_customer_baseurl}/{customer['id']}",
                    }
                )
                cmt_str += f"\n- Deleted account with Stripe: [{customerName}]({stripe_admin_customer_baseurl}/{customer['id']})"

            # return web.json_response(response_data, status=200)

        return web.json_response(response_data, status=200)

    except Exception:
        traceback_print_exc(file=sys.stderr)
        return web.Response(status=500)


async def webhook(request: web.Request):
    try:
        return web.Response(status=200)

    except Exception:
        traceback_print_exc(file=sys.stderr)
        return web.Response(status=500)

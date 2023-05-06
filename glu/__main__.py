import sys
from traceback import print_exc as traceback_print_exc
from aiohttp import (web, ClientSession)
from aiohttp.web_request import Request
from cachetools import LRUCache
from gidgethub import (aiohttp as gh_aiohttp, routing, sansio)
from gidgethub.apps import (get_installation_access_token)
import glu.events as event
from glu.config_loader import config

router = routing.Router(
    event.item_opened,
    event.item_labeled,
    event.item_comment,
)
cache = LRUCache(maxsize=500)


async def main(request: Request):
    try:
        body = await request.read()
        webhook_secret = config["github"]["webhook_secret"]
        event = sansio.Event.from_http(
            request.headers,
            body,
            secret=webhook_secret
        )

        print('GH delivery ID:', event.delivery_id, file=sys.stderr)

        if event.event == "ping":
            return web.Response(status=200)

        async with ClientSession() as session:
            app_id = str(request.headers.get(
                "X-GitHub-Hook-Installation-Target-ID"))
            user_agent = config["github"]["user_agent"]
            gh = gh_aiohttp.GitHubAPI(session, user_agent)
            access_info = await get_installation_access_token(
                gh,
                app_id=app_id,
                installation_id=event.data["installation"]["id"],
                private_key=config["github"]["private_key"],
            )
            gh_app = gh_aiohttp.GitHubAPI(
                session, user_agent,
                oauth_token=access_info["token"],
                cache=cache

            )
            await router.dispatch(event, gh_app, session=session)
            # jwt_token = get_jwt(
            #         app_id=app_id,
            #         private_key=config["github"]["private_key"],
            # )
            # print(await gh_app.getitem("/app", jwt=jwt_token))

            return web.Response(status=200)

    except Exception:
        traceback_print_exc(file=sys.stderr)
        return web.Response(status=500)


if __name__ == "__main__":
    app = web.Application()
    app.router.add_post("/", main)
    port = int(config["server"].get("port", 8000))
    host = str(config["server"].get("host", "127.0.0.1"))
    web.run_app(app, host=host, port=port)

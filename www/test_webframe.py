import logging; logging.basicConfig(level=logging.INFO)
import asyncio
from aiohttp import web

from web_app import orm
from webframe import add_routes, add_static
from middleware_factories import init_jinja2, datetime_filter, logger_factory, response_factory, auth_factory
from web_app.config import configs

# 编写web框架测试
async def init(loop):
    await orm.create_pool(loop=loop, **configs.db)
    app = web.Application(loop=loop, middlewares=[
        logger_factory, auth_factory, response_factory
    ])
    init_jinja2(app, filters=dict(datetime=datetime_filter))# 初始化Jinja2，设置文件路径的path参数
    add_routes(app, 'handlers')
    add_static(app)
    srv = await loop.create_server(app.make_handler(), '127.0.0.1', 9001)
    logging.info('server started at http://127.0.0.1:9001...')
    return srv

loop = asyncio.get_event_loop()
loop.run_until_complete(init(loop))
loop.run_forever()
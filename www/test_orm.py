import asyncio

from web_app import orm
from web_app.models import User, Blog

async def test(loop):
	await orm.create_pool(loop = loop, user = 'www-data', password = 'www-data', db = 'awesome')

	u = User(name = 'Test', email = 'test@example.com', passwd = '1234567890', image = 'about:blank')

	await u.save()

	# await destory_pool()

loop = asyncio.get_event_loop()
loop.run_until_complete(test(loop))
# __pool.close()
# loop.run_until_complete(__pool.wait_closed())
# loop.close()
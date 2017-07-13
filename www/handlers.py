from web_app.models import User, Blog, Comment, next_id
from web_app.apis import APIValueError, APIResourceNotFoundError
from webframe import get, post
from config import configs
from aiohttp import web
import asyncio, logging, time, hashlib, re, json, base64
# import markdown2

COOKIE_NAME = 'awesession'
_COOKIE_KEY = configs.session.secret

# 编写用于测试的URL处理函数
@get('/')
def root(request):
	summary = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
	blogs = [
		Blog(id='1', name='Test Blog', summary=summary, created_at=time.time()-120),
		Blog(id='2', name='Something new', summary=summary, created_at=time.time()-3600),
		Blog(id='3', name='Learn Swift', summary=summary, created_at=time.time()-7200)
	]
	return {
		'__template__': 'blogs.html',
		'blogs': blogs
		# '_user': request.__user
	}

@get('/firstblog')
async def handler_url_blog(request):
	body = '<h1>Awesome</h1>'
	return body

@get('/greeting')
async def handler_url_greeting(*, name, request):# name需要传入参数，eg:127.0.0.1:9000/greeting?name=xxx
	body = '<h1>Awesome: /greeting %s</h1>' % name
	return body

@get('/index')
async def index(request):
	users = await User.findAll()
	return {
		'__template__': 'test.html',
		'users': users
	}

# @get('/api/users')
# async def api_get_users():
# 	# page_index = get_page_index(page)
# 	# num = await User.findNumber('count(id)')
# 	# p = Page(num, page_index)
# 	# if num == 0:
# 	# 	return dict(page=p, users=())
# 	# users = await User.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
# 	users = await User.findAll(orderBy='created_at desc')
# 	for u in users:
# 		u.passwd = '******'
# 	# return dict(page=p, users=users)
# 	return dict(users=users)

_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')

@get('/register')
def register():
    return {
        '__template__': 'register.html'
    }

@get('/signin')
def signin():
    return {
        '__template__': 'signin.html'
    }

@get('/signout')
def signout(request):
    referer = request.headers.get('Referer')
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
    logging.info('user signed out.')
    return r

@post('/api/users')
def api_register_user(*, email, name, passwd):
	if not name or not name.strip():
		raise APIValueError('name')
	if not email or not _RE_EMAIL.match(email):
		raise APIValueError('email')
	if not passwd or not _RE_SHA1.match(passwd):
		raise APIValueError('passwd')
	users = yield from User.findAll('eamil=?', [email])
	if len(users) > 0:
		raise APIError('register:failed', 'email', 'Email is already in use.')
	uid = next_id()
	sha1_passwd = '%s:%s' % (uid, passwd)
	user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(), image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
	yield from user.save()
	# make session cookie:
	r = web.Response()
	r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
	user.passwd = '******'
	r.content_type = 'application/json'
	r.body = json.dumps(user, ensure_ascii=Flase).encode('utf-8')
	return r

@post('/api/authenticate')
def authenticate(*, email, passwd):
	if not email:
		raise APIValueError('email', 'Invalid email.')
	if not passwd:
		raise APIValueError('passwd', 'invalid password.')
	users = yield from User.findAll('email=?', [email])
	if len(users) == 0:
		raise APIValueError('email', 'Email not exist.')
	user = users[0]
	# check passwd:
	sha1 = hashlib.sha1()
	sha1.update(user.id.encode('utf-8'))
	sha1.update(b':')
	sha1.update(passwd.encode('utf-8'))
	if user.passwd != sha1.hexdigest():
		raise APIValueError('passwd', 'Invalid password.')
	# authenticate ok, set cookie:
	r = web.Response()
	r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
	user.passwd = '******'
	r.content_type = 'application/json'
	r.body = json.dumps(user, ensure_ascii=Flase).encode('utf-8')
	return r

# 计算加密cookie：
def user2cookie(user, max_age):
	# build cookie string by: id-expires-sha1
	expires = str(int(time.time() + max_age))
	s = '%s-%s-%s-%s' % (user.id, user.passwd, expires, _COOKIE_KEY)
	L = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
	return '-'.join(L)

async def auth_factory(app, handler):
	async def auth(request):
		logging.info('check user: %s %s' % (request.method, request.path))
		request.__user__ = None
		cookie_str = request.cookie.get(COOKIE_NAME)
		if cookie_str:
			user = await cookie2user(cookie_str)
			if user:
				logging.info('set current user: %s' % user.email)
				request.__user__ = user
		return (await handler(request))
	return auth

# 解密cookie:
@asyncio.coroutine
def cookie2user(cookie_str):
	'''
	Parse cookie and load user if cookie is valid
	'''
	if not cookie_str:
		return None
	try:
		L = cookie_str.split('-')
		if len(L) != 3:
			return None
		uid, expires, sha1 = L
		if int(expires) < time.time():
			return None
		user = yield from User.find(uid)
		if user is None:
			return None
		s = '%s-%s-%s-%s' % (uid, user.passwd, expires, _COOKIE_KEY)
		if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
			logging.info('invalid sha1')
			return None
		user.passwd = '******'
		return user
	except Exception as e:
		logging.exception(e)
		return None
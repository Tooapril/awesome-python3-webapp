import hashlib, json, logging, re, time
from aiohttp import web

from web_app.makedown2 import markdown
from web_app.apis import APIValueError, APIError, APIPermissionError, APIResourceNotFoundError, Page
from web_app.config import configs
from web_app.models import User, Blog, Comment, next_id
from webframe import get, post

COOKIE_NAME = 'awesession'
_COOKIE_KEY = configs.session.secret

_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')

# 检查是否为管理员
def check_admin(request):
	if request.__user__ is None or not request.__user__.admin:
		raise APIPermissionError()

# 获取页面页码
def get_page_index(page_str):
	p = 1
	try:
		p = int(page_str)
	except ValueError as e:
		pass
	if p < 1:
		p = 1
	return p

# 计算加密cookie：
def user2cookie(user, max_age):
	# build cookie string by: id-expires-sha1
	expires = str(int(time.time() + max_age))
	s = '%s-%s-%s-%s' % (user.id, user.passwd, expires, _COOKIE_KEY)
	L = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
	return '-'.join(L)

# 解密cookie:
async def cookie2user(cookie_str):
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
		user = await User.find(uid)
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

# text->html
def text2html(text):
	lines = map(lambda s: '<p>%s</p>' % s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'),
				filter(lambda s: s.strip() != '', text.split('\n')))
	return ''.join(lines)


'''后端API'''
# 获取日志
@get('/api/blogs')
async def api_blogs(*, page='1'):
	page_index = get_page_index(page)
	num = await Blog.findNumber('count(id)')
	p = Page(num, page_index)
	if num == 0:
		return dict(page = p, blogs=())
	blogs = await Blog.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
	return dict(page=p, blogs=blogs)

# 获取日志详情??
@get('/api/blogs/{id}')
async def api_get_blog(*, id):
	blog = await Blog.find(id)
	return blog

# 创建日志
@post('/api/blogs')
async def api_create_blog(request, *, name, summary, content):
	check_admin(request)
	if not name or not name.strip():
		raise APIValueError('name', 'name cannot be empty.')
	if not summary or not summary.strip():
		raise APIValueError('summary', 'summary cannot be empty.')
	if not content or not content.strip():
		raise APIValueError('content', 'content cannot be empty.')
	blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image,
				name=name.strip(), summary=summary.strip(), content=content.strip())
	await blog.save()
	return blog

# 修改日志
@post('/api/blogs/{id}')
async def api_update_blog(id, request, *, name, summary, content):
	check_admin(request)
	blog = await Blog.find(id)
	if not name or not name.strip():
		raise APIValueError('name', 'name cannot be empty.')
	if not summary or not summary.strip():
		raise APIValueError('summary', 'summary cannot be empty.')
	if not content or not content.strip():
		raise APIValueError('content', 'content cannot be empty.')
	blog.name=name
	blog.summary=summary
	blog.content=content
	await blog.update()
	return blog

# 删除日志
@post('/api/blogs/{id}/delete')
async def api_delete_blog(request, *, id):
	check_admin(request)
	blog = await Blog.find(id)
	await blog.remove()
	return dict(id=id)

# 获取评论
@get('/api/comments')
async def api_comments(*, page='1'):
	page_index = get_page_index(page)
	num = await Comment.findNumber('count(id)')
	p = Page(num, page_index)
	if num == 0:
		return dict(page=p, comments=())
	comments = await Comment.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
	return dict(page=p, comments=comments)

# 创建评论
@post('/api/blogs/{id}/comments')
async def api_create_comments(id, request, *, content):
	user = request.__user__
	if user is None:
		raise APIPermissionError('Please signin first.')
	if not content or not content.strip():
		raise APIValueError('content', 'content cannot be empty.')
	blog = await Blog.find(id)
	if blog is None:
		raise APIResourceNotFoundError('Blog')
	comment = Comment(blog_id=blog.id, user_id=user.id, user_name=user.name, user_image=user.image, content=content.strip())
	await comment.save()
	return comment

# 删除评论
@post('/api/comments/{id}/delete')
async def api_delete_comments(id, request):
	check_admin(request)
	comment = await Comment.find(id)
	if comment is None:
		raise APIResourceNotFoundError('Comment')
	await comment.remove()
	return dict(id=id)

# 创建用户
@post('/api/users')
async def api_register_user(*, email, name, passwd):
	if not name or not name.strip():
		raise APIValueError('name')
	if not email or not _RE_EMAIL.match(email):
		raise APIValueError('email')
	if not passwd or not _RE_SHA1.match(passwd):
		raise APIValueError('passwd')
	users = await User.findAll('email=?', [email])
	if len(users) > 0:
		raise APIError('register:failed', 'email', 'Email is already in use.')
	uid = next_id()
	sha1_passwd = '%s:%s' % (uid, passwd)
	user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(),
				image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.sha1(email.encode('utf-8')).hexdigest())
	await user.save()
	# make session cookie:
	r = web.Response()
	r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
	user.passwd = '******'
	r.content_type = 'application/json'
	r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')

	return r

# 获取用户
@get('/api/users')
async def api_get_users(*, page='1'):
	page_index = get_page_index(page)
	num = await User.findNumber('count(id)')
	p = Page(num, page_index)
	if num == 0:
		return dict(page=p, users=())
	users = await User.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
	for u in users:
		u.passwd = '******'
	return dict(page=p, users=users)

@post('/api/authenticate')
async def authenticate(*, email, passwd):
	if not email:
		raise APIValueError('email', 'Invalid email.')
	if not passwd:
		raise APIValueError('passwd', 'invalid password.')
	users = await User.findAll('email=?', [email])
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
	r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
	return r


'''管理页面'''
# 重定向
@get('/manage/')
def manage():
    return 'redirect:/manage/comments'

# 评论列表页
@get('/manage/comments')
def manage_comments(*, page='1'):
	return {
		'__template__': 'manage_comments.html',
		'page_index': get_page_index(page)
	}

# 日志列表页
@get('/manage/blogs')
def manage_blogs(*, page='1'):
	return {
		'__template__': 'manage_blogs.html',
		'page_index': get_page_index(page)
	}

# 创建日志页
@get('/manage/blogs/create')
def manage_create_blog():
	return {
        '__template__': 'manage_blog_edit.html',
        'id': '',
        'action': '/api/blogs'
    }

# 修改日志页
@get('/manage/blogs/edit')
def manage_edit_blog(*, id):
	return {
		'__templa te__': 'manage_blog_edit.html',
		'id': id,
		'action': '/api/blogs/%s' % id
	}

# 用户列表页
@get('/manage/users')
def manage_users(*,page='1'):
	return {
		'__template__': 'manage_users.html',
		'page_index': get_page_index(page)
	}


'''用户浏览页面'''
# 注册页
@get('/register')
def register():
	return {
        '__template__': 'register.html'
    }

# 登录页
@get('/signin')
def signin():
    return {
        '__template__': 'signin.html'
    }

# 注销页
@get('/signout')
def signout(request):
    referer = request.headers.get('Referer')
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
    logging.info('user signed out.')
    return r

# 首页
@get('/')
async def root(*, page='1'):
	#	summary = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit,' \
	#			  'sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
	#	blogs = [
	#		Blog(id='1', name='Test Blog', summary=summary, created_at=time.time()-120),
	#		Blog(id='2', name='Something new', summary=summary, created_at=time.time()-3600),
	#		Blog(id='3', name='Learn Swift', summary=summary, created_at=time.time()-7200)
	#	]
	page_index = get_page_index(page)
	num = await Blog.findNumber('count(id)')
	page = Page(num, page_index)
	if num == 0:
		blogs = []
	else:
		blogs = await Blog.findAll(orderBy='created_at desc', limit=(page.offset, page.limit))
	return {
		'__template__': 'blogs.html',
		'blogs': blogs,
		'page': page
	}

# 日志详情页
@get('/blog/{id}')
async def get_blog(id):
	blog = await Blog.find(id)
	comments = await Comment.findAll('blog_id=?', [id], orderBy='created_at desc')
	for c in comments:
		c.html_content = text2html(c.content)
	blog.html_content = markdown(blog.content)
	return {
        '__template__': 'blog.html',
        'blog': blog,
        'comments': comments
    }


'''其他'''
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
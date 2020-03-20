#coding=utf-8
import os
from datetime import datetime
from flask import Flask, render_template, session, redirect, \
				  url_for, flash, current_app, request
from flask_script import Manager, Shell
from flask_migrate import Migrate, MigrateCommand
from flask_bootstrap import Bootstrap
from flask_login import UserMixin, LoginManager, login_required, \
						login_user, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, \
					BooleanField, IntegerField, ValidationError
from wtforms.validators import Required, Length, Regexp
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

import random
from faker import Faker
fake = Faker('zh_CN')

'''
Config
'''
basedir = os.path.abspath(os.path.dirname(__file__))

def make_shell_context():
	return dict(app=app, db=db, Device=Device, User=User, Role=Role)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] =\
	'sqlite:///' + os.path.join(basedir, 'data.sqlite')
app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['AdminPassword'] = 666666
app.config['SECRET_KEY'] = "this is a secret_key"
db = SQLAlchemy(app)
manager = Manager(app)
bootstrap = Bootstrap(app)
migrate = Migrate(app, db)
manager.add_command('db', MigrateCommand)
manager.add_command('shell', Shell(make_shell_context))
login_manager = LoginManager(app)

login_manager.session_protection = 'strong'
login_manager.login_view = 'login'
login_manager.login_message = u"你需要登录才能访问这个页面."


'''
Models
'''

class Role(db.Model):
	__tablename__ = 'roles'
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(64), unique=True)
	users = db.relationship('User', backref='role', lazy='dynamic')
	devices = db.relationship('Device', backref='role', lazy='dynamic')

	@staticmethod
	def insert_roles():
		roles = ('Student', 'Admin')
		for r in roles:
			role = Role.query.filter_by(name=r).first()
			if role is None:
				role = Role(name=r)
			db.session.add(role)
		db.session.commit()

	def __repr__(self):
		return '<Role %r>' % self.name


class User(UserMixin, db.Model):
	__tablename__ = 'users'
	id = db.Column(db.Integer, primary_key=True)
	number = db.Column(db.SmallInteger, unique=True, index=True)
	username = db.Column(db.String(64), unique=True,index=True)
	# password = db.Column(db.String(128), default=123456)
	password_hash = db.Column(db.String(128))
	role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))

	def __init__(self, **kwargs):
		super(User, self).__init__(**kwargs)
		# 新添加的用户，初始其角色为学生。
		if self.role is None:
			self.role = Role.query.filter_by(name='Student').first()

	def __repr__(self):
		return '<User %r>' % self.username

	# 初次运行程序时生成初始管理员的静态方法
	@staticmethod
	def generate_admin():
		admin = Role.query.filter_by(name='Admin').first()
		u = User.query.filter_by(role=admin).first()
		if u is None:
			u = User(number=000000, username='Admin', role=Role.query.filter_by(name='Admin').first())
			u.set_password(current_app.config['AdminPassword'])
			db.session.add(u)
		db.session.commit()

	#def verify_password(self, password):
	#	return self.password == password

	def validate_password(self, password):
		return check_password_hash(self.password_hash, password)

	def set_password(self, password):
		self.password_hash = generate_password_hash(password)


class Device(UserMixin, db.Model):
	__tablename__ = 'devices'
	id = db.Column(db.Integer, primary_key=True)
	lab = db.Column(db.String(64), unique=True, index=True)
	name = db.Column(db.String(64), index=True)
	time = db.Column(db.DateTime, default=datetime.utcnow)
	role_id = db.Column(db.String(64), db.ForeignKey('users.id'))

	def __init__(self, **kwargs):
		super(Device, self).__init__(**kwargs)
		#新添加的实验设备，初始其购置人为管理员。
		if self.role is None:
			self.role = Role.query.filter_by(name='Admin').first()

	def __repr__(self):
		return '<Device %r>' %self.name


'''
Forms
'''

class LoginForm(FlaskForm):
	number = StringField(u'账号', validators=[Required()])
	password = PasswordField(u'密码', validators=[Required()])
	remember_me = BooleanField(u'记住我')
	submit = SubmitField(u'登录')


class SearchForm(FlaskForm):
	id = IntegerField(u'设备号', validators=[Required(message=u'请输入数字')])
	submit = SubmitField(u'搜索')


class DeviceForm(FlaskForm):
	name = StringField(u'设备名', validators=[Required()])
	id = IntegerField(u'设备编号', validators=[Required(message=u'请输入数字')])
	submit = SubmitField(u'添加')

	def validate_number(self, field):
		if Device.query.filter_by(id=field.data).first():
			raise ValidationError(u'此设备已存在，请检查考号！')

'''
views
'''
@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
	form = SearchForm()
	admin = Role.query.filter_by(name='Admin').first()
	if form.validate_on_submit():
		#获得设备列表，其id包含form中的数字
		devices = Device.query.filter(Device.lab.like('%{}%'.format(form.id.data))).all()
	else:
		devices = Device.query.order_by(Device.role_id.desc(), Device.lab.asc()).all()
	return render_template('index.html', form=form, devices=devices, admin=admin)


#增加新设备
@app.route('/add-user', methods=['GET', 'POST'])
@login_required
def add_device():
	form = DeviceForm()
	if form.validate_on_submit():
		user = Device(name=form.name.data, id=form.id.data)
		db.session.add(user)
		flash(u'成功添加设备')
		return redirect(url_for('index'))
	return render_template('add_user.html', form=form)


#移除设备
@app.route('/remove-user/<int:id>', methods=['GET', 'POST'])
@login_required
def remove_device(id):
	device = Device.query.get_or_404(id)
	if device.role == Role.query.filter_by(name='Admin').first():
		flash(u'不能删除管理员添加的设备')
	else:
		db.session.delete(device)
		flash(u'成功删除此设备')
	return redirect(url_for('index'))

#登录，系统只允许管理员登录
@app.route('/login', methods=['GET', 'POST'])
def login():
	form  = LoginForm()
	if form.validate_on_submit():
		user = User.query.filter_by(number=form.number.data).first()
		if user is not None and user.validate_password(form.password.data): #user.verify_password(form.password.data):
			if user.role != Role.query.filter_by(name='Admin').first():
				flash(u'系统只对管理员开放，请联系管理员获得权限！')
			else:
				login_user(user, form.remember_me.data)
				return redirect(url_for('index'))
		flash(u'用户名或密码错误！')
	return render_template('login.html', form=form)


@app.route('/logout')
@login_required
def logout():
	logout_user()
	flash(u'成功注销！')
	return redirect(url_for('login'))

@app.errorhandler(404)
def page_not_found(e):
	return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
	return render_template('500.html'), 500

#加载用户的回调函数
@login_manager.user_loader
def load_user(user_id):
	return User.query.get(int(user_id))


'''
fake
'''
'''
def fake_admin():
    admin = User(name='',
                 username='lalala',
                 email='admin@helloflask.com',
                 bio=fake.sentence(),
                 website='http://character.com',
                 confirmed=True)
    admin.set_password('helloflask')
    notification = Notification(message='您好，欢迎来到文墨', receiver=admin)
    db.session.add(notification)
    db.session.add(admin)
    db.session.commit()
'''

def fake_user(count=10):
    for i in range(count):
        user = User(username=fake.name(),
                    email=fake.email(),
					role_id=2)
        user.set_password('123456')
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()

def fake_device(count=10):
    for i in range(count):
        device = Device(name=fake.name(),
					role_id=User.query.get(random.randint(1, User.query.count())),
                    email=fake.email(),
					time=fake.date_time_this_year(),
					lab=fake.company())
        db.session.add(device)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()

'''
增加命令'python app.py init' 
以增加身份与初始管理员帐号
'''
@manager.command
def init():
	from app import Role, User
	Role.insert_roles()
	User.generate_admin()
	fake_user()
	fake_device()



if __name__=='__main__':
	manager.run()
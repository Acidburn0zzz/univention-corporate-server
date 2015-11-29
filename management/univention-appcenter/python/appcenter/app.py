#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
#
# Univention App Center
#  Application class
#
# Copyright 2015 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.
#

import os
import os.path
from glob import glob
import re
from ConfigParser import RawConfigParser, NoOptionError, NoSectionError, MissingSectionHeaderError
from copy import copy
from cgi import escape as cgi_escape
from distutils.version import LooseVersion
import platform
from inspect import getargspec

from univention.config_registry import ConfigRegistry
from univention.lib.package_manager import PackageManager

from univention.appcenter.log import get_base_logger
from univention.appcenter.meta import UniventionMetaClass, UniventionMetaInfo
from univention.appcenter.utils import app_ports, mkdir, get_current_ram_available, get_locale, _


CACHE_DIR = '/var/cache/univention-appcenter'
LOCAL_ARCHIVE = '/usr/share/univention-appcenter/archives/all.tar.gz'
SHARE_DIR = '/usr/share/univention-appcenter/apps'
DATA_DIR = '/var/lib/univention-appcenter/apps'
CONTAINER_SCRIPTS_PATH = '/usr/share/univention-docker-container-mode/'

app_logger = get_base_logger().getChild('apps')


def _read_ini_file(filename):
	parser = RawConfigParser()
	try:
		with open(filename, 'rb') as f:
			parser.readfp(f)
	except (IOError, MissingSectionHeaderError):
		pass
	return parser


def _get_from_parser(parser, section, attr):
	try:
		return parser.get(section, attr)
	except (NoSectionError, NoOptionError):
		return None


def _get_rating_items():
	if _get_rating_items._items is None:
		_get_rating_items._items = []
		rating_parser = _read_ini_file(os.path.join(CACHE_DIR, '.rating.ini'))
		locale = get_locale()
		for section in rating_parser.sections():
			label = _get_from_parser(rating_parser, section, 'Label')
			if locale:
				label = _get_from_parser(rating_parser, section, 'Label[%s]' % locale) or label
			description = _get_from_parser(rating_parser, section, 'Description')
			if locale:
				description = _get_from_parser(rating_parser, section, 'Description[%s]' % locale) or description
			item = {'name': section, 'description': description, 'label': label}
			_get_rating_items._items.append(item)
	return [itm.copy() for itm in _get_rating_items._items]
_get_rating_items._items = None


class CaseSensitiveConfigParser(RawConfigParser):
	def optionxform(self, optionstr):
		return optionstr


class Requirement(UniventionMetaInfo):
	save_as_list = '_requirements'
	auto_set_name = True
	pop = True

	def __init__(self, actions, hard, func):
		self.actions = actions
		self.hard = hard
		self.func = func

	def test(self, app, function, package_manager, ucr):
		method = getattr(app, self.name)
		kwargs = {}
		arguments = getargspec(method).args[1:]  # remove self
		if 'function' in arguments:
			kwargs['function'] = function
		if 'package_manager' in arguments:
			kwargs['package_manager'] = package_manager
		if 'ucr' in arguments:
			kwargs['ucr'] = ucr
		return method(**kwargs)

	def contribute_to_class(self, klass, name):
		super(Requirement, self).contribute_to_class(klass, name)
		setattr(klass, name, self.func)


def hard_requirement(*actions):
	return lambda func: Requirement(actions, True, func)


def soft_requirement(*actions):
	return lambda func: Requirement(actions, False, func)


class AppAttribute(UniventionMetaInfo):
	save_as_list = '_attrs'
	auto_set_name = True

	def __init__(self, required=False, default=None, regex=None, choices=None, escape=True, localisable=False, localisable_by_file=None, strict=True):
		super(AppAttribute, self).__init__()
		self.regex = regex
		self.default = default
		self.required = required
		self.choices = choices
		self.escape = escape
		self.localisable = localisable
		self.localisable_by_file = localisable_by_file
		self.strict = strict

	def test_regex(self, regex, value):
		if value is not None and not re.match(regex, value):
			raise ValueError('Invalid format')

	def test_choices(self, value):
		if value is not None and value not in self.choices:
			raise ValueError('Not allowed')

	def test_required(self, value):
		if value is None:
			raise ValueError('Value required')

	def test_type(self, value, instance_type):
		if value is not None:
			if instance_type is None:
				instance_type = basestring
			if not isinstance(value, instance_type):
				raise ValueError('Wrong type')

	def parse_with_ini_file(self, value, ini_file):
		return self.parse(value)

	def test(self, value):
		try:
			if self.required:
				self.test_required(value)
			self.test_type(value, basestring)
			if self.choices:
				self.test_choices(value)
			if self.regex:
				self.test_regex(self.regex, value)
		except ValueError as e:
			if self.strict:
				raise
			else:
				app_logger.warn(str(e))

	def parse(self, value):
		if self.escape and value:
			value = cgi_escape(value)
		return value

	def get(self, value, ini_file):
		if value is None:
			value = copy(self.default)
		try:
			value = self.parse_with_ini_file(value, ini_file)
		except ValueError as exc:
			raise ValueError('%s: %s (%r): %s' % (ini_file, self.name, value, exc))
		else:
			self.test(value)
			return value


class AppBooleanAttribute(AppAttribute):
	def test_type(self, value, instance_type):
		super(AppBooleanAttribute, self).test_type(value, bool)

	def parse(self, value):
		if value in [True, False]:
			return value
		if value is not None:
			value = RawConfigParser._boolean_states.get(str(value).lower())
			if value is None:
				raise ValueError('Invalid value')
		return value


class AppIntAttribute(AppAttribute):
	def test_type(self, value, instance_type):
		super(AppIntAttribute, self).test_type(value, int)

	def parse(self, value):
		if value is not None:
			return int(value)


class AppListAttribute(AppAttribute):
	def parse(self, value):
		if value == '':
			value = None
		if isinstance(value, basestring):
			value = re.split('\s*,\s*', value)
		if value is None:
			value = []
		return value

	def test_required(self, value):
		if not value:
			raise ValueError('Value required')

	def test_type(self, value, instance_type):
		super(AppListAttribute, self).test_type(value, list)

	def test_choices(self, value):
		if not value:
			return
		for val in value:
			super(AppListAttribute, self).test_choices(val)

	def test_regex(self, regex, value):
		if not value:
			return
		for val in value:
			super(AppListAttribute, self).test_regex(regex, val)


class AppLocalisedListAttribute(AppListAttribute):
	_cache = {}

	@classmethod
	def _translate(cls, fname, locale, value, reverse=False):
		if fname not in cls._cache:
			cls._cache[fname] = translations = {}
			localiser = CaseSensitiveConfigParser()
			cached_file = os.path.join(CACHE_DIR, '.%s' % fname)
			try:
				with open(cached_file, 'rb') as f:
					localiser.readfp(f)
			except IOError:
				pass
			else:
				for section in localiser.sections():
					translations[section] = dict(localiser.items(section))
		translations = cls._cache[fname].get(locale)
		if translations:
			if reverse:
				for k, v in translations.iteritems():
					if v == value:
						value = k
						break
			else:
				if value in translations:
					value = translations[value]
		return value

	def parse(self, value):
		value = super(AppLocalisedListAttribute, self).parse(value)
		locale = get_locale()
		if self.localisable_by_file and locale:
			for i, val in enumerate(value):
				value[i] = self._translate(self.localisable_by_file, locale, val)
		return value

	def test_choices(self, value):
		value = value[:]
		locale = get_locale()
		for i, val in enumerate(value):
			value[i] = self._translate(self.localisable_by_file, locale, val, reverse=True)
		super(AppLocalisedListAttribute, self).test_choices(value)


class AppAttributeOrFalseOrNone(AppBooleanAttribute):
	def __init__(self, required=False, default=None, regex=None, choices=None, escape=True, localisable=False, localisable_by_file=None, strict=True):
		choices = (choices or [])[:]
		choices.extend([None, False])
		super(AppAttributeOrFalseOrNone, self).__init__(required, default, regex, choices, escape, localisable, localisable_by_file, strict)

	def parse(self, value):
		if value == 'False':
			value = False
		elif value == 'None':
			value = None
		return value

	def test_type(self, value, instance_type):
		if value is not False and value is not None:
			super(AppBooleanAttribute, self).test_type(value, basestring)


class AppFileAttribute(AppAttribute):
	# TODO: UCR TOKEN
	def __init__(self, required=False, default=None, regex=None, choices=None, escape=False, localisable=True):
		# escape=False, localisable=True !
		super(AppFileAttribute, self).__init__(required, default, regex, choices, escape, localisable)

	def parse_with_ini_file(self, value, ini_file):
		filename = self.get_filename(ini_file)
		if filename:
			with open(filename, 'rb') as fhandle:
				value = ''.join(fhandle.readlines()).strip()
		return super(AppFileAttribute, self).parse_with_ini_file(value, ini_file)

	def get_filename(self, ini_file):
		directory = os.path.dirname(ini_file)
		component_id = os.path.splitext(os.path.basename(ini_file))[0]
		fname = self.name.upper()
		localised_file_exts = [fname, '%s_EN' % fname]
		if self.localisable:
			locale = get_locale()
			if locale:
				localised_file_exts.insert(0, '%s_%s' % (fname, locale.upper()))
		for localised_file_ext in localised_file_exts:
			filename = os.path.join(directory, '%s.%s' % (component_id, localised_file_ext))
			if os.path.exists(filename):
				return filename


class AppDockerScriptAttribute(AppAttribute):
	def set_name(self, name):
		self.default = os.path.join(CONTAINER_SCRIPTS_PATH, name[14:])
		super(AppDockerScriptAttribute, self).set_name(name)


class App(object):
	__metaclass__ = UniventionMetaClass

	id = AppAttribute(regex='^[a-zA-Z0-9]+(([a-zA-Z0-9-_]+)?[a-zA-Z0-9])?$', required=True)
	code = AppAttribute(regex='^[A-Za-z0-9]{2}$', required=True)
	component_id = AppAttribute(required=True)
	ucs_version = AppAttribute(required=True)

	name = AppAttribute(required=True, localisable=True)
	version = AppAttribute(required=True)
	description = AppAttribute(localisable=True)
	long_description = AppAttribute(escape=False, localisable=True)
	thumbnails = AppListAttribute(localisable=True)
	screenshot = AppAttribute(localisable=True)  # deprecated, use thumbnails instead
	categories = AppLocalisedListAttribute(choices=['Administration', 'Business', 'Collaboration', 'Education', 'System services', 'UCS components', 'Virtualization', ''], localisable_by_file='categories.ini', strict=False)

	website = AppAttribute(localisable=True)
	support_url = AppAttribute(localisable=True)
	contact = AppAttribute()
	vendor = AppAttribute()
	website_vendor = AppAttribute(localisable=True)
	maintainer = AppAttribute()
	website_maintainer = AppAttribute(localisable=True)

	license_agreement = AppFileAttribute()
	readme = AppFileAttribute()
	readme_install = AppFileAttribute()
	readme_post_install = AppFileAttribute()
	readme_update = AppFileAttribute()
	readme_post_update = AppFileAttribute()
	readme_uninstall = AppFileAttribute()
	readme_post_uninstall = AppFileAttribute()

	notify_vendor = AppBooleanAttribute(default=True)
	notification_email = AppAttribute()

	web_interface = AppAttribute()
	web_interface_name = AppAttribute()
	web_interface_port_http = AppIntAttribute(default=80)
	web_interface_port_https = AppIntAttribute(default=443)
	auto_mod_proxy = AppBooleanAttribute(default=True)
	ucs_overview_category = AppAttributeOrFalseOrNone(default='service', choices=['admin', 'service'])

	conflicted_apps = AppListAttribute()
	required_apps = AppListAttribute()
	conflicted_system_packages = AppListAttribute()
	required_ucs_version = AppAttribute(regex=r'^(\d+)\.(\d+)-(\d+)(?: errata(\d+))?$')
	end_of_life = AppBooleanAttribute()

	without_repository = AppBooleanAttribute()
	default_packages = AppListAttribute()
	default_packages_master = AppListAttribute()

	rating = AppListAttribute()

	umc_module_name = AppAttribute()
	umc_module_flavor = AppAttribute()

	user_activation_required = AppBooleanAttribute()

	ports_exclusive = AppListAttribute(regex='^\d+$')
	ports_redirection = AppListAttribute(regex='^\d+:\d+$')

	server_role = AppListAttribute(default=['domaincontroller_master', 'domaincontroller_backup', 'domaincontroller_slave', 'memberserver'], choices=['domaincontroller_master', 'domaincontroller_backup', 'domaincontroller_slave', 'memberserver'])
	supported_architectures = AppListAttribute(default=['amd64', 'i386'], choices=['amd64', 'i386'])
	min_physical_ram = AppIntAttribute(default=0)

	#use_shop = AppBooleanAttribute(localisable=True)
	shop_url = AppAttribute(localisable=True)

	ad_member_issue_hide = AppBooleanAttribute()
	ad_member_issue_password = AppBooleanAttribute()

	app_report_object_type = AppAttribute()
	app_report_object_filter = AppAttribute()
	app_report_object_attribute = AppAttribute()
	app_report_attribute_type = AppAttribute()
	app_report_attribute_filter = AppAttribute()

	docker_image = AppAttribute()
	docker_shell_command = AppAttribute(default='/bin/bash')
	docker_allowed_images = AppListAttribute()
	docker_volumes = AppListAttribute()
	docker_server_role = AppAttribute(default='memberserver', choices=['memberserver', 'domaincontroller_slave'])
	docker_script_init = AppAttribute(default='/sbin/init')
	docker_script_setup = AppDockerScriptAttribute()
	docker_script_store_data = AppDockerScriptAttribute()
	docker_script_restore_data_before_setup = AppDockerScriptAttribute()
	docker_script_restore_data_after_setup = AppDockerScriptAttribute()
	docker_script_update_available = AppDockerScriptAttribute()
	docker_script_update_packages = AppDockerScriptAttribute()
	docker_script_update_release = AppDockerScriptAttribute()
	docker_script_update_app_version = AppDockerScriptAttribute()

	def __init__(self, **kwargs):
		self._is_ucs_component = None
		for attr in self._attrs:
			setattr(self, attr.name, kwargs.get(attr.name))
		if self.docker:
			self.supported_architectures = ['amd64']
		self._has_logo_detail_page = None

	def attrs_dict(self):
		ret = {}
		for attr in self._attrs:
			ret[attr.name] = getattr(self, attr.name)
		return ret

	def get_docker_image_name(self):
		image = self.get_docker_images()[0]
		if self.is_installed():
			ucr = ConfigRegistry()
			ucr.load()
			image = ucr.get(self.ucr_image_key) or image
		return image

	def get_docker_images(self):
		return [self.docker_image] + self.docker_allowed_images

	def has_local_web_interface(self):
		if self.web_interface:
			return self.web_interface.startswith('/')

	def __str__(self):
		return '%s=%s' % (self.id, self.version)

	def __repr__(self):
		return 'App(id="%s" version="%s")' % (self.id, self.version)

	@classmethod
	def from_ini(cls, ini_file, locale=True):
		app_logger.debug('Loading app from %s' % ini_file)
		if locale is True:
			locale = get_locale()
		component_id = os.path.splitext(os.path.basename(ini_file))[0]
		meta_file = os.path.join(CACHE_DIR, '%s.meta' % component_id)
		ini_parser = _read_ini_file(ini_file)
		if os.path.exists(meta_file):
			app_logger.debug('Using additional %s' % meta_file)
			meta_parser = _read_ini_file(meta_file)
		else:
			meta_parser = RawConfigParser()  # empty
		attr_values = {}
		for attr in cls._attrs:
			value = None
			if attr.name == 'component_id':
				value = component_id
			if attr.name == 'ucs_version':
				# TODO: ucr.get('version/version')
				value = '4.1'
			elif attr.name == 'rating':
				value = []
				rating_items = _get_rating_items()
				for item in rating_items:
					val = _get_from_parser(meta_parser, 'Application', item['name'])
					try:
						val = int(val)
					except (ValueError, TypeError):
						pass
					else:
						item['value'] = val
						value.append(item)
			else:
				ini_attr_name = attr.name.replace('_', '')
				priority_sections = [(meta_parser, 'Application'), (ini_parser, 'Application')]
				if attr.localisable and locale:
					priority_sections.insert(0, (meta_parser, locale))
					priority_sections.insert(2, (ini_parser, locale))
				for parser, section in priority_sections:
					try:
						value = parser.get(section, ini_attr_name)
					except (NoSectionError, NoOptionError):
						pass
					else:
						break
			try:
				value = attr.get(value, ini_file)
			except ValueError as e:
				app_logger.error('Ignoring %s because of %s: %s' % (ini_file, attr.name, e))
				return
			attr_values[attr.name] = value
		return cls(**attr_values)

	@property
	def docker(self):
		return self.docker_image is not None

	@property
	def ucr_status_key(self):
		return 'appcenter/apps/%s/status' % self.id

	@property
	def ucr_version_key(self):
		return 'appcenter/apps/%s/version' % self.id

	@property
	def ucr_upgrade_key(self):
		return 'appcenter/apps/%s/update/available' % self.id

	@property
	def ucr_container_key(self):
		return 'appcenter/apps/%s/container' % self.id

	@property
	def ucr_hostdn_key(self):
		return 'appcenter/apps/%s/hostdn' % self.id

	@property
	def ucr_image_key(self):
		return 'appcenter/apps/%s/image' % self.id

	@property
	def ucr_ip_key(self):
		return 'appcenter/apps/%s/ip' % self.id

	@property
	def ucr_ports_key(self):
		return 'appcenter/apps/%s/ports/%%s' % self.id

	@property
	def ucr_component_key(self):
		return 'repository/online/component/%s' % self.component_id

	def get_attr(self, attr_name):
		for attr in self._attrs:
			if attr.name == attr_name:
				return attr

	def is_installed(self):
		ucr = ConfigRegistry()
		ucr.load()
		if self.docker:
			return ucr.get(self.ucr_status_key) in ['installed', 'stalled'] and ucr.get(self.ucr_version_key) == self.version
		else:
			if not self.without_repository:
				if self.ucr_component_key not in ucr:
					return False
			package_manager = AppManager.get_package_manager()
			for package_name in self.default_packages:
				try:
					package = package_manager.get_package(package_name, raise_key_error=True)
				except KeyError:
					return False
				else:
					if not package.is_installed:
						return False
			return True

	def is_ucs_component(self):
		if self._is_ucs_component is None:
			app = App.from_ini(self.get_ini_file(), locale=False)
			self._is_ucs_component = 'UCS Components' in app.categories
		return self._is_ucs_component

	def get_share_dir(self):
		return os.path.join(SHARE_DIR, self.id)

	def get_share_file(self, ext):
		return os.path.join(self.get_share_dir(), '%s.%s' % (self.id, ext))

	def get_data_dir(self):
		return os.path.join(DATA_DIR, self.id, 'data')

	def get_conf_dir(self):
		return os.path.join(DATA_DIR, self.id, 'conf')

	def get_conf_file(self, fname):
		if fname.startswith('/'):
			fname = fname[1:]
		fname = os.path.join(self.get_conf_dir(), fname)
		if not os.path.exists(fname):
			mkdir(os.path.dirname(fname))
		return fname

	def get_cache_file(self, ext):
		return os.path.join(CACHE_DIR, '%s.%s' % (self.component_id, ext))

	def get_ini_file(self):
		return self.get_cache_file('ini')

	@property
	def logo_name(self):
		return 'apps-%s.svg' % self.component_id

	@property
	def logo_detail_page_name(self):
		if self._has_logo_detail_page is None:
			# cache value
			self._has_logo_detail_page = os.path.exists(self.get_cache_file('logodetailpage'))
		if self._has_logo_detail_page:
			return 'apps-%s-detail.svg' % self.component_id
		return None

	def get_screenshot_url(self):
		if not self.screenshot:
			return None
		app_path = '%s/' % self.id
		if self.ucs_version == '4.0' or self.ucs_version.startswith('3.'):
			# since UCS 4.1, each app has a separate subdirectory
			app_path = ''
		return '%s/meta-inf/%s/%s%s' % (AppManager.get_server(), self.ucs_version, app_path, self.screenshot)

	def get_thumbnail_urls(self):
		if not self.thumbnails:
			return []
		thumbnails = []
		for ithumb in self.thumbnails:
			if ithumb.startswith('http://') or ithumb.startswith('https://'):
				# item is already a full URI
				thumbnails.append(ithumb)
				continue

			app_path = '%s/' % self.id
			if self.ucs_version == '4.0' or self.ucs_version.startswith('3.'):
				# since UCS 4.1, each app has a separate subdirectory
				app_path = ''
			thumbnails.append('%s/meta-inf/%s/%s%s' % (AppManager.get_server(), self.ucs_version, app_path, ithumb))
		return thumbnails

	def get_localised(self, key, loc=None):
		from univention.appcenter import get_action
		get = get_action('get')()
		keys = [(loc, key)]
		for section, name, value in get.get_values(self, keys, warn=False):
			return value

	def get_localised_list(self, key, loc=None):
		from univention.appcenter import get_action
		get = get_action('get')()
		ret = []
		key = key.replace('_', '').lower()
		keys = [(None, key), ('de', key)]
		for section, name, value in get.get_values(self, keys, warn=False):
			if value is None:
				continue
			if section is None:
				section = 'en'
			value = '[%s] %s' % (section, value)
			ret.append(value)
		return ret

	@hard_requirement('install', 'upgrade')
	def must_have_fitting_ucs_version(self, ucr):
		required_version = self.required_ucs_version
		if not required_version:
			return True
		version_bits = re.match(r'^(\d+)\.(\d+)-(\d+)(?: errata(\d+))?$', required_version).groups()
		major, minor = ucr.get('version/version').split('.', 1)
		patchlevel = ucr.get('version/patchlevel')
		errata = ucr.get('version/erratalevel')
		comparisons = zip(version_bits, [major, minor, patchlevel, errata])
		for required, present in comparisons:
			if int(required or 0) > int(present):
				return {'required_version': required_version}
		return True

	@hard_requirement('install', 'upgrade')
	def must_have_fitting_kernel_version(self, ucr):
		if self.docker:
			kernel = LooseVersion(os.uname()[2])
			if kernel < LooseVersion('4.1'):
				return False
		return True

	@hard_requirement('install', 'upgrade')
	def must_not_be_docker_if_docker_is_disabled(self, ucr):
		'''The application uses a container technology while the App Center
		is configured to not not support it'''
		return not self.docker or ucr.is_true('appcenter/docker', True)

	@hard_requirement('install', 'upgrade')
	def must_not_be_docker_in_docker(self, ucr):
		'''The application uses a container technology while the system
		itself runs in a container. Using the application is not
		supported on this host'''
		return not self.docker or not ucr.get('docker/container/uuid')

	@hard_requirement('install', 'upgrade')
	def must_have_valid_license(self, ucr):
		'''For the installation of this application, a UCS license key
		with a key identification (Key ID) is required'''
		if self.notify_vendor:
			return ucr.get('uuid/license') is not None
		return True

	@hard_requirement('install')
	def must_not_be_installed(self):
		'''This application is already installed'''
		return not self.is_installed()

	@hard_requirement('install')
	def must_not_be_end_of_life(self):
		'''This application was discontinued and may not be installed
		anymore'''
		return not self.end_of_life

	@hard_requirement('install', 'upgrade')
	def must_have_supported_architecture(self):
		'''This application only supports %(supported)s as
		architecture. %(msg)s'''
		supported_architectures = self.supported_architectures
		platform_bits = platform.architecture()[0]
		aliases = {'i386': '32bit', 'amd64': '64bit'}
		if supported_architectures:
			for architecture in supported_architectures:
				if aliases[architecture] == platform_bits:
					break
			else:
				# For now only two architectures are supported:
				#   32bit and 64bit - and this will probably not change
				#   too soon.
				# So instead of returning lists and whatnot
				#   just return a nice message
				# Needs to be adapted when supporting different archs
				supported = supported_architectures[0]
				if supported == 'i386':
					needs = 32
					has = 64
				else:
					needs = 64
					has = 32
				msg = _('The application needs a %(needs)s-bit operating system. This server is running a %(has)s-bit operating system.') % {'needs': needs, 'has': has}
				return {'supported': supported, 'msg': msg}
		return True

	@hard_requirement('install', 'upgrade')
	def must_be_joined_if_master_packages(self):
		'''This application requires an extension of the LDAP schema'''
		is_joined = os.path.exists('/var/univention-join/joined')
		return bool(is_joined or not self.default_packages_master)

	@hard_requirement('install', 'upgrade', 'remove')
	def must_not_have_concurrent_operation(self, package_manager):
		'''Another package operation is in progress'''
		if self.docker:
			return True
		else:
			return package_manager.progress_state._finished  # TODO: package_manager.is_finished()

	@hard_requirement('install', 'upgrade')
	def must_have_correct_server_role(self, ucr):
		'''The application cannot be installed on the current server
		role (%(current_role)s). In order to install the application,
		one of the following roles is necessary: %(allowed_roles)r'''
		server_role = ucr.get('server/role')
		if not self._allowed_on_local_server(ucr):
			return {
				'current_role': server_role,
				'allowed_roles': ', '.join(self.server_role),
			}
		return True

	@hard_requirement('install', 'upgrade')
	def must_have_no_conflicts_packages(self, package_manager):
		'''The application conflicts with the following packages: %r'''
		conflict_packages = []
		for pkgname in self.conflicted_system_packages:
			if package_manager.is_installed(pkgname):
				conflict_packages.append(pkgname)
		if conflict_packages:
			return conflict_packages
		return True

	@hard_requirement('install', 'upgrade')
	def must_have_no_conflicts_apps(self, ucr):
		'''The application conflicts with the following applications:
			%r'''
		conflictedapps = []
		# check ConflictedApps
		for app in AppManager.get_all_apps():
			if not app._allowed_on_local_server(ucr):
				# cannot be installed, continue
				continue
			if app.id in self.conflicted_apps or self.id in app.conflicted_apps:
				if app.is_installed():
					conflictedapps.append({'id': app.id, 'name': app.name})
		# check port conflicts
		ports = []
		for i in self.ports_exclusive:
			ports.append(i)
		for i in self.ports_redirection:
			ports.append(i.split(':', 1)[0])
		for app_id, container_port, host_port in app_ports():
			if app_id != self.id and str(host_port) in ports:
				conflictedapps.append({'id': app_id})
		if conflictedapps:
			return conflictedapps
		return True

	@hard_requirement('install', 'upgrade')
	def must_have_no_unmet_dependencies(self):
		'''The application requires the following applications: %r'''
		unmet_packages = []
		for app in AppManager.get_all_apps():
			if app.id in self.required_apps:
				if not app.is_installed():
					unmet_packages.append({'id': app.id, 'name': app.name})
		if unmet_packages:
			return unmet_packages
		return True

	@hard_requirement('remove')
	def must_not_be_depended_on(self):
		'''The application is required for the following applications
		to work: %r'''
		depending_apps = []
		for app in AppManager.get_all_apps():
			if self.id in app.required_apps and app.is_installed():
				depending_apps.append({'id': app.id, 'name': app.name})
		if depending_apps:
			return depending_apps
		return True

	@soft_requirement('install', 'upgrade')
	def shall_have_enough_ram(self, function):
		'''The application requires %(minimum)d MB of free RAM but only
		%(current)d MB are available.'''
		current_ram = get_current_ram_available()
		required_ram = self.min_physical_ram
		if function == 'upgrade':
			# is already installed, just a minor version upgrade
			#   RAM "used" by this installed app should count
			#   as free. best approach: substract it
			installed_app = AppManager.find(self)
			old_required_ram = installed_app.min_physical_ram
			required_ram = required_ram - old_required_ram
		if current_ram < required_ram:
			return {'minimum': required_ram, 'current': current_ram}
		return True

	@soft_requirement('install', 'upgrade')
	def shall_only_be_installed_in_ad_env_with_password_service(self, ucr):
		'''The application requires the password service to be set up
		on the Active Directory domain controller server.'''
		return not self._has_active_ad_member_issue(ucr, 'password')

	def check(self, function):
		package_manager = AppManager.get_package_manager()
		ucr = ConfigRegistry()
		ucr.load()
		hard_problems = {}
		soft_problems = {}
		for requirement in self._requirements:
			if function not in requirement.actions:
				continue
			app = self
			if function == 'upgrade':
				app = AppManager.find(self)
				if app > self:
					# upgrade is not possible,
					#   special handling
					hard_problems['must_have_candidate'] = False
					continue
			result = requirement.test(app, function, package_manager, ucr)
			if result is not True:
				if requirement.hard:
					hard_problems[requirement.name] = result
				else:
					soft_problems[requirement.name] = result
		return hard_problems, soft_problems

	def _allowed_on_local_server(self, ucr):
		server_role = ucr.get('server/role')
		allowed_roles = self.server_role
		return not allowed_roles or server_role in allowed_roles

	def _has_active_ad_member_issue(self, ucr, issue):
		return ucr.is_true('ad/member') and getattr(self, 'ad_member_issue_%s' % issue, False)

	def __cmp__(self, other):
		return cmp(self.id, other.id) or cmp(LooseVersion(self.version), LooseVersion(other.version))


class AppManager(object):
	_cache = []
	_package_manager = None

	@classmethod
	def clear_cache(cls):
		cls._cache[:] = []
		cls.reload_package_manager()
		_get_rating_items._items = None

	@classmethod
	def _get_every_single_app(cls):
		if not cls._cache:
			for ini in glob(os.path.join(CACHE_DIR, '*.ini')):
				app = App.from_ini(ini)
				if app is not None:
					cls._cache.append(app)
			cls._cache.sort()
		return cls._cache

	@classmethod
	def get_all_apps(cls):
		ret = []
		ids = set()
		for app in cls._get_every_single_app():
			ids.add(app.id)
		for app_id in sorted(ids):
			ret.append(cls.find(app_id))
		return ret

	@classmethod
	def get_all_locally_installed_apps(cls):
		ret = []
		for app in cls._get_every_single_app():
			if app.is_installed():
				ret.append(app)
		return ret

	@classmethod
	def find_by_component_id(cls, component_id):
		for app in cls._get_every_single_app():
			if app.component_id == component_id:
				return app

	@classmethod
	def get_all_apps_with_id(cls, app_id):
		ret = []
		for app in cls._get_every_single_app():
			if app.id == app_id:
				ret.append(app)
		return ret

	@classmethod
	def find(cls, app_id, app_version=None, latest=False):
		if isinstance(app_id, App):
			app_id = app_id.id
		apps = cls.get_all_apps_with_id(app_id)
		if app_version:
			for app in apps:
				if app.version == app_version:
					return app
		elif not latest:
			for app in apps:
				if app.is_installed():
					return app
		if apps:
			return apps[-1]

	@classmethod
	def reload_package_manager(cls):
		if cls._package_manager is None:
			return
		return cls._package_manager.reopen_cache()

	@classmethod
	def get_package_manager(cls):
		if cls._package_manager is None:
			cls._package_manager = PackageManager(lock=False)
			cls._package_manager.set_finished()  # currently not working. accepting new tasks
			cls._package_manager.logger.parent = get_base_logger()
		return cls._package_manager

	@classmethod
	def set_package_manager(cls, package_manager):
		cls._package_manager = package_manager

	@classmethod
	def get_server(cls):
		ucr = ConfigRegistry()
		ucr.load()
		server = ucr.get('repository/app_center/server', 'appcenter.software-univention.de')
		if not server.startswith('http'):
			server = 'https://%s' % server
		return server

# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  hook definitions
#
# Copyright 2004-2018 Univention GmbH
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

import univention.debug
import univention.admin.modules
import univention.admin.uexceptions
from univention.admin import localization
import sys
import os
import traceback

translation = localization.translation('univention/admin')
_ = translation.translate


def import_hook_files():
	"""
	Load all additional hook files :file:`hooks.d/*.py`.
	"""
	base = os.path.join(os.path.dirname(__file__), 'hooks.d')
	if not os.path.isdir(base):
		return
	for f in os.listdir(base):
						if not f.endswith('.py'):
							continue
						fn = os.path.join(base, f)
						try:
							with open(fn, 'r') as fd:
								exec fd in sys.modules[__name__].__dict__
							univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'admin.syntax.import_hook_files: importing "%s"' % fn)
						except:
							univention.debug.debug(univention.debug.ADMIN, univention.debug.ERROR, 'admin.syntax.import_hook_files: loading %s failed' % fn)
							univention.debug.debug(univention.debug.ADMIN, univention.debug.ERROR, 'admin.syntax.import_hook_files: TRACEBACK:\n%s' % traceback.format_exc())


class simpleHook(object):
	type = 'simpleHook'

	#
	# To use the LDAP connection of the parent UDM call in any of the following
	# methods, use obj.lo and obj.position.
	#

	def hook_open(self, obj):
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'admin.syntax.hook.simpleHook: _open called')

	def hook_ldap_pre_create(self, obj):
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'admin.syntax.hook.simpleHook: _ldap_pre_create called')

	def hook_ldap_addlist(self, obj, al=[]):
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'admin.syntax.hook.simpleHook: _ldap_addlist called')
		return al

	def hook_ldap_post_create(self, obj):
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'admin.syntax.hook.simpleHook: _ldap_post_create called')

	def hook_ldap_pre_modify(self, obj):
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'admin.syntax.hook.simpleHook: _ldap_pre_modify called')

	def hook_ldap_modlist(self, obj, ml=[]):
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'admin.syntax.hook.simpleHook: _ldap_modlist called')
		return ml

	def hook_ldap_post_modify(self, obj):
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'admin.syntax.hook.simpleHook: _ldap_post_modify called')

	def hook_ldap_pre_remove(self, obj):
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'admin.syntax.hook.simpleHook: _ldap_pre_remove called')

	def hook_ldap_post_remove(self, obj):
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'admin.syntax.hook.simpleHook: _ldap_post_remove called')


import_hook_files()

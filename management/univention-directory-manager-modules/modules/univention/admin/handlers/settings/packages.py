# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  admin module for package lists
#
# Copyright 2004-2019 Univention GmbH
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

from univention.admin.layout import Tab, Group
import univention.admin.syntax
import univention.admin.filter
import univention.admin.handlers
import univention.admin.localization

import univention.debug

translation = univention.admin.localization.translation('univention.admin.handlers.settings')
_ = translation.translate

module = 'settings/packages'
operations = ['add', 'edit', 'remove', 'search', 'move']
superordinate = 'settings/cn'

childs = 0
short_description = _('Settings: Package List')
object_name = _('Package List')
object_name_plural = _('Package Lists')
long_description = _('List of Packages for UCS Systems')
options = {
	'default': univention.admin.option(
		default=True,
		objectClasses=['top', 'univentionPackageList'],
	),
}
property_descriptions = {
	'name': univention.admin.property(
		short_description=_('Name'),
		long_description=_('Name'),
		syntax=univention.admin.syntax.string,
		include_in_default_search=True,
		required=True,
		may_change=True,
		identifies=True,
	),
	'packageList': univention.admin.property(
		short_description=_('Package List'),
		long_description=_('Package List'),
		syntax=univention.admin.syntax.string,
		multivalue=True,
		dontsearch=True,
		may_change=True,
		identifies=False,
	),
}

layout = [
	Tab(_('General'), _('Package List'), layout=[
		Group(_('General package list settings'), layout=[
			'name',
			'packageList',
		]),
	]),
]

mapping = univention.admin.mapping.mapping()
mapping.register('name', 'cn', None, univention.admin.mapping.ListToString)
mapping.register('packageList', 'univentionPackageDefinition')


class object(univention.admin.handlers.simpleLdap):
	module = module

	@classmethod
	def unmapped_lookup_filter(cls):
		return univention.admin.filter.conjunction('&', [
			univention.admin.filter.expression('objectClass', 'univentionPackageList')
		])


lookup = object.lookup


def identify(dn, attr, canonical=0):
	return 'univentionPackageList' in attr.get('objectClass', [])

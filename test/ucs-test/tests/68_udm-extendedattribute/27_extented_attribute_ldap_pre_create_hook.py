#!/usr/share/ucs-test/runner python
## desc: settings/extented_attribute LDAP pre create hook
## tags: [udm]
## roles: [domaincontroller_master]
## exposure: careful
## packages:
##   - univention-config
##   - univention-directory-manager-tools

import univention.testing.udm as udm_test
import univention.testing.utils as utils
import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import os
import atexit

if __name__ == '__main__':
	ucr = ucr_test.UCSTestConfigRegistry()
	ucr.load()

	hook_name = uts.random_name()

	atexit.register(os.remove, '/usr/lib/pymodules/python2.6/univention/admin/hooks.d/%s.py' % hook_name)
	atexit.register(os.remove, '/tmp/%s_executed' % hook_name)

	with open('/usr/lib/pymodules/python2.6/univention/admin/hooks.d/%s.py' % hook_name, 'w') as hook_module:
		hook_module.write("""
import univention.admin
import univention.admin.modules
import univention.admin.hook
import univention.admin.handlers.users.user
import univention.testing.utils

class %s(univention.admin.hook.simpleHook):
	def hook_ldap_pre_create(self, module):
		with open('/tmp/%s_executed', 'w') as fp:
			if not isinstance(module, univention.admin.handlers.users.user.object):
				fp.write('LDAP pre create Hook called with wrong object parameter (Type: %%s)' %% type(module))

			univention.testing.utils.wait_for_replication()
			try:
				univention.testing.utils.verify_ldap_object('uid=%s,cn=users,%s', should_exist = False)
			except univention.testing.utils.LDAPUnexpectedObjectFound:
				fp.write('\\nObject had already been created when LDAP pre create hook was called')
""" % (hook_name, hook_name, hook_name, ucr['ldap/base']))
					

	with udm_test.UCSTestUDM() as udm:
		udm.stop_cli_server()
		cli_name = uts.random_string()
		udm.create_object('settings/extended_attribute', position = udm.UNIVENTION_CONTAINER,
			name = uts.random_name(),
			shortDescription = uts.random_string(),
			CLIName = cli_name,
			module = 'users/user',
			objectClass = 'univentionFreeAttributes',
			ldapMapping = 'univentionFreeAttribute15',
			hook = hook_name
		)

		udm.create_user(**{cli_name: uts.random_string(), 'username': hook_name})[0]

		with open('/tmp/%s_executed' % hook_name) as fp:
			fails = fp.read()
			if fails:
				utils.fail(fails)

#!/usr/bin/python2.7
# vim:set fileencoding=utf-8:
#
# Univention SSH host key manager
#
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2018 Univention GmbH

name = 'univention-ssh'
description = 'Manage list of SSH known hosts from LDAP'
filter = 'objectClass=univentionHost'
attributes = [
	'univentionSshHostKey',
	'aRecord',
	'aAAARecord',
	'associatedDomain',
	'cn',
]
modrdn = "1"


__package__ = ''  # workaround for PEP 366
import listener
from os import fchmod
from subprocess import check_call
from ipaddr import IPv6Address
import univention.debug as ud

SKH = '/etc/ssh/ssh_known_hosts'


def initialize():
	"""
	Initialize UCS Listener module.
	"""
	ud.debug(ud.LISTENER, ud.PROCESS, "initialize()")
	with AsRoot():
		with open(SKH, 'a') as skh:
			fchmod(skh.fileno(), 0o644)


def handler(dn, new, old, command=''):
	"""
	Handle changes to SSH host keys.

	:param str dn: The distinguished name of the LDAP entry bying modified.
	:param dict new: The new LDAP values or None.
	:param dict old: The old LDAP values or None.
	:param str command: A single letter command specifying the LDAP operation.
	"""
	ud.debug(ud.LISTENER, ud.PROCESS, "handler(dn=%s new=%d old=%d command=%s)" % (dn, len(new), len(old), command))
	remove_old(old)
	add_new(new)


def remove_old(old):
	"""
	Remove all old SSH host keys associated to this host.

	:param dict old: The old LDAP values
	"""
	ud.debug(ud.LISTENER, ud.PROCESS, "remove_old(old=%d)" % (len(old),))
	if not old:
		return
	with AsRoot():
		for name in names(old):
			check_call(('ssh-keygen', '-R', name, '-f', SKH))


def add_new(new):
	"""
	Add all new SSH host keys associated to this host.

	:param dict new: The new LDAP values
	"""
	ud.debug(ud.LISTENER, ud.PROCESS, "add_new(new=%d)" % (len(new),))
	if not new:
		return
	if 'univentionSshHostKey' not in new:
		return
	keys = new['univentionSshHostKey']
	if not keys:
		return
	with AsRoot():
		with open(SKH, 'a') as skh:
			for name in names(new):
				for key in keys:
					skh.write('%s %s' % (name, key))


def names(values):
	"""
	Yield all names and addresses associated with the host.

	:param dict values: The old or new LDAP values.
	:returns: An iterator returning all names.
	"""
	val = values['cn'][0]
	ud.debug(ud.LISTENER, ud.PROCESS, "names: cn=%s" % (val,))
	yield val
	try:
		val = '%s.%s' % (values['cn'][0], values['associatedDomain'][0])
		ud.debug(ud.LISTENER, ud.PROCESS, "names: fqdn=%s" % (val,))
		yield val
	except LookupError:
		pass
	for ip in values.get('aRecord', []):
		ud.debug(ud.LISTENER, ud.PROCESS, "names: IPv4=%s" % (ip,))
		yield ip
	for ip in values.get('aAAARecord', []):
		ud.debug(ud.LISTENER, ud.PROCESS, "names: IPv6=%s" % (ip,))
		yield '%s' % (IPv6Address(ip),)


class AsRoot(object):
	"""
	Temporarily change effective UID to 'root'.
	"""

	def __enter__(self):
		listener.setuid(0)

	def __exit__(self, exc_type, exc_value, traceback):
		listener.unsetuid()

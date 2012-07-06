--
-- Univention Package Database
--  database table definitions
--
-2012- Copyright 2004-2012 Univention GmbH
--
-- http://www.univention.de/
--
-- All rights reserved.
--
-- The source code of this program is made available
-- under the terms of the GNU Affero General Public License version 3
-- (GNU AGPL V3) as published by the Free Software Foundation.
--
-- Binary versions of this program provided by Univention to you as
-- well as other copyrighted, protected or trademarked materials like
-- Logos, graphics, fonts, specific documentations and configurations,
-- cryptographic keys etc. are subject to a license agreement between
-- you and Univention and not subject to the GNU AGPL V3.
--
-- In the case you use this program under the terms of the GNU AGPL V3,
-- the program is provided in the hope that it will be useful,
-- but WITHOUT ANY WARRANTY; without even the implied warranty of
-- MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
-- GNU Affero General Public License for more details.
--
-- You should have received a copy of the GNU Affero General Public
-- License with the Debian GNU/Linux or Univention distribution in file
-- /usr/share/common-licenses/AGPL-3; if not, see
-- <http://www.gnu.org/licenses/>.

-- Definition of pgkdb

create group pkgdbg user pkgdbu;
grant all privileges on database pkgdb to pkgdbu;
grant all privileges on database pkgdb to group pkgdbg;

-- Table a) systems
create table systems (
  sysname         varchar(255) not null,
  sysversion      varchar(255) not null,
  sysrole         varchar(255) not null,
  ldaphostdn      varchar(255) not null,
  scandate        timestamp not null,
  updatedate      timestamp,
  updatemessage   text,
  upgradedate     timestamp,
  upgrademessage  text,
  installdate     timestamp,
  installmessage  text,
  removedate      timestamp,
  removemessage   text,
  primary key( sysname )
);

grant all privileges on table systems to pkgdbu;
grant all privileges on table systems to group pkgdbg;


-- Table b) packages
create table packages (
  pkgname         varchar(255) not null,
  vername         varchar(255) not null,
  inststatus      char not null,
  primary key( pkgname, vername )
);

grant all privileges on table packages to pkgdbu;
grant all privileges on table packages to group pkgdbg;


-- Table c) packages_on_systems
create table packages_on_systems (
  sysname         varchar(255) not null,
  pkgname         varchar(255) not null,
  vername         varchar(255) not null,
  scandate        timestamp not null,
  inststatus      char not null,
  selectedstate   smallint not null,
  inststate       smallint not null,
  currentstate    smallint not null,
  primary key( sysname, pkgname )
);

grant all privileges on table packages_on_systems to pkgdbu;
grant all privileges on table packages_on_systems to group pkgdbg;

-- to speed-up select
create index systems_sysname_index on systems (sysname);
create index systems_sysversion_index on systems (sysversion);
create index systems_sysrole_index on systems (sysrole);
create index packages_pkgname_index on packages (pkgname);
create index packages_vername_index on packages (vername);
create index packages_on_systems_vername_index on packages_on_systems (vername);
create index packages_on_systems_sysname_index on packages_on_systems (sysname);
create index packages_on_systems_pkgname_index on packages_on_systems (pkgname);
create index packages_on_systems_selectedstate_index on packages_on_systems (selectedstate);
create index packages_on_systems_inststate_index on packages_on_systems (inststate);
create index packages_on_systems_currentstate_index on packages_on_systems (currentstate);

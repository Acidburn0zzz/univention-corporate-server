/*
 * Univention Directory Listener
 *  header information for base64.c
 *
 * Copyright (C) 2004, 2005, 2006, 2007 Univention GmbH
 *
 * http://www.univention.de/
 *
 * All rights reserved.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation.
 *
 * Binary versions of this file provided by Univention to you as
 * well as other copyrighted, protected or trademarked materials like
 * Logos, graphics, fonts, specific documentations and configurations,
 * cryptographic keys etc. are subject to a license agreement between
 * you and Univention.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
 */

#ifndef _BASE64_H_
#define _BASE64_H_

#define BASE64_ENCODE_LEN(n)      (((n)+2)/3 * 4)
#define BASE64_DECODE_LEN(n)      (((n)+3)/4 * 3)

int	base64_encode	(u_char const	*src,
			 size_t		 srclength,
			 char		*target,
			 size_t		 targsize);
int	base64_decode	(char const	*src,
			 u_char		*target,
			 size_t		 targsize);

#endif /* _BASE64_H_ */

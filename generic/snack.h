/* 
 * Copyright (C) 1997-2005 Kare Sjolander <kare@speech.kth.se>
 *
 * This file is part of the Snack Sound Toolkit.
 * The latest version can be found at http://www.speech.kth.se/snack/
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
 */

#include "tcl.h"

#ifdef BUILD_snack
# undef TCL_STORAGE_CLASS
# define TCL_STORAGE_CLASS DLLEXPORT
#endif

/* Tcl 9 removed CONST; older Snack code still uses it in APIs like Tcl_Obj *CONST objv[] */
#ifndef CONST
#  define CONST const
#endif

#ifndef CONST84
#   define CONST84 const
#endif

/* Tcl_Size was introduced in Tcl/Tk 8.7; define it for older versions */
#ifndef Tcl_Size
#   define Tcl_Size int
#endif


#include "jkSound.h"
#include "jkAudIO.h"

#define SNACK_VERSION     "2.2"
#define SNACK_PATCH_LEVEL "2.2.10"

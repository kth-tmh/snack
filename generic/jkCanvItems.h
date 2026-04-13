/* 
 * Copyright (C) 1997-2002 Kare Sjolander <kare@speech.kth.se>
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

#ifdef __cplusplus
extern "C" {
#endif

/* Tk_Offset was removed in Tk 9; provide a compat definition using offsetof */
#ifndef Tk_Offset
#  include <stddef.h>
#  define Tk_Offset(type, field) ((int) offsetof(type, field))
#endif

#define NDEFCOLS 256
#define FRAMESIZE 262144

typedef struct SnackItemInfo {
  int    fftlen;
  int    winlen;
  float  spacing;
  float  *hamwin;
  float  preemph;
  int    BufPos;
  int    RestartPos;
  short  *frame[100];
  int    nfrms;
  int    frlen;
  float  **blocks;
  Pixmap pixmap;
  int    nfft;
  int    fftmax;
  int    fftmin;
  int    debug;
  int    samprate;
  int    encoding;
  int    nchannels;
  int    channel;
  int    channelSet;
  float  abmax;
  double bright;
  double contrast;
  double topfrequency;
  int    limit;
  double gridTspacing;
  int    gridFspacing;
  double pixpsec;
  int    ncolors;
  XColor **xcolor;
  int    subsample;
  XColor *gridcolor;
  int    depth;
  Visual *visual;
  Display *display;
  unsigned long *pixelmap;
  float  xUnderSamp;
  int xTot;
  int doneSpeg;
  char *fcname;
  int storeType;
  Sound *sound;
  int ssmp;
  int validStart;
  Tcl_Obj *cmdPtr;
  int computing;
  int skip;
  SnackWindowType windowType;
  SnackWindowType windowTypeSet;

} SnackItemInfo;

#define CONF_WIDTH 1
#define CONF_PPS 2
#define CONF_WIDTH_PPS 3

extern int  CheckFFTlen(Tcl_Interp *interp, int fftlen);

extern int  CheckWinlen(Tcl_Interp *interp, int winlen, int fftlen);

extern int  CheckLPCorder(Tcl_Interp *interp, int lpcorder);

#if !defined(WIN) && !defined(MAC) && !defined(MAC_OSX_TK)
#define TkPutImage(colors, ncolors, display, pixels, gc, image, \
		   destx, desty, srcx, srcy, width, height) \
        XPutImage(                  display, pixels, gc, image, \
		   destx, desty, srcx, srcy, width, height);
#endif

#if defined(WIN) || defined(MAC) || defined(MAC_OSX_TK)
#  ifndef XFree
#  define XFree(data) {if ((data) != NULL) ckfree((char *) (data));}
#  endif
#endif

#if defined MAC
#  include <tclMacMath.h>
#  define hypot hypotd

  extern double hypot(double x, double y);
#endif

/* TK_CONFIG_OPTION_SPECIFIED was removed in Tk 9; the bit value (0x4) is
 * preserved here so that specFlags-based tracking of which options were
 * explicitly set continues to work. */
#ifndef TK_CONFIG_OPTION_SPECIFIED
#   define TK_CONFIG_OPTION_SPECIFIED 0x4
#endif

#if TK_MAJOR_VERSION >= 9
#  define SNACK_CANVAS_CREATE_ARGS Tcl_Size objc, Tcl_Obj *const objv[]
#  define SNACK_CANVAS_COORD_ARGS Tcl_Size objc, Tcl_Obj *const objv[]
#  define SNACK_CANVAS_CONFIG_ARGS Tcl_Size objc, Tcl_Obj *const objv[], int flags
#  define SNACK_CANVAS_SET_ARGC(objc, argc) const Tcl_Size argc = objc
#  define SNACK_CANVAS_ARG(argv, objv, i) Tcl_GetString((objv)[i])
#  define SNACK_CANVAS_PREPARE_ARGV(argc, argv, objv) \
     do { \
       Tcl_Size snack_i; \
       (argv) = (const char **) ckalloc((unsigned) (argc) * sizeof(char *)); \
       for (snack_i = 0; snack_i < (argc); snack_i++) { \
         (argv)[snack_i] = Tcl_GetString((objv)[snack_i]); \
       } \
     } while (0)
#  define SNACK_CANVAS_FREE_ARGV(argv) ckfree((char *) (argv))
#else
#  define SNACK_CANVAS_CREATE_ARGS int argc, char **argv
#  define SNACK_CANVAS_COORD_ARGS int argc, char **argv
#  define SNACK_CANVAS_CONFIG_ARGS int argc, char **argv, int flags
#  define SNACK_CANVAS_SET_ARGC(objc, argc) ((void) 0)
#  define SNACK_CANVAS_ARG(argv, objv, i) (argv)[i]
#  define SNACK_CANVAS_PREPARE_ARGV(argc, argv, objv) ((void) 0)
#  define SNACK_CANVAS_FREE_ARGV(argv) ((void) 0)
#endif

#define OptSpecified(option) (configSpecs[option].specFlags & TK_CONFIG_OPTION_SPECIFIED)

#ifdef __cplusplus
}
#endif

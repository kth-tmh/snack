/*
 * Copyright (C) 2000-2002 Kare Sjolander <kare@speech.kth.se>
 *
 * This file is part of the Snack Sound Toolkit.
 * The latest version can be found at http://www.speech.kth.se/snack/
 *
 * The original bundled MP3 decoder had non-open distribution terms.
 * This implementation uses the upstream minimp3 decoder instead:
 * https://github.com/lieff/minimp3
 */

#include <string.h>

#include "snack.h"

#define MINIMP3_ONLY_MP3
#define MINIMP3_IMPLEMENTATION
#include "jkFormatMP3.h"

extern int useOldObjAPI;
extern struct Snack_FileFormat *snackFileFormats;

#define SNACK_MP3_INT 18

static void
CloseDecoder(mp3Info *si)
{
  if (si != NULL && si->decoderOpen) {
    mp3dec_ex_close(&si->dec);
    si->decoderOpen = 0;
  }
}

static int
OpenDecoderFromFile(mp3Info *si, const char *filename)
{
  CloseDecoder(si);
  if (mp3dec_ex_open(&si->dec, filename, MP3D_SEEK_TO_SAMPLE) != 0) {
    return TCL_ERROR;
  }
  si->decoderOpen = 1;
  return TCL_OK;
}

static int
OpenDecoderFromObject(mp3Info *si, Tcl_Obj *obj)
{
  const unsigned char *bytes = NULL;
  int length = 0;

  CloseDecoder(si);
  if (useOldObjAPI) {
    bytes = (const unsigned char *) obj->bytes;
    length = obj->length;
  } else {
#ifdef TCL_81_API
    bytes = Tcl_GetByteArrayFromObj(obj, &length);
#endif
  }
  if (bytes == NULL || length <= 0) {
    return TCL_ERROR;
  }
  if (mp3dec_ex_open_buf(&si->dec, bytes, (size_t) length,
                         MP3D_SEEK_TO_SAMPLE) != 0) {
    return TCL_ERROR;
  }
  si->decoderOpen = 1;
  return TCL_OK;
}

static mp3Info *
GetOrCreateMp3Info(Sound *s)
{
  mp3Info *si = (mp3Info *) s->extHead;

  if (si == NULL) {
    si = (mp3Info *) ckalloc(sizeof(mp3Info));
    memset(si, 0, sizeof(mp3Info));
    s->extHead = (char *) si;
    s->extHeadType = SNACK_MP3_INT;
  }
  return si;
}

char *
GuessMP3File(char *buf, int len)
{
  if (len < 4) {
    return QUE_STRING;
  }
  if (strncmp("ID3", buf, 3) == 0) {
    return MP3_STRING;
  }
  if (strncasecmp("RIFF", buf, 4) == 0 && len > 21 && ((unsigned char) buf[20]) == 0x55) {
    return MP3_STRING;
  }
  if (mp3dec_detect_buf((const uint8_t *) buf, (size_t) len) == 0) {
    return MP3_STRING;
  }
  return NULL;
}

int
GetMP3Header(Sound *s, Tcl_Interp *interp, Tcl_Channel ch, Tcl_Obj *obj, char *buf)
{
  mp3Info *si;
  int status;

  (void) ch;
  (void) buf;

  if (s->extHead != NULL && s->extHeadType != SNACK_MP3_INT) {
    Snack_FileFormat *ff;

    for (ff = snackFileFormats; ff != NULL; ff = ff->nextPtr) {
      if (strcmp(s->fileType, ff->name) == 0 && ff->freeHeaderProc != NULL) {
        (ff->freeHeaderProc)(s);
      }
    }
  }

  si = GetOrCreateMp3Info(s);
  status = (obj == NULL) ? OpenDecoderFromFile(si, s->fcname)
                         : OpenDecoderFromObject(si, obj);
  if (status != TCL_OK) {
    Tcl_AppendResult(interp, "Could not open MP3 stream", NULL);
    return TCL_ERROR;
  }
  if (si->dec.info.channels <= 0 || si->dec.info.hz <= 0) {
    Tcl_AppendResult(interp, "Could not find MP3 header", NULL);
    CloseDecoder(si);
    return TCL_ERROR;
  }

  si->bitrate = si->dec.info.bitrate_kbps * 1000;
  si->nchannels = si->dec.info.channels;

  s->nchannels = si->dec.info.channels;
  s->samprate = si->dec.info.hz;
  s->encoding = LIN16;
  s->sampsize = 2;
  s->length = (int) (si->dec.samples / si->dec.info.channels);
  s->headSize = 0;
  s->swap = 0;
  s->extHeadType = SNACK_MP3_INT;

  return TCL_OK;
}

int
SeekMP3File(Sound *s, Tcl_Interp *interp, Tcl_Channel ch, int pos)
{
  mp3Info *si = (mp3Info *) s->extHead;

  (void) interp;
  (void) ch;

  if (si == NULL || !si->decoderOpen) {
    return -1;
  }
  if (mp3dec_ex_seek(&si->dec, (uint64_t) pos * (uint64_t) si->nchannels) != 0) {
    return -1;
  }
  return pos;
}

int
ReadMP3Samples(Sound *s, Tcl_Interp *interp, Tcl_Channel ch, char *ibuf, float *obuf, int len)
{
  mp3Info *si = (mp3Info *) s->extHead;
  int total = 0;
  mp3d_sample_t pcm[MINIMP3_MAX_SAMPLES_PER_FRAME];

  (void) interp;
  (void) ch;
  (void) ibuf;

  if (si == NULL || !si->decoderOpen) {
    return 0;
  }

  while (total < len) {
    size_t want = (size_t) (len - total);
    size_t got;
    int i;

    if (want > MINIMP3_MAX_SAMPLES_PER_FRAME) {
      want = MINIMP3_MAX_SAMPLES_PER_FRAME;
    }
    got = mp3dec_ex_read(&si->dec, pcm, want);
    if (got == 0) {
      break;
    }
    for (i = 0; i < (int) got; i++) {
      obuf[total + i] = (float) pcm[i];
    }
    total += (int) got;
  }

  return total;
}

char *
ExtMP3File(char *s)
{
  int l1 = (int) strlen(".mp3");
  int l2 = (int) strlen(s);

  if (l2 >= l1 && strncasecmp(".mp3", &s[l2 - l1], l1) == 0) {
    return MP3_STRING;
  }
  return NULL;
}

int
OpenMP3File(Sound *s, Tcl_Interp *interp, Tcl_Channel *ch, char *mode)
{
  mp3Info *si = GetOrCreateMp3Info(s);

  if (strcmp(mode, "r") != 0) {
    Tcl_AppendResult(interp, "Unsupported MP3 open mode", NULL);
    return TCL_ERROR;
  }
  if ((*ch = Tcl_OpenFileChannel(interp, s->fcname, mode, 0)) == NULL) {
    return TCL_ERROR;
  }
  Tcl_SetChannelOption(interp, *ch, "-translation", "binary");
#ifdef TCL_81_API
  Tcl_SetChannelOption(interp, *ch, "-encoding", "binary");
#endif

  if (OpenDecoderFromFile(si, s->fcname) != TCL_OK) {
    Tcl_Close(interp, *ch);
    *ch = NULL;
    Tcl_AppendResult(interp, "Could not open MP3 stream", NULL);
    return TCL_ERROR;
  }

  return TCL_OK;
}

int
CloseMP3File(Sound *s, Tcl_Interp *interp, Tcl_Channel *ch)
{
  mp3Info *si = (mp3Info *) s->extHead;

  CloseDecoder(si);
  Tcl_Close(interp, *ch);
  *ch = NULL;
  return TCL_OK;
}

void
FreeMP3Header(Sound *s)
{
  mp3Info *si = (mp3Info *) s->extHead;

  if (si != NULL) {
    CloseDecoder(si);
    ckfree((char *) si);
    s->extHead = NULL;
    s->extHeadType = 0;
  }
}

int
ConfigMP3Header(Sound *s, Tcl_Interp *interp, int objc, Tcl_Obj *CONST objv[])
{
  mp3Info *si = (mp3Info *) s->extHead;
  int arg;
  int index;
  static CONST84 char *optionStrings[] = {
    "-bitrate", NULL
  };
  enum options {
    BITRATE
  };

  if (si == NULL || objc < 3) {
    return 0;
  }

  if (objc == 3) {
    if (Tcl_GetIndexFromObj(interp, objv[2], optionStrings, "option", 0,
                            &index) != TCL_OK) {
      Tcl_AppendResult(interp, ", or\n", NULL);
      return 0;
    }
    if ((enum options) index == BITRATE) {
      Tcl_SetObjResult(interp, Tcl_NewIntObj(si->bitrate));
    }
    return 1;
  }

  for (arg = 2; arg < objc; arg += 2) {
    if (Tcl_GetIndexFromObj(interp, objv[arg], optionStrings, "option", 0,
                            &index) != TCL_OK) {
      return TCL_ERROR;
    }
    if (arg + 1 == objc) {
      Tcl_AppendResult(interp, "No argument given for ",
                       optionStrings[index], " option\n", (char *) NULL);
      return 0;
    }
    if ((enum options) index == BITRATE) {
      /* Read-only metadata for MP3 input. */
    }
  }

  return 1;
}

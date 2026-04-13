/*
 * Copyright (C) 2000-2002 Kare Sjolander <kare@speech.kth.se>
 *
 * This file is part of the Snack Sound Toolkit.
 * The latest version can be found at http://www.speech.kth.se/snack/
 */

#ifndef JK_FORMAT_MP3_H
#define JK_FORMAT_MP3_H

#include "minimp3_ex.h"

typedef struct mp3Info {
  mp3dec_ex_t dec;
  int decoderOpen;
  int bitrate;
  int nchannels;
} mp3Info;

#endif

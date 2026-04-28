/*
 * snack_core/snack_iir.c --
 *
 *   Standalone IIR filter kernel for the Snack DSP core.
 *
 *   No Tcl, Tk, or interpreter dependency.  Uses only ISO C99 and the
 *   standard library (<stdlib.h>, <string.h>, <math.h>).
 *
 * Design notes
 * ------------
 * Implements Direct Form I using backward-reading ring-buffers for both
 * the input (feedforward) and output (feedback) delay lines.
 *
 * Ring-buffer invariant (both x_hist and y_hist):
 *   history[pos * channels + ch]  == most recent sample for channel ch
 *   history[(pos-1+n) * channels + ch]  == second most recent
 *   ...
 *
 * The difference equation evaluated per frame i, channel c is:
 *
 *   a[0] * y[i] = sum_{j=0}^{n_b-1} b[j] * x[i-j]
 *               - sum_{j=1}^{n_a-1} a[j] * y[i-j]
 *
 * RNG
 * ---
 * A 32-bit xorshift generator is stored inline in SnackIIRState.
 * It is never 0 (initialised to 1 and a seed of 0 maps to 1).
 * All stochastic behaviour is opt-in; default noise_scale and
 * dither_scale are 0.0.
 *
 * Copyright (c) 2000 MusicMatch, Inc. / 2024 Snack contributors.
 * See snack_iir.h for full license text.
 */

#include "snack_iir.h"

#include <stdlib.h>
#include <string.h>
#include <math.h>

/* -----------------------------------------------------------------------
 * Internal RNG helpers (xorshift32)
 * ----------------------------------------------------------------------- */

/* Advance xorshift32 state and return the new value. */
static uint32_t
xorshift32_next(uint32_t *state)
{
    uint32_t x = *state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *state = x;
    return x;
}

/* Uniform deviate in [0, 1). */
static double
rng_uniform(uint32_t *state)
{
    return (double)xorshift32_next(state) / (double)0xFFFFFFFFu;
}

/*
 * Gaussian deviate with mean 0, variance 1, via the 12-uniform-sum
 * method.  Uses 12 RNG draws.  Accuracy is comparable to Box-Muller
 * for audio-rate dithering purposes and avoids transcendental functions.
 */
static double
rng_normal(uint32_t *state)
{
    double s = 0.0;
    int i;
    for (i = 0; i < 6; i++) {
        s += rng_uniform(state);
        s -= rng_uniform(state);
    }
    return s;
}

/* Triangular deviate in (-1, 1): difference of two uniform draws. */
static double
rng_triangular(uint32_t *state)
{
    return rng_uniform(state) - rng_uniform(state);
}

/* -----------------------------------------------------------------------
 * Public API
 * ----------------------------------------------------------------------- */

int
snack_iir_init(SnackIIRState *st,
               int            n_b,
               const double  *b,
               int            n_a,
               const double  *a,
               int            channels)
{
    if (!st || n_b < 1 || !b || n_a < 1 || !a || channels < 1)
        return -1;
    if (a[0] == 0.0)
        return -1;

    memset(st, 0, sizeof(*st));
    st->n_b      = n_b;
    st->n_a      = n_a;
    st->channels = channels;
    st->rng      = 1u; /* xorshift32 must not be 0 */

    /* Copy coefficient arrays. */
    st->b = (double *)malloc((size_t)n_b * sizeof(double));
    if (!st->b)
        return -1;
    memcpy(st->b, b, (size_t)n_b * sizeof(double));

    st->a = (double *)malloc((size_t)n_a * sizeof(double));
    if (!st->a) {
        free(st->b);
        st->b = NULL;
        return -1;
    }
    memcpy(st->a, a, (size_t)n_a * sizeof(double));

    /* Allocate zero-initialised history buffers. */
    st->x_hist = (double *)calloc((size_t)(n_b * channels), sizeof(double));
    if (!st->x_hist) {
        free(st->b);
        free(st->a);
        st->b = st->a = NULL;
        return -1;
    }

    st->y_hist = (double *)calloc((size_t)(n_a * channels), sizeof(double));
    if (!st->y_hist) {
        free(st->b);
        free(st->a);
        free(st->x_hist);
        st->b = st->a = st->x_hist = NULL;
        return -1;
    }

    /* Ring-buffer positions: pos=0 after init, y_hist[0] acts as y[-1]=0. */
    st->x_pos = 0;
    st->y_pos = 0;

    return 0;
}

void
snack_iir_seed(SnackIIRState *st, uint32_t seed)
{
    if (!st) return;
    st->rng = seed ? seed : 1u;
}

void
snack_iir_reset(SnackIIRState *st)
{
    if (!st) return;
    if (st->x_hist)
        memset(st->x_hist, 0, (size_t)(st->n_b * st->channels) * sizeof(double));
    if (st->y_hist)
        memset(st->y_hist, 0, (size_t)(st->n_a * st->channels) * sizeof(double));
    st->x_pos = 0;
    st->y_pos = 0;
}

int
snack_iir_process_f32(SnackIIRState *st,
                      const float   *in,
                      float         *out,
                      int            n_frames,
                      double         noise_scale,
                      double         dither_scale)
{
    int ch, i, j, k;
    double outsmp;

    if (!st || !in || !out || n_frames < 0)
        return -1;
    if (!st->b || !st->a || !st->x_hist || !st->y_hist)
        return -1;

    /*
     * Outer loop: channels.
     * Ring-buffer positions are reset to the same starting point for each
     * channel because the interleaved layout shares the ring index across
     * channels: x_hist[pos * channels + ch].  Every channel executes the
     * same number of frames, so they all advance the ring by the same amount.
     */
    for (ch = 0; ch < st->channels; ch++) {
        int xp = st->x_pos;
        int yp = st->y_pos;

        for (i = 0; i < n_frames; i++) {
            /*
             * 1. Store current input sample in the feedforward delay line.
             *    The write position is advanced BEFORE writing so that
             *    x_hist[xp * channels + ch] always holds the most recent
             *    sample after the write.
             */
            xp = (xp + 1) % st->n_b;
            st->x_hist[xp * st->channels + ch] = (double)in[i * st->channels + ch];

            /*
             * 2. Feedforward sum:  sum_{j=0}^{n_b-1} b[j] * x[i-j]
             *    Read backward from xp: xp = x[i], xp-1 = x[i-1], …
             */
            outsmp = 0.0;
            k = xp;
            for (j = 0; j < st->n_b; j++) {
                outsmp += st->b[j] * st->x_hist[k * st->channels + ch];
                k = (k - 1 + st->n_b) % st->n_b;
            }

            /*
             * 3. Feedback sum:  - sum_{j=1}^{n_a-1} a[j] * y[i-j]
             *    Read backward from yp: yp = y[i-1], yp-1 = y[i-2], …
             *    (yp still points to the most recent *stored* output.)
             */
            k = yp;
            for (j = 1; j < st->n_a; j++) {
                outsmp -= st->a[j] * st->y_hist[k * st->channels + ch];
                k = (k - 1 + st->n_a) % st->n_a;
            }
            outsmp /= st->a[0];

            /*
             * 4. Store current output in the feedback delay line.
             *    Advance yp AFTER computing outsmp so it becomes the
             *    "most recent" entry for the next frame.
             */
            yp = (yp + 1) % st->n_a;
            st->y_hist[yp * st->channels + ch] = outsmp;

            /*
             * 5. Stochastic additions (opt-in; both 0 by default).
             */
            if (noise_scale != 0.0)
                outsmp += noise_scale * rng_normal(&st->rng);
            if (dither_scale != 0.0)
                outsmp += dither_scale * rng_triangular(&st->rng);

            out[i * st->channels + ch] = (float)outsmp;
        }

        /*
         * Save final ring-buffer positions back to state.
         * Because every channel processes the same n_frames, the final
         * xp and yp are identical for all channels, so writing from the
         * last iteration is correct.
         */
        st->x_pos = xp;
        st->y_pos = yp;
    }

    return 0;
}

void
snack_iir_free(SnackIIRState *st)
{
    if (!st) return;
    free(st->b);      st->b      = NULL;
    free(st->a);      st->a      = NULL;
    free(st->x_hist); st->x_hist = NULL;
    free(st->y_hist); st->y_hist = NULL;
}

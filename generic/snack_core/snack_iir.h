/*
 * snack_core/snack_iir.h --
 *
 *   Standalone IIR filter kernel for the Snack DSP core.
 *
 *   This header has NO dependency on Tcl, Tk, or any interpreter.
 *   It may be compiled and linked independently of the Snack Tcl/Tk
 *   extension.
 *
 * Copyright (c) 2000 MusicMatch, Inc. / 2024 Snack contributors.
 *
 * The authors hereby grant permission to use, copy, modify, distribute,
 * and license this software and its documentation for any purpose, provided
 * that existing copyright notices are retained in all copies and that this
 * notice is included verbatim in any distributions. No written agreement,
 * license, or royalty fee is required for any of the authorized uses.
 * Modifications to this software may be copyrighted by their authors
 * and need not follow the licensing terms described here, provided that
 * the new terms are clearly indicated on the first page of each file where
 * they apply.
 *
 * IN NO EVENT SHALL THE AUTHORS OR DISTRIBUTORS BE LIABLE TO ANY PARTY
 * FOR DIRECT, INDIRECT, SPECIAL, INCIDENTAL, OR CONSEQUENTIAL DAMAGES
 * ARISING OUT OF THE USE OF THIS SOFTWARE, ITS DOCUMENTATION, OR ANY
 * DERIVATIVES THEREOF, EVEN IF THE AUTHORS HAVE BEEN ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 *
 * THE AUTHORS AND DISTRIBUTORS SPECIFICALLY DISCLAIM ANY WARRANTIES,
 * INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT.  THIS SOFTWARE
 * IS PROVIDED ON AN "AS IS" BASIS, AND THE AUTHORS AND DISTRIBUTORS HAVE
 * NO OBLIGATION TO PROVIDE MAINTENANCE, SUPPORT, UPDATES, ENHANCEMENTS, OR
 * MODIFICATIONS.
 */

#ifndef SNACK_IIR_H
#define SNACK_IIR_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * SnackIIRState — all state for one IIR filter instance.
 *
 * Implements the standard Direct Form I difference equation:
 *
 *   a[0]*y[n] = b[0]*x[n] + b[1]*x[n-1] + ... + b[n_b-1]*x[n-n_b+1]
 *             - a[1]*y[n-1] - a[2]*y[n-2] - ... - a[n_a-1]*y[n-n_a+1]
 *
 * History buffers are ring-buffers using backward indexing so that
 * position [pos] is always the most recent sample, [pos-1] the second
 * most recent, etc.
 *
 * All buffers are owned by this struct (allocated by snack_iir_init,
 * freed by snack_iir_free).  No global state is used; multiple instances
 * may coexist safely in the same process.
 */
typedef struct {
    int      n_b;       /* number of numerator (feedforward) taps, >= 1    */
    int      n_a;       /* number of denominator (feedback) taps, >= 1     */
    int      channels;  /* number of interleaved audio channels, >= 1      */
    double  *b;         /* numerator coefficients [n_b], owned             */
    double  *a;         /* denominator coefficients [n_a], owned; a[0]!=0  */
    double  *x_hist;    /* input history [n_b * channels], ring-buffer     */
    double  *y_hist;    /* output history [n_a * channels], ring-buffer    */
    int      x_pos;     /* ring-buffer write position (most recent input)  */
    int      y_pos;     /* ring-buffer write position (most recent output) */
    uint32_t rng;       /* explicit xorshift32 RNG state (never 0)         */
} SnackIIRState;

/*
 * snack_iir_init — initialise an IIR filter state.
 *
 * Copies b and a into internal buffers owned by *st.
 * Allocates zero-initialised history for each channel.
 *
 * Parameters:
 *   st       — output state to initialise (must not be NULL).
 *   n_b      — number of numerator taps (>= 1).
 *   b        — numerator coefficients (copied; must not be NULL).
 *   n_a      — number of denominator taps (>= 1).
 *   a        — denominator coefficients (copied; must not be NULL;
 *               a[0] must be non-zero).
 *   channels — number of interleaved audio channels (>= 1).
 *
 * Returns 0 on success, -1 on invalid arguments or allocation failure.
 */
int snack_iir_init(SnackIIRState *st,
                   int            n_b,
                   const double  *b,
                   int            n_a,
                   const double  *a,
                   int            channels);

/*
 * snack_iir_seed — set the RNG seed for reproducible stochastic noise.
 *
 * A seed of 0 is silently replaced with 1 (xorshift32 must not have
 * state 0).  Call before snack_iir_process_f32 when noise_scale or
 * dither_scale are non-zero.  The default after snack_iir_init is 1.
 */
void snack_iir_seed(SnackIIRState *st, uint32_t seed);

/*
 * snack_iir_reset — zero all history buffers without freeing memory.
 *
 * Restores the filter to its just-initialised state without reallocation.
 */
void snack_iir_reset(SnackIIRState *st);

/*
 * snack_iir_process_f32 — filter a block of interleaved float32 samples.
 *
 * Samples in `in` and `out` are interleaved across channels:
 *   [ch0_frame0, ch1_frame0, ..., ch0_frame1, ch1_frame1, ...]
 *
 * `in` and `out` may point to the same buffer (in-place processing).
 *
 * Stochastic additions (noise, dither) use the internal RNG state so
 * that results are fully reproducible given the same seed.  Pass 0.0
 * for both to get deterministic output (the default in modern mode).
 *
 * Parameters:
 *   st           — initialised filter state.
 *   in           — input samples (n_frames * channels floats).
 *   out          — output buffer (n_frames * channels floats).
 *   n_frames     — number of frames to process (>= 0).
 *   noise_scale  — amplitude of additive Gaussian noise.  0.0 = none.
 *   dither_scale — amplitude of triangular dither added to output.  0.0 = none.
 *
 * Returns 0 on success, -1 on NULL argument.
 */
int snack_iir_process_f32(SnackIIRState *st,
                          const float   *in,
                          float         *out,
                          int            n_frames,
                          double         noise_scale,
                          double         dither_scale);

/*
 * snack_iir_free — release all memory owned by the state.
 *
 * The struct itself is not freed; the caller manages it.
 * After this call the struct may be re-used by snack_iir_init.
 */
void snack_iir_free(SnackIIRState *st);

#ifdef __cplusplus
}
#endif

#endif /* SNACK_IIR_H */

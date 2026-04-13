/*
 * _snack.c - Python C extension for the Snack Sound Toolkit
 *
 * Provides a direct Python API over the Snack C library.  No Tcl or Tk
 * APIs are exposed to Python callers; an embedded Tcl interpreter is
 * used internally for resource management and complex operations.
 *
 * The Sound_Init() entry point (from generic/sound.c) initialises Snack
 * without Tk, so this extension has no GUI dependency.
 *
 * Copyright (C) 1997-2005 Kare Sjolander
 * Python bindings copyright (C) 2024 contributors
 * GPL v2 – see LICENSE.txt
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "tcl.h"
#include "snack.h"

/* Single embedded Tcl interpreter, initialised once at module load. */
static Tcl_Interp *g_interp = NULL;
static int g_sound_counter  = 0;

/* -----------------------------------------------------------------------
 * Helpers
 * ----------------------------------------------------------------------- */

/* Convert the current Tcl result into a Python exception and return NULL. */
static PyObject *
raise_tcl_error(const char *prefix)
{
    const char *msg = g_interp ? Tcl_GetStringResult(g_interp) : "(no interp)";
    if (prefix)
        PyErr_Format(PyExc_RuntimeError, "%s: %s", prefix, msg);
    else
        PyErr_SetString(PyExc_RuntimeError, msg);
    return NULL;
}

/* Convert a Tcl list result into a Python list of floats. */
static PyObject *
tcl_list_to_pylist_doubles(Tcl_Obj *obj)
{
    int n;
    Tcl_Obj **elems;
    if (Tcl_ListObjGetElements(g_interp, obj, &n, &elems) != TCL_OK)
        return raise_tcl_error("ListObjGetElements");

    PyObject *list = PyList_New(n);
    if (!list) return NULL;

    for (int i = 0; i < n; i++) {
        double v;
        Tcl_GetDoubleFromObj(g_interp, elems[i], &v);
        PyList_SET_ITEM(list, i, PyFloat_FromDouble(v));
    }
    return list;
}

/* -----------------------------------------------------------------------
 * Sound Python type
 * ----------------------------------------------------------------------- */

typedef struct {
    PyObject_HEAD
    Sound *snd;
    char   name[32];
} PySoundObject;

static void
PySound_dealloc(PySoundObject *self)
{
    if (self->snd && g_interp) {
        char cmd[64];
        snprintf(cmd, sizeof(cmd), "%s destroy", self->name);
        Tcl_Eval(g_interp, cmd);
        self->snd = NULL;
    }
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *
PySound_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    int         rate     = 16000;
    int         channels = 1;
    const char *encoding = "Lin16";

    static char *kwlist[] = {"sample_rate", "channels", "encoding", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "|iis", kwlist,
                                     &rate, &channels, &encoding))
        return NULL;

    PySoundObject *self = (PySoundObject *)type->tp_alloc(type, 0);
    if (!self) return NULL;

    snprintf(self->name, sizeof(self->name), "_pysnd%d", ++g_sound_counter);

    char cmd[256];
    snprintf(cmd, sizeof(cmd),
             "sound %s -rate %d -channels %d -encoding %s",
             self->name, rate, channels, encoding);

    if (Tcl_Eval(g_interp, cmd) != TCL_OK) {
        Py_DECREF(self);
        return raise_tcl_error("Sound creation");
    }

    self->snd = Snack_GetSound(g_interp, self->name);
    if (!self->snd) {
        char destroy[64];
        snprintf(destroy, sizeof(destroy), "%s destroy", self->name);
        Tcl_Eval(g_interp, destroy);
        Py_DECREF(self);
        PyErr_SetString(PyExc_RuntimeError, "Failed to retrieve sound object");
        return NULL;
    }

    return (PyObject *)self;
}

/* read(filename, start=0, end=-1) */
static PyObject *
PySound_read(PySoundObject *self, PyObject *args, PyObject *kwds)
{
    const char *filename;
    int         start = 0, end = -1;
    static char *kwlist[] = {"filename", "start", "end", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "s|ii", kwlist,
                                     &filename, &start, &end))
        return NULL;

    char cmd[2048];
    if (end >= 0)
        snprintf(cmd, sizeof(cmd),
                 "%s read {%s} -start %d -end %d", self->name, filename, start, end);
    else
        snprintf(cmd, sizeof(cmd), "%s read {%s}", self->name, filename);

    if (Tcl_Eval(g_interp, cmd) != TCL_OK)
        return raise_tcl_error("Sound.read");
    Py_RETURN_NONE;
}

/* write(filename, format=None, start=0, end=-1) */
static PyObject *
PySound_write(PySoundObject *self, PyObject *args, PyObject *kwds)
{
    const char *filename;
    const char *fmt   = NULL;
    int         start = 0, end = -1;
    static char *kwlist[] = {"filename", "format", "start", "end", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "s|sii", kwlist,
                                     &filename, &fmt, &start, &end))
        return NULL;

    char cmd[2048];
    int  off = snprintf(cmd, sizeof(cmd), "%s write {%s}", self->name, filename);
    if (fmt)
        off += snprintf(cmd + off, sizeof(cmd) - (size_t)off,
                        " -fileformat %s", fmt);
    if (end >= 0)
        snprintf(cmd + off, sizeof(cmd) - (size_t)off,
                 " -start %d -end %d", start, end);

    if (Tcl_Eval(g_interp, cmd) != TCL_OK)
        return raise_tcl_error("Sound.write");
    Py_RETURN_NONE;
}

/* play(blocking=True) */
static PyObject *
PySound_play(PySoundObject *self, PyObject *args, PyObject *kwds)
{
    int blocking = 1;
    static char *kwlist[] = {"blocking", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "|p", kwlist, &blocking))
        return NULL;

    char cmd[64];
    snprintf(cmd, sizeof(cmd), "%s play%s",
             self->name, blocking ? " -block 1" : "");

    if (Tcl_Eval(g_interp, cmd) != TCL_OK)
        return raise_tcl_error("Sound.play");
    Py_RETURN_NONE;
}

/* record() */
static PyObject *
PySound_record(PySoundObject *self, PyObject *args)
{
    char cmd[64];
    snprintf(cmd, sizeof(cmd), "%s record", self->name);
    if (Tcl_Eval(g_interp, cmd) != TCL_OK)
        return raise_tcl_error("Sound.record");
    Py_RETURN_NONE;
}

/* stop() */
static PyObject *
PySound_stop(PySoundObject *self, PyObject *Py_UNUSED(ignored))
{
    char cmd[64];
    snprintf(cmd, sizeof(cmd), "%s stop", self->name);
    Tcl_Eval(g_interp, cmd);
    Py_RETURN_NONE;
}

/* pause() */
static PyObject *
PySound_pause(PySoundObject *self, PyObject *Py_UNUSED(ignored))
{
    char cmd[64];
    snprintf(cmd, sizeof(cmd), "%s pause", self->name);
    Tcl_Eval(g_interp, cmd);
    Py_RETURN_NONE;
}

/* crop(start, end) */
static PyObject *
PySound_crop(PySoundObject *self, PyObject *args)
{
    int start, end;
    if (!PyArg_ParseTuple(args, "ii", &start, &end)) return NULL;
    char cmd[128];
    snprintf(cmd, sizeof(cmd), "%s crop %d %d", self->name, start, end);
    if (Tcl_Eval(g_interp, cmd) != TCL_OK)
        return raise_tcl_error("Sound.crop");
    Py_RETURN_NONE;
}

/* reverse() */
static PyObject *
PySound_reverse(PySoundObject *self, PyObject *Py_UNUSED(ignored))
{
    char cmd[64];
    snprintf(cmd, sizeof(cmd), "%s reverse", self->name);
    if (Tcl_Eval(g_interp, cmd) != TCL_OK)
        return raise_tcl_error("Sound.reverse");
    Py_RETURN_NONE;
}

/* get_sample(channel, index) -> float */
static PyObject *
PySound_get_sample(PySoundObject *self, PyObject *args)
{
    int channel, index;
    if (!PyArg_ParseTuple(args, "ii", &channel, &index)) return NULL;

    int nlen  = Snack_GetLength(self->snd);
    int nchan = Snack_GetNumChannels(self->snd);
    if (index < 0 || index >= nlen) {
        PyErr_SetString(PyExc_IndexError, "sample index out of range");
        return NULL;
    }
    if (channel < 0 || channel >= nchan) {
        PyErr_SetString(PyExc_IndexError, "channel index out of range");
        return NULL;
    }
    return PyFloat_FromDouble(Snack_GetSample(self->snd, channel, index));
}

/* get_samples() -> flat list [ch0s0, ch1s0, ch0s1, ...] */
static PyObject *
PySound_get_samples(PySoundObject *self, PyObject *Py_UNUSED(ignored))
{
    int nframes = Snack_GetLength(self->snd);
    int nchan   = Snack_GetNumChannels(self->snd);

    PyObject *list = PyList_New((Py_ssize_t)nframes * nchan);
    if (!list) return NULL;

    for (int i = 0; i < nframes; i++) {
        for (int c = 0; c < nchan; c++) {
            PyObject *v = PyFloat_FromDouble(Snack_GetSample(self->snd, c, i));
            if (!v) { Py_DECREF(list); return NULL; }
            PyList_SET_ITEM(list, (Py_ssize_t)i * nchan + c, v);
        }
    }
    return list;
}

/* pitch(**kwargs) -> list of floats */
static PyObject *
PySound_pitch(PySoundObject *self, PyObject *args, PyObject *kwds)
{
    char cmd[512];
    int  off = snprintf(cmd, sizeof(cmd), "%s pitch", self->name);

    /* Forward any keyword arguments as Tcl options */
    if (kwds) {
        PyObject *key, *value;
        Py_ssize_t pos = 0;
        while (PyDict_Next(kwds, &pos, &key, &value)) {
            const char *k = PyUnicode_AsUTF8(key);
            PyObject *vs = PyObject_Str(value);
            if (!vs) return NULL;
            off += snprintf(cmd + off, sizeof(cmd) - (size_t)off,
                            " -%s %s", k, PyUnicode_AsUTF8(vs));
            Py_DECREF(vs);
        }
    }

    if (Tcl_Eval(g_interp, cmd) != TCL_OK)
        return raise_tcl_error("Sound.pitch");
    return tcl_list_to_pylist_doubles(Tcl_GetObjResult(g_interp));
}

/* formant(**kwargs) -> list of floats */
static PyObject *
PySound_formant(PySoundObject *self, PyObject *args, PyObject *kwds)
{
    char cmd[512];
    int  off = snprintf(cmd, sizeof(cmd), "%s formant", self->name);

    if (kwds) {
        PyObject *key, *value;
        Py_ssize_t pos = 0;
        while (PyDict_Next(kwds, &pos, &key, &value)) {
            const char *k = PyUnicode_AsUTF8(key);
            PyObject *vs = PyObject_Str(value);
            if (!vs) return NULL;
            off += snprintf(cmd + off, sizeof(cmd) - (size_t)off,
                            " -%s %s", k, PyUnicode_AsUTF8(vs));
            Py_DECREF(vs);
        }
    }

    if (Tcl_Eval(g_interp, cmd) != TCL_OK)
        return raise_tcl_error("Sound.formant");
    return tcl_list_to_pylist_doubles(Tcl_GetObjResult(g_interp));
}

/* power_spectrum(fft_length=512, start=0, end=-1) -> list of dB floats */
static PyObject *
PySound_power_spectrum(PySoundObject *self, PyObject *args, PyObject *kwds)
{
    int fft_length = 512, start = 0, end = -1;
    static char *kwlist[] = {"fft_length", "start", "end", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "|iii", kwlist,
                                     &fft_length, &start, &end))
        return NULL;

    char cmd[256];
    int  off = snprintf(cmd, sizeof(cmd),
                        "%s dBPowerSpectrum -fftlength %d -start %d",
                        self->name, fft_length, start);
    if (end >= 0)
        snprintf(cmd + off, sizeof(cmd) - (size_t)off, " -end %d", end);

    if (Tcl_Eval(g_interp, cmd) != TCL_OK)
        return raise_tcl_error("Sound.power_spectrum");
    return tcl_list_to_pylist_doubles(Tcl_GetObjResult(g_interp));
}

/* Properties */
static PyObject *
PySound_get_length(PySoundObject *self, void *Py_UNUSED(closure))
{
    return PyLong_FromLong(Snack_GetLength(self->snd));
}

static PyObject *
PySound_get_sample_rate(PySoundObject *self, void *Py_UNUSED(closure))
{
    return PyLong_FromLong(Snack_GetSampleRate(self->snd));
}

static PyObject *
PySound_get_channels(PySoundObject *self, void *Py_UNUSED(closure))
{
    return PyLong_FromLong(Snack_GetNumChannels(self->snd));
}

static PyObject *
PySound_get_encoding(PySoundObject *self, void *Py_UNUSED(closure))
{
    return PyLong_FromLong(Snack_GetSampleEncoding(self->snd));
}

static PyObject *
PySound_repr(PySoundObject *self)
{
    return PyUnicode_FromFormat(
        "Sound(sample_rate=%d, channels=%d, length=%d)",
        Snack_GetSampleRate(self->snd),
        Snack_GetNumChannels(self->snd),
        Snack_GetLength(self->snd));
}

static PyMethodDef PySound_methods[] = {
    {"read",           (PyCFunction)PySound_read,           METH_VARARGS | METH_KEYWORDS,
     "read(filename, start=0, end=-1)\n\nLoad sound data from a file."},
    {"write",          (PyCFunction)PySound_write,          METH_VARARGS | METH_KEYWORDS,
     "write(filename, format=None, start=0, end=-1)\n\nSave sound data to a file."},
    {"play",           (PyCFunction)PySound_play,           METH_VARARGS | METH_KEYWORDS,
     "play(blocking=True)\n\nPlay the sound."},
    {"record",         (PyCFunction)PySound_record,         METH_NOARGS,
     "record()\n\nStart recording into this sound object."},
    {"stop",           (PyCFunction)PySound_stop,           METH_NOARGS,
     "stop()\n\nStop playback or recording."},
    {"pause",          (PyCFunction)PySound_pause,          METH_NOARGS,
     "pause()\n\nPause playback."},
    {"crop",           (PyCFunction)PySound_crop,           METH_VARARGS,
     "crop(start, end)\n\nRemove samples outside [start, end]."},
    {"reverse",        (PyCFunction)PySound_reverse,        METH_NOARGS,
     "reverse()\n\nReverse the sample order."},
    {"get_sample",     (PyCFunction)PySound_get_sample,     METH_VARARGS,
     "get_sample(channel, index) -> float"},
    {"get_samples",    (PyCFunction)PySound_get_samples,    METH_NOARGS,
     "get_samples() -> list\n\n"
     "Return all samples as a flat list [ch0s0, ch1s0, ch0s1, ...]."},
    {"pitch",          (PyCFunction)PySound_pitch,          METH_VARARGS | METH_KEYWORDS,
     "pitch(**options) -> list of floats\n\nCompute F0 (pitch) contour."},
    {"formant",        (PyCFunction)PySound_formant,        METH_VARARGS | METH_KEYWORDS,
     "formant(**options) -> list of floats\n\nCompute formant frequencies."},
    {"power_spectrum", (PyCFunction)PySound_power_spectrum, METH_VARARGS | METH_KEYWORDS,
     "power_spectrum(fft_length=512, start=0, end=-1) -> list of dB floats"},
    {NULL, NULL, 0, NULL}
};

static PyGetSetDef PySound_getsetters[] = {
    {"length",      (getter)PySound_get_length,      NULL, "Number of sample frames", NULL},
    {"sample_rate", (getter)PySound_get_sample_rate, NULL, "Sample rate in Hz",       NULL},
    {"channels",    (getter)PySound_get_channels,    NULL, "Number of channels",      NULL},
    {"encoding",    (getter)PySound_get_encoding,    NULL, "Sample encoding constant",NULL},
    {NULL, NULL, NULL, NULL, NULL}
};

static PyTypeObject PySoundType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name      = "_snack.Sound",
    .tp_basicsize = sizeof(PySoundObject),
    .tp_dealloc   = (destructor)PySound_dealloc,
    .tp_repr      = (reprfunc)PySound_repr,
    .tp_flags     = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_doc       =
        "Sound(sample_rate=16000, channels=1, encoding='Lin16')\n\n"
        "Snack sound object.  Backed directly by the Snack C library;\n"
        "no Tcl or Tk APIs are visible to callers of this type.\n\n"
        "encoding can be any string accepted by Snack: 'Lin16', 'Lin8',\n"
        "'Alaw', 'Mulaw', 'Lin32', 'Float', 'Double', etc.",
    .tp_methods   = PySound_methods,
    .tp_getset    = PySound_getsetters,
    .tp_new       = PySound_new,
};

/* -----------------------------------------------------------------------
 * Module-level functions
 * ----------------------------------------------------------------------- */

static PyObject *
mod_get_output_devices(PyObject *Py_UNUSED(self), PyObject *Py_UNUSED(args))
{
    if (Tcl_Eval(g_interp, "snack::audio outputDevices") != TCL_OK)
        return raise_tcl_error("get_output_devices");

    Tcl_Obj *result = Tcl_GetObjResult(g_interp);
    int n;
    Tcl_Obj **elems;
    if (Tcl_ListObjGetElements(g_interp, result, &n, &elems) != TCL_OK)
        return raise_tcl_error("get_output_devices (parse)");

    PyObject *list = PyList_New(n);
    for (int i = 0; i < n; i++)
        PyList_SET_ITEM(list, i,
                        PyUnicode_FromString(Tcl_GetString(elems[i])));
    return list;
}

static PyObject *
mod_get_input_devices(PyObject *Py_UNUSED(self), PyObject *Py_UNUSED(args))
{
    if (Tcl_Eval(g_interp, "snack::audio inputDevices") != TCL_OK)
        return raise_tcl_error("get_input_devices");

    Tcl_Obj *result = Tcl_GetObjResult(g_interp);
    int n;
    Tcl_Obj **elems;
    if (Tcl_ListObjGetElements(g_interp, result, &n, &elems) != TCL_OK)
        return raise_tcl_error("get_input_devices (parse)");

    PyObject *list = PyList_New(n);
    for (int i = 0; i < n; i++)
        PyList_SET_ITEM(list, i,
                        PyUnicode_FromString(Tcl_GetString(elems[i])));
    return list;
}

static PyObject *
mod_audio_rate(PyObject *Py_UNUSED(self), PyObject *Py_UNUSED(args))
{
    if (Tcl_Eval(g_interp, "snack::audio rate") != TCL_OK)
        return raise_tcl_error("audio_rate");
    int rate;
    Tcl_GetIntFromObj(g_interp, Tcl_GetObjResult(g_interp), &rate);
    return PyLong_FromLong(rate);
}

static PyMethodDef snack_methods[] = {
    {"get_output_devices", mod_get_output_devices, METH_NOARGS,
     "Return list of available audio output device names."},
    {"get_input_devices",  mod_get_input_devices,  METH_NOARGS,
     "Return list of available audio input device names."},
    {"audio_rate",         mod_audio_rate,         METH_NOARGS,
     "Return the current audio device sample rate."},
    {NULL, NULL, 0, NULL}
};

/* -----------------------------------------------------------------------
 * Module initialisation
 * ----------------------------------------------------------------------- */

static struct PyModuleDef snackmodule = {
    PyModuleDef_HEAD_INIT,
    "_snack",
    "Snack sound toolkit – Python C extension.\n\n"
    "Uses an embedded Tcl interpreter for resource management; Tk is NOT\n"
    "required.  The Sound type provides direct C-level access to audio\n"
    "I/O, file formats, DSP analysis, and sample data.",
    -1,
    snack_methods
};

PyMODINIT_FUNC
PyInit__snack(void)
{
    /* Initialise the embedded Tcl interpreter. */
    g_interp = Tcl_CreateInterp();
    if (!g_interp) {
        PyErr_SetString(PyExc_RuntimeError, "Tcl_CreateInterp failed");
        return NULL;
    }
    if (Tcl_Init(g_interp) != TCL_OK) {
        PyErr_Format(PyExc_RuntimeError,
                     "Tcl_Init failed: %s", Tcl_GetStringResult(g_interp));
        return NULL;
    }

    /* Sound_Init is the Tcl-only (no-Tk) entry point from generic/sound.c. */
    extern int Sound_Init(Tcl_Interp *interp);
    if (Sound_Init(g_interp) != TCL_OK) {
        PyErr_Format(PyExc_RuntimeError,
                     "Sound_Init failed: %s", Tcl_GetStringResult(g_interp));
        return NULL;
    }

    if (PyType_Ready(&PySoundType) < 0) return NULL;

    PyObject *m = PyModule_Create(&snackmodule);
    if (!m) return NULL;

    Py_INCREF(&PySoundType);
    if (PyModule_AddObject(m, "Sound", (PyObject *)&PySoundType) < 0) {
        Py_DECREF(&PySoundType);
        Py_DECREF(m);
        return NULL;
    }

    /* Encoding integer constants (from jkAudIO.h) */
    PyModule_AddIntConstant(m, "LIN16",        LIN16);
    PyModule_AddIntConstant(m, "ALAW",         ALAW);
    PyModule_AddIntConstant(m, "MULAW",        MULAW);
    PyModule_AddIntConstant(m, "LIN8OFFSET",   LIN8OFFSET);
    PyModule_AddIntConstant(m, "LIN8",         LIN8);
    PyModule_AddIntConstant(m, "LIN24",        LIN24);
    PyModule_AddIntConstant(m, "LIN32",        LIN32);
    PyModule_AddIntConstant(m, "SNACK_FLOAT",  SNACK_FLOAT);
    PyModule_AddIntConstant(m, "SNACK_DOUBLE", SNACK_DOUBLE);

    return m;
}

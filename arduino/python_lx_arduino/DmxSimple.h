/**
 * DmxSimple - A simple interface to DMX.
 *
 * Copyright (c) 2008-2009 Peter Knight, Tinker.it! All rights reserved.
 * Edited by Chris Gerth for higher speed for use with python_lx
 */

#ifndef DmxSimple_h
#define DmxSimple_h

#include <inttypes.h>

#if RAMEND <= 0x4FF
#define DMX_SIZE 128
#else
#define DMX_SIZE 512
#endif

class DmxSimpleClass
{
  public:
    void maxChannel(int);
    void write(int, uint8_t);
    void usePins(uint8_t, uint8_t);
};
extern DmxSimpleClass DmxSimple;

#endif

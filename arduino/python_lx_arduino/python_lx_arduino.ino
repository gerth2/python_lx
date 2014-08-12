/*
**********************************************************************************************
** Python_LX - A simple, Python and Arduino based DMX512 lighting console
** by Chris Gerth - Summer/Fall 2014
** 
** File - python_lx_arduino.ino
** Description: Main arduino sketch for DMX generation. Recieves serial data commands to 
**              set dmx frame values
**
**
**********************************************************************************************
*/


#include "DmxSimple.h" //pull from local version, which is differnt from standard library.

#define DMX_PIN 3
#define FRAME_PIN 4
#define ACTIVITY_LED_PIN 13
#define MAX_DMX_CH 150

#define START_OF_FRAME 0x10 //whenever this character is rx'ed, it means to reset reading to channel 1. 
                                //yes, this cuts back on the number of levels we can incode, but it's theater
                                //30-ft rule applies. If anyone tells you "hey, that light is at 128, not 127",
                                //they most likely are possessed. Seek the help of the Devine.


void setup() {
  Serial.begin(115200);
  DmxSimple.usePins(DMX_PIN, FRAME_PIN); //start dmx output 
  DmxSimple.maxChannel(MAX_DMX_CH);
}



void loop() {
  static uint8_t in_byte;
  static uint16_t channel;  
  
//note dmx transmits in the background at all times...
  while(!Serial.available()); //wait for something to come in
  in_byte = Serial.read();
  if (in_byte == START_OF_FRAME) 
  {
    channel = 1U;
  } 
  
  
  else 
  {
      DmxSimple.write(channel, in_byte);
      channel = min(channel + 1, MAX_DMX_CH);
  }
  
}

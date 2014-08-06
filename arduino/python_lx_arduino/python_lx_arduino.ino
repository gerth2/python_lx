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

int numch = 512;

void setup() {
  /* The most common pin for DMX output is pin 3, which DmxSimple
  ** uses by default. If you need to change that, do it here. */
  DmxSimple.usePin(3);
  Serial.begin(9600);

  /* DMX devices typically need to receive a complete set of channels
  ** even if you only need to adjust the first channel. You can
  ** easily change the number of channels sent here. If you don't
  ** do this, DmxSimple will set the maximum channel number to the
  ** highest channel you DmxSimple.write() to. */
  DmxSimple.maxChannel(numch);
  Serial.println("Initalized!");
}

void loop() {
  int ch;
  
  while(1)
  {
      for (ch = 0; ch <= numch; ch++) 
      {
    
        /* Update DMX channel 1 to new brightness */
        /*temp!!!*/
        DmxSimple.write(ch, ch);
        
      }
      
    Serial.println("Writing DMX Values...");
  }

}

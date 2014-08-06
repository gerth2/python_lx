#######################################################################################################################
#######################################################################################################################
###
### Python_LX - A simple, Python and Arduino based DMX512 lighting console
### by Chris Gerth - Summer/Fall 2014
###
### File - python_lx.py - main python function for GUI
### Dependencies - Tkinter, pySerial
###
#######################################################################################################################
#######################################################################################################################
from Tkinter import * #gui
import serial #arduino communication
import os, sys, math #system dependencies


#######################################################################################################################
### DATA
#######################################################################################################################
g_max_dmx_ch = 99; #highest DMX channel. Must be in range [1,512]
g_cur_dmx_output = [0]*g_max_dmx_ch #current dmx frame output values

c_dmx_disp_row_width = 32


#######################################################################################################################
### END DATA
#######################################################################################################################


#######################################################################################################################
### APPLICATION DEFINITION
#######################################################################################################################
class Application(Frame):
    #Button action definitions
    def go_but_act(self):
        print "Go!"
    def back_but_act(self):
        print "Back..."
    def record_cue_but_act(self):
        print "Record Cue"
        
    #GUI Creation
    def create_widgets(self):
        #dmx ch displays will be arranged in a grid. 
        #calculate this grid's size
        max_row = int(math.floor(g_max_dmx_ch/32)*2)
        if(c_dmx_disp_row_width < g_max_dmx_ch):
            max_col = int(c_dmx_disp_row_width)
        else:
            max_col = int(g_max_dmx_ch)
            
        #define DMX vals display variables
        self.DMX_VALS_FRAME = Frame(self) #a frame to hold them all
        self.DMX_VALS_FRAME["bd"] = 3
        self.DMX_VALS_FRAME["relief"] = "groove"
        self.DMX_VALS_FRAME.grid(row = 0, column = 0)
        self.DMX_VALS_DISPS = ['']*g_max_dmx_ch
        self.DMX_VALS_STRS = ['']*g_max_dmx_ch
        self.DMX_CH_LABELS = ['']*g_max_dmx_ch
        self.DMX_VALS_ROW_FRAMES = ['']*max_row
        
        #set up the per-row frames
        for i in range(0,max_row):
            self.DMX_VALS_ROW_FRAMES[i] = Frame(self.DMX_VALS_FRAME)
            self.DMX_VALS_ROW_FRAMES[i].grid(row = i, column = 0)
            self.DMX_VALS_ROW_FRAMES[i]["pady"] = 5
        
        #configure the grid
        for i in range(0,max_col):
            self.DMX_VALS_FRAME.columnconfigure(i, pad=3)
        
        #set up the contents of the grid, ch values and labels
        for i in range(0,g_max_dmx_ch):
            self.DMX_CH_LABELS[i] = Label(self.DMX_VALS_ROW_FRAMES[int(math.floor(i/c_dmx_disp_row_width))], text = str(i+1)+':')
            self.DMX_CH_LABELS[i].grid(row=0, column=(i%c_dmx_disp_row_width))
            self.DMX_VALS_STRS[i] = StringVar() #create a string variable for each box
            self.DMX_VALS_DISPS[i] = Entry(self.DMX_VALS_ROW_FRAMES[int(math.floor(i/c_dmx_disp_row_width))], textvariable=self.DMX_VALS_STRS[i])
            self.DMX_VALS_DISPS[i]["bg"] = "black"
            self.DMX_VALS_DISPS[i]["fg"] = "white"
            self.DMX_VALS_DISPS[i]["width"] = 3
            self.DMX_VALS_DISPS[i]["exportselection"] = 0 #don't copy to clipboard by default
            self.DMX_VALS_DISPS[i]["selectbackground"] = "slate blue"
            self.DMX_VALS_STRS[i].set(str(i)) #set default val for each box
            self.DMX_VALS_DISPS[i].grid(row=1, column=(i%c_dmx_disp_row_width))
        
        #set up a frame for the cue info
        self.CUE_INFO_FRAME= Frame(root)
        self.CUE_INFO_FRAME.grid(row = 2, column = 0)

        self.CUE_NUM_DISP_LABEL = Label(self.CUE_INFO_FRAME, text = "Cue")
        self.CUE_NUM_DISP_LABEL.grid(row=0, column=0)
        self.CUE_NUM_DISP = Entry(self.CUE_INFO_FRAME)
        self.CUE_NUM_DISP["bg"] = "navy"
        self.CUE_NUM_DISP["fg"] = "white"
        self.CUE_NUM_DISP["width"] = 4
        self.CUE_NUM_DISP["exportselection"] = 0 #don't copy to clipboard by default
        self.CUE_NUM_DISP["selectbackground"] = "slate blue"
        self.CUE_NUM_DISP.grid(row=0, column=1)
        self.CUE_TIME_UP_DISP_LABEL = Label(self.CUE_INFO_FRAME, text = "Time Up")
        self.CUE_TIME_UP_DISP_LABEL.grid(row=1, column=0)     
        self.CUE_TIME_UP_DISP = Entry(self.CUE_INFO_FRAME)
        self.CUE_TIME_UP_DISP["bg"] = "navy"
        self.CUE_TIME_UP_DISP["fg"] = "white"
        self.CUE_TIME_UP_DISP["width"] = 4
        self.CUE_TIME_UP_DISP["exportselection"] = 0 #don't copy to clipboard by default
        self.CUE_TIME_UP_DISP["selectbackground"] = "slate blue"
        self.CUE_TIME_UP_DISP.grid(row=1, column=1)        

        #set up a frame for the programming buttons
        self.PROG_BTNS = Frame(root)
        self.PROG_BTNS.grid(row = 2, column = 1)
        
        #define Record Cue Button
        self.RECCUE = Button(self.PROG_BTNS)
        self.RECCUE["text"] = "Record Cue"
        self.RECCUE["fg"]   = "black"
        self.RECCUE["command"] =  self.record_cue_but_act
        self.RECCUE.grid(row = 0, column = 0)
        
        #set up a frame for the show control buttons
        self.SHOW_CTRL_BTNS = Frame(root)
        self.SHOW_CTRL_BTNS.grid(row = 3, column = 1)
    
        #define Back Button
        self.BACK = Button(self.SHOW_CTRL_BTNS)
        self.BACK["text"] = "BACK"
        self.BACK["fg"]   = "red"
        self.BACK["command"] =  self.back_but_act
        self.BACK.grid(row = 0, column = 0)
        
        #define Go Button
        self.GO = Button(self.SHOW_CTRL_BTNS)
        self.GO["text"] = "GO"
        self.GO["fg"]   = "green"
        self.GO["command"] =  self.go_but_act
        self.GO.grid(row = 0, column = 2)

    #I don't really know what this does, but it doesn't work without it. :(
    def __init__(self, master=None):
        Frame.__init__(self, master)
        self.grid()
        self.create_widgets()
#######################################################################################################################
### END APPLICATION DEFINITION
#######################################################################################################################

#######################################################################################################################
### MAIN FUNCTION
#######################################################################################################################
root = Tk()
app = Application(master=root)
app.mainloop() #sit here while events happen

#######################################################################################################################
### END MAIN FUNCTION
#######################################################################################################################
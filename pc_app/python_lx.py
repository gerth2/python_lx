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
import os, sys, math, threading, time, datetime #system dependencies


#######################################################################################################################
### DATA
#######################################################################################################################
#Constants
c_dmx_disp_row_width = 32
c_max_dmx_ch = 16; #highest DMX channel. Must be in range [1,512]

#"enum" def for states of the system
c_STATE_NOT_READY = -1
c_STATE_STANDBY = 0
c_STATE_TRANSITION_FWD = 1
c_STATE_TRANSITION_BKW = 2

#Global Variables
g_cur_dmx_output = [0]*c_max_dmx_ch # current dmx frame output values
g_cur_cue_index = 0 # current cue (index into cue list). Invalid if state is "TRANSITION_FWD" or "TRANSITION_BKW"
g_prev_cue_index = 0 # last cue (index into cue list). Valid only if state is "TRANSITION_FWD" or "TRANSITION_BKW"
g_next_cue_index = 0 # next cue (index into cue list). Valid only if state is "TRANSITION_FWD" or "TRANSITION_BKW"
g_state = c_STATE_NOT_READY; #current state of the system

g_kill_timed_thread = 0; #set to 1 on exit
g_sec_per_frame = 0.1;

g_cue_list = [];

#######################################################################################################################
### END DATA
#######################################################################################################################

#######################################################################################################################
### CUE DEFINITION
#######################################################################################################################
#Cues are members in a python list
#Each cue is a struct of the dmx values, the cue number, and the transition timing information
class Cue:
    def __init__(self, i_cue_num, i_dmx_vals):
        self.CUE_NUM = i_cue_num
        self.DMX_VALS = i_dmx_vals
        self.UP_TIME = 0
        self.DOWN_TIME = 0         
        
#######################################################################################################################
### END CUE DEFINITION
#######################################################################################################################

#######################################################################################################################
### CUE LIST FUNCTION DEFINITION
#######################################################################################################################
#the Cue List is a python list. These functions are used to insert or remove cues from the list

def insert_cue(cue_list, cue_num):
    print "inserting cue..."
def remove_cue(cue_list, cue_num):
    print "removing cue..."
#######################################################################################################################
### END CUE LIST FUNCTION DEFINITION
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
        max_row = int(math.floor(c_max_dmx_ch/32)*2)+1
        if(c_dmx_disp_row_width < c_max_dmx_ch):
            max_col = int(c_dmx_disp_row_width)
        else:
            max_col = int(c_max_dmx_ch)
            
        #define DMX vals display variables
        self.DMX_VALS_FRAME = Frame(self) #a frame to hold them all
        self.DMX_VALS_FRAME["bd"] = 3
        self.DMX_VALS_FRAME["relief"] = "groove"
        self.DMX_VALS_FRAME.grid(row = 0, column = 0)
        self.DMX_VALS_DISPS = ['']*c_max_dmx_ch
        self.DMX_VALS_STRS = ['']*c_max_dmx_ch
        self.DMX_CH_LABELS = ['']*c_max_dmx_ch
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
        for i in range(0,c_max_dmx_ch):
            self.DMX_CH_LABELS[i] = Label(self.DMX_VALS_ROW_FRAMES[int(math.floor(i/c_dmx_disp_row_width))], text = str(i+1)+':')
            self.DMX_CH_LABELS[i].grid(row=0, column=(i%c_dmx_disp_row_width))
            self.DMX_CH_LABELS[i]["width"] = 3
            self.DMX_VALS_STRS[i] = StringVar() #create a string variable for each box
            self.DMX_VALS_DISPS[i] = Entry(self.DMX_VALS_ROW_FRAMES[int(math.floor(i/c_dmx_disp_row_width))], textvariable=self.DMX_VALS_STRS[i])
            self.DMX_VALS_DISPS[i]["bg"] = "black"
            self.DMX_VALS_DISPS[i]["fg"] = "white"
            self.DMX_VALS_DISPS[i]["width"] = 3
            self.DMX_VALS_DISPS[i]["exportselection"] = 0 #don't copy to clipboard by default
            self.DMX_VALS_DISPS[i]["selectbackground"] = "slate blue"
            self.DMX_VALS_STRS[i].set(str(g_cur_dmx_output[i])) #set default val for each box
            self.DMX_VALS_DISPS[i].grid(row=1, column=(i%c_dmx_disp_row_width))
        
        #set up a frame for the cue info
        self.CUE_INFO_FRAME= Frame(root)
        self.CUE_INFO_FRAME.grid(row = 2, column = 0)

        self.CUE_NUM_DISP_LABEL = Label(self.CUE_INFO_FRAME, text = "Cue")
        self.CUE_NUM_DISP_LABEL.grid(row=0, column=0)
        self.CUE_NUM_DISP_STR = StringVar() #create a string variable for the cue number
        self.CUE_NUM_DISP = Entry(self.CUE_INFO_FRAME, textvariable=self.CUE_NUM_DISP_STR)
        self.CUE_NUM_DISP["bg"] = "navy"
        self.CUE_NUM_DISP["fg"] = "white"
        self.CUE_NUM_DISP["width"] = 4
        self.CUE_NUM_DISP["exportselection"] = 0 #don't copy to clipboard by default
        self.CUE_NUM_DISP["selectbackground"] = "slate blue"
        self.CUE_NUM_DISP.grid(row=0, column=1)
        self.CUE_NUM_DISP_STR.set(str(g_cur_cue_index))#temp, need cue number here
        
        self.CUE_TIME_UP_DISP_LABEL = Label(self.CUE_INFO_FRAME, text = "Time Up")
        self.CUE_TIME_UP_DISP_LABEL.grid(row=1, column=0) 
        self.CUE_TIME_UP_DISP_STR = StringVar() #create a string variable for the cue number        
        self.CUE_TIME_UP_DISP = Entry(self.CUE_INFO_FRAME, textvariable=self.CUE_TIME_UP_DISP_STR)
        self.CUE_TIME_UP_DISP["bg"] = "navy"
        self.CUE_TIME_UP_DISP["fg"] = "white"
        self.CUE_TIME_UP_DISP["width"] = 4
        self.CUE_TIME_UP_DISP["exportselection"] = 0 #don't copy to clipboard by default
        self.CUE_TIME_UP_DISP["selectbackground"] = "slate blue"
        self.CUE_TIME_UP_DISP.grid(row=1, column=1)        
        self.CUE_NUM_DISP_STR.set(0)#temp, need time here
        
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
        
    #define what needs to happen each frame update
    def update_displayed_vals(self):
        for i in range(0,c_max_dmx_ch):
            self.DMX_VALS_STRS[i].set(str(g_cur_dmx_output[i]))
        self.CUE_NUM_DISP_STR.set(str(g_cur_cue_index))#temp, need cue number here
        self.CUE_NUM_DISP_STR.set(0)#temp, need time here
                
    #I don't really know what this does, but it doesn't work without it. :(
    def __init__(self, master=None):
        Frame.__init__(self, master)
        self.grid()
        self.create_widgets()
#######################################################################################################################
### END APPLICATION DEFINITION
#######################################################################################################################

#######################################################################################################################
### TIMED THREAD
#######################################################################################################################
class Timed_Thread(threading.Thread):
    def __init__(self, threadID):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = "PYTHON_LX_TIMED_THREAD"
    def run(self):
        print "Starting " + self.name
        timedif = 0
        while(g_kill_timed_thread != 1):
            time.sleep(g_sec_per_frame - timedif) #start by waiting
            starttime = datetime.datetime.now().microsecond #mark time we start the loop at
            #temp!!!
            g_cur_dmx_output[1] = g_cur_dmx_output[1]+1
            #calculate current DMX frame
            #tx current dmx frame
            print("DMX Frame at" + str(time.time()))
            print( g_cur_dmx_output)
            app.update_displayed_vals()
            
            endtime = datetime.datetime.now().microsecond #mark how long the timed loop took
            if(endtime > starttime):
                timedif = float(endtime-starttime)/1000000.0 #calculate a sleep correction factor
            print(timedif)
            if(timedif > g_sec_per_frame ):
                timedif = g_sec_per_frame  #but warn the user if we missed the deadline
                print("WARNING MISSED TIMED LOOP DEADLINE")

    
#######################################################################################################################
### END TIMED THREAD
#######################################################################################################################


#######################################################################################################################
### MAIN FUNCTION
#######################################################################################################################
#set up cue list. 
#TEMP always make new show until file read/write is done



#set up GUI
root = Tk()
app = Application(master=root)

#initialize DMX Hardware

#run timed Thread
g_state = c_STATE_STANDBY
g_kill_timed_thread = 0;
Timed_Thread_obj= Timed_Thread(1) #thread id 1
Timed_Thread_obj.start()

#run GUI
app.mainloop() #sit here while events happen
#User has exited, tear things down

#set the TIMED kill variable, wait for it to end
g_kill_timed_thread = 1;
Timed_Thread_obj.join();


#######################################################################################################################
### END MAIN FUNCTION
#######################################################################################################################
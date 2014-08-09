########################################################################
########################################################################
###
### Python_LX - A simple, Python and Arduino based DMX512 lighting console
### by Chris Gerth - Summer/Fall 2014
###
### File - python_lx.py - main python function for GUI
### Dependencies - Tkinter, pySerial
###
########################################################################
########################################################################
from Tkinter import * #gui
import serial #arduino communication
import os, sys, math, threading, time, datetime, copy #system dependencies


########################################################################
### DATA
########################################################################
#Constants
c_dmx_disp_row_width = 32
c_max_dmx_ch = 16; #highest DMX channel. Must be in range [1,512]
c_sec_per_frame = 0.1; #refresh rate for dmx channel data

#"enum" def for states of the system
c_STATE_NOT_READY = -1
c_STATE_STANDBY = 0
c_STATE_TRANSITION_FWD = 1
c_STATE_TRANSITION_BKW = 2

#Global Variables
g_cur_dmx_output = [0]*c_max_dmx_ch # current dmx frame output values
g_prev_dmx_output = [0]*c_max_dmx_ch #dmx frame right before the go or back button was pushed
g_cur_cue_index = 0 
g_state = c_STATE_NOT_READY; #current state of the system

#User-entered numbers for cue information
g_entered_cue_num = 0
g_entered_up_time = 0
g_entered_down_time = 0

g_kill_timed_thread = 0; #set to 1 on exit
g_sec_into_transition = 0.0;

g_cue_list = [];

########################################################################
### END DATA
########################################################################

########################################################################
### CUE DEFINITION
########################################################################
#Cues are members in a python list
#Each cue is a struct of the dmx values, the cue number, and the transition timing information
class Cue:
    def __init__(self, i_cue_num, i_dmx_vals,i_up_time, i_down_time):
        self.CUE_NUM = copy.deepcopy(i_cue_num) #do nothing if we're in standby (steady state)
        self.DMX_VALS = copy.deepcopy(map(int,i_dmx_vals))
        self.UP_TIME = copy.deepcopy(i_up_time+c_sec_per_frame) #can't actually have zero transition time
        self.DOWN_TIME = copy.deepcopy(i_down_time+c_sec_per_frame) #can't actually have zero transition time
        
########################################################################
### END CUE DEFINITION
########################################################################

########################################################################
### CUE LIST FUNCTION DEFINITION
########################################################################
#the Cue List is a python list. These functions are used to insert or remove cues from the list

def insert_cue(cue_num, dmx_vals,up_time, down_time):
    global g_cur_cue_index
    #case, insert only cue
    if(len(g_cue_list) == 0):
        print("Inserting cue into empty list")
        g_cue_list.append(Cue(cue_num, dmx_vals,up_time,down_time))
        g_cur_cue_index = 0
    #case, insert first cue
    elif(cue_num < g_cue_list[0].CUE_NUM):
        print("inserting cue into the first slot in the list")
        g_cue_list.insert(0, Cue(cue_num,dmx_vals,up_time,down_time))
        g_cur_cue_index = 0
    #case, insert last cue
    elif(cue_num > g_cue_list[len(g_cue_list)-1].CUE_NUM):
        print("Inserting cue into last slot in list")
        g_cue_list.append(Cue(cue_num,dmx_vals,up_time,down_time))
        g_cur_cue_index = len(g_cue_list)-1
    #case, replace last cue
    elif(cue_num == g_cue_list[len(g_cue_list)-1].CUE_NUM):
        print("Overwriting last cue in list")
        g_cue_list[len(g_cue_list)-1] = Cue(cue_num,dmx_vals,up_time,down_time)
        g_cur_cue_index = len(g_cue_list)-1
    #case, insert cue in middle of list
    else:
        for i in range(0,len(g_cue_list)-1):
    	    if(cue_num == g_cue_list[i].CUE_NUM):#case, overwrite existing cue
                print("Overwriting Cue #" + str(g_cue_list[i].CUE_NUM))
    	        g_cue_list[i] = Cue(cue_num,dmx_vals,up_time,down_time)
                g_cur_cue_index = i
                break
    	    elif(cue_num > g_cue_list[i].CUE_NUM and cue_num < g_cue_list[i+1].CUE_NUM):
                print("Inserting cue after #" + str(g_cue_list[i].CUE_NUM) + " and before #" + str(g_cue_list[i+1].CUE_NUM))
    	        g_cue_list.insert(i+1, Cue(cue_num,dmx_vals,up_time,down_time))
                g_cur_cue_index = i+1
                break
    print(len(g_cue_list))
         		   
 
def remove_cue(cue_num):
    for i in range(0,len(g_cue_list)): #linearlly traverse list until cue is found
        if(g_cue_list[i].CUE_NUM == cue_num):
            print "removing cue..."
            g_cue_list.pop(i)

def lookup_cue_index(cue_num):
    for i in range(0,len(g_cue_list)): #linearlly traverse list until cue is found
        if(g_cue_list[i].CUE_NUM == cue_num):
            return int(i)
    print "Cue " + str(cue_num) + " does not exist"
    return -1

def print_cue(cue_num):
    l_cue_index = lookup_cue_index(cue_num)
    if(l_cue_index != -1):
        l_Cue = g_cue_list[l_cue_index]
        print("Cue # " + str(l_Cue.CUE_NUM))
        print("UpTime: " + str(l_Cue.UP_TIME))
        print("DownTime: " + str(l_Cue.DOWN_TIME))
        print("DMX Vals: ")
        for i in range(0, c_max_dmx_ch):
            print("Ch" + str(i) + "@" + str(l_Cue.DMX_VALS[i]) + ", ")

#############################################################
### END CUE LIST FUNCTION DEFINITION
########################################################################



########################################################################
### APPLICATION DEFINITION
########################################################################
class Application(Frame):

    #Button action definitions
    def goto_but_act(self):
        global g_prev_dmx_output
        global g_cur_cue_index
        global g_state
        global g_sec_into_transition 
        l_temp = lookup_cue_index(g_entered_cue_num) #determine if the cue even exists, and what index it is
        if(l_temp != -1):
            print "Goto..."
            g_prev_dmx_output = copy.deepcopy(g_cur_dmx_output)
            g_cur_cue_index = l_temp
            g_sec_into_transition = 0.0        
            g_state = c_STATE_TRANSITION_FWD

    def go_but_act(self):
        global g_prev_dmx_output
        global g_cur_cue_index
        global g_state
        global g_sec_into_transition
        if(g_cur_cue_index < len(g_cue_list)-1): 
            print "Go!"
            g_prev_dmx_output = copy.deepcopy(g_cur_dmx_output)
            g_cur_cue_index = g_cur_cue_index+1
            g_sec_into_transition = 0.0
            g_state = c_STATE_TRANSITION_FWD

    def back_but_act(self):
        global g_prev_dmx_output
        global g_cur_cue_index
        global g_state
        global g_sec_into_transition
        if(g_cur_cue_index > 0):   
            print "Back..." 
            g_prev_dmx_output = copy.deepcopy(g_cur_dmx_output)
            g_cur_cue_index = g_cur_cue_index-1
            g_state = c_STATE_TRANSITION_BKW
            g_sec_into_transition = 0.0
    
    def record_cue_but_act(self):
        global g_prev_dmx_output
        global g_cur_cue_index
        global g_sec_into_transition
        if(g_state == c_STATE_STANDBY):
           self.read_gui_input() #get current gui values
           insert_cue(g_entered_cue_num, g_cur_dmx_output, g_entered_up_time, g_entered_down_time)
    
    def read_gui_input(self): #actions to do whenever a text box is changed in the GUI
        global g_cur_dmx_output
        global g_entered_cue_num
        global g_entered_up_time
        global g_entered_down_time
        #print("TEST!")
        try:
            if(g_state == c_STATE_STANDBY):
                g_entered_cue_num = abs(float(self.CUE_NUM_DISP_STR.get()))
                g_entered_up_time = abs(float(self.CUE_TIME_UP_DISP_STR.get()))
                g_entered_down_time = abs(float(self.CUE_TIME_DOWN_DISP_STR.get()))
                for i in range(0,c_max_dmx_ch):
                    try:
                        g_cur_dmx_output[i]=abs(int(self.DMX_VALS_STRS[i].get()))
                        #print("got DMX Output" + str(i) + " at " + str(g_cur_dmx_output[i]))
                    except ValueError:
                        print "Val Error reading from GUI"
        except ValueError:
            print"Val Error Reading from GUI"

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
        self.CUE_NUM_DISP_STR.set(0)#temp, need cue number here
        
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
        self.CUE_TIME_UP_DISP_STR.set(0)#temp, need time here
       
        self.CUE_TIME_DOWN_DISP_LABEL = Label(self.CUE_INFO_FRAME, text = "Time Down")
        self.CUE_TIME_DOWN_DISP_LABEL.grid(row=2, column=0) 
        self.CUE_TIME_DOWN_DISP_STR = StringVar() #create a string variable for the cue number        
        self.CUE_TIME_DOWN_DISP = Entry(self.CUE_INFO_FRAME, textvariable=self.CUE_TIME_DOWN_DISP_STR)
        self.CUE_TIME_DOWN_DISP["bg"] = "navy"
        self.CUE_TIME_DOWN_DISP["fg"] = "white"
        self.CUE_TIME_DOWN_DISP["width"] = 4
        self.CUE_TIME_DOWN_DISP["exportselection"] = 0 #don't copy to clipboard by default
        self.CUE_TIME_DOWN_DISP["selectbackground"] = "slate blue"
        self.CUE_TIME_DOWN_DISP.grid(row=2, column=1)        
        self.CUE_TIME_DOWN_DISP_STR.set(0)#temp, need time here
        

 
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
        self.GO.grid(row = 0, column = 1)
       
        #define Go Button
        self.GOTO = Button(self.SHOW_CTRL_BTNS)
        self.GOTO["text"] = "GoToCue"
        self.GOTO["fg"]   = "black"
        self.GOTO["command"] =  self.goto_but_act
        self.GOTO.grid(row = 0, column = 2)
        
 
    #define what needs to happen each frame update
    def update_displayed_vals(self):
        for i in range(0,c_max_dmx_ch):
            self.DMX_VALS_STRS[i].set(str(int(g_cur_dmx_output[i])))
        self.CUE_NUM_DISP_STR.set(str(g_cue_list[g_cur_cue_index].CUE_NUM))
        self.CUE_TIME_UP_DISP_STR.set((g_cue_list[g_cur_cue_index].UP_TIME))
                
    #I don't really know what this does, but it doesn't work without it. :(
    def __init__(self, master=None):
        Frame.__init__(self, master)
        self.grid()
        self.create_widgets()
########################################################################
### END APPLICATION DEFINITION
########################################################################

########################################################################
### TIMED THREAD
########################################################################
class Timed_Thread(threading.Thread):
    def __init__(self, threadID):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = "PYTHON_LX_TIMED_THREAD"
    def run(self):
    	global g_state
    	global g_prev_dmx_output
        global g_cur_cue_index
        global g_sec_into_transition
        print "Starting " + self.name
        timedif = 0
        while(g_kill_timed_thread != 1):
            time.sleep(c_sec_per_frame - timedif) #start by waiting
            starttime = datetime.datetime.now().microsecond #mark time we start the loop at
            #calculate current DMX frame
           
            #if we're transitioning, the current dmx frame is dependant on how long we've been transitioning 
            if(g_state == c_STATE_TRANSITION_FWD or g_state == c_STATE_TRANSITION_BKW):
                for i in range(0, c_max_dmx_ch): #calculate each dmx value based on how far we are through the fade
                    g_cur_dmx_output[i] = int(float(g_prev_dmx_output[i])*(1.0-(g_sec_into_transition/g_cue_list[g_cur_cue_index].UP_TIME))+float(g_cue_list[g_cur_cue_index].DMX_VALS[i])*(g_sec_into_transition/g_cue_list[g_cur_cue_index].UP_TIME))
                app.update_displayed_vals() #update the displayed vals on the screen
                if(g_sec_into_transition >= g_cue_list[g_cur_cue_index].UP_TIME-c_sec_per_frame/2): #catch if the fade is done, and end it
                    g_state = c_STATE_STANDBY
                    g_sec_into_transition = 0
                    for i in range(0,c_max_dmx_ch): #account for descrete timestep issues by ensuring the last loop in transition sets the outptus right
                        g_cur_dmx_output[i] = g_cue_list[g_cur_cue_index].DMX_VALS[i]
                else:
                    g_sec_into_transition = g_sec_into_transition + c_sec_per_frame #update how far we are through the fade
          
            #if we're in standby, we should read the gui's values (user editable)
            elif(g_state == c_STATE_STANDBY):
                app.read_gui_input() 
          

            #tx current dmx frame
            
            #add serial tx here!!!!

            #calculate how well we did keeping time and correct for it
            endtime = datetime.datetime.now().microsecond #mark how long the timed loop took
            if(endtime > starttime):
                timedif = float(endtime-starttime)/1000000.0 #calculate a sleep correction factor
            if(timedif > c_sec_per_frame ):
                timedif = c_sec_per_frame  #but warn the user if we missed the deadline
                print("WARNING MISSED TIMED LOOP DEADLINE")

    
########################################################################
### END TIMED THREAD
########################################################################


########################################################################
### MAIN FUNCTION
########################################################################
#set up cue list. 
#TEMP always make new show until file read/write is done
g_cue_list.append(Cue(0,[0]*c_max_dmx_ch,0,0))
g_cur_cue_index = 0


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


########################################################################
### END MAIN FUNCTION
########################################################################

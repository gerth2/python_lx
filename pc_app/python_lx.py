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
import tkSimpleDialog
import tkFileDialog #file io dialogue boxes
import cPickle #python object mashing for file io
import serial #arduino communication
import os, sys, math, threading, time, datetime, copy, array, re #system dependencies


########################################################################
### DATA
########################################################################
#Constants (cannot change at runtime)
c_dmx_disp_row_width = 32
c_max_dmx_ch = 150; #highest DMX channel. Must be in range [1,512]
c_sec_per_frame = 0.05; #refresh rate for dmx channel data

#"enum" def for states of the system
c_STATE_NOT_READY = -1
c_STATE_STANDBY = 0
c_STATE_TRANSITION_FWD = 1
c_STATE_TRANSITION_BKW = 2

c_CH_STATE_NO_CHANGE = 0
c_CH_STATE_INC = 1
c_CH_STATE_DEC = 2
c_CH_STATE_CAPTURED = 3

#Initialize global data
def init_global_data():
    #Variables which will be global:
    global g_cur_dmx_output
    global g_prev_dmx_output
    global g_cur_cue_index
    global g_ch_states_array
    global g_entered_cue_num
    global g_entered_up_time
    global g_entered_down_time
    global g_prev_entered_cue_num
    global g_prev_entered_up_time
    global g_prev_entered_down_time
    global g_cue_list


    #set default values for these variables
    g_cur_dmx_output = [0]*c_max_dmx_ch # current dmx frame output values
    g_prev_dmx_output = [0]*c_max_dmx_ch #dmx frame right before the go or back button was pushed
    g_cur_cue_index = 0 
    g_ch_states_array = [c_CH_STATE_NO_CHANGE]*c_max_dmx_ch


    #User-entered numbers for cue information
    g_entered_cue_num = 0
    g_entered_up_time = 1
    g_entered_down_time = 1
    g_prev_entered_cue_num = 0
    g_prev_entered_up_time = 1
    g_prev_entered_down_time = 1



    g_cue_list = [];


#global variables which should not be tuned or altered when a new show is loaded
g_kill_timed_thread = 0; #set to 1 on exit
g_sec_into_transition = 0.0;
g_state = c_STATE_NOT_READY; #current state of the system

#so this is technically multithreaded. And has shared resources. Which
#implies the need for some sort of locking strategy. I suppose in the 
#future I can do a more rigorous analysis of the locking requirements.
#but I'm a EE who likes getting things done. So for now we're using the
#"wait for bug to occur and then lock until it goes away" analysis method.

#gui access lock - used to facilitate clean shutdowns between threads
#whenever the timed thread accesses the gui, it should get this lock 
#first. As it is the only thing grabbing the lock normally, this 
#should not cause deadlines to be missed by the realtime loop.
#However, before the app is closed, the main thread will wait and 
#grab the lock as soon as it is available, close the tk gui, and then try to 
#join the realtime thread. On the next realtime loop, the realtime loop will 
#get stuck in its while loop which only checks for the kill_relatime_thread
#flag. The main thread will have set the flag. Since the lock is taken, the
#realtime thread will be forced to check the kill flag, and exit gracefully
#without getting the lock. Once the realtime thread has been joined, 
#the main thread may clean up and return. All this is to prevent the main
#thread from killing the gui while the realtime thread is trying to manipulate
#it, which leads to very odd errors and system hangups (usually requiring a 
#force kill of the application)
g_gui_access_lock = threading.RLock()

#Technically, any variable touched by the real-time thread needs to have
#a lock on it to ensure two threads aren't touching the same piece of
#data at the same time. Although python should make these accesses serially,
#it seems that putting tkinter into the mix screws some things up. In the interest
#of going for low-hanging fruit first, most of the crashes seem to be fixed when 
#we simply lock the g_cur_dmx_output variable. Every write (and most of the reads)
#to g_cur_dmx_output will be surrounded by a lock and guaranteed atomic.
g_dmx_vals_lock = threading.Lock()

#turns out it's also good to lock when resources shared by button action functions
#and timed loop. This seems to be the source of the illusive button-mashing bug.
g_button_action_lock = threading.Lock()


########################################################################
### END DATA
########################################################################

########################################################################
### CUE DEFINITION
########################################################################
#Cues are members in a python list
#Each cue is a struct of the dmx values, the cue number, and the transition timing information
class Cue:
    def __init__(self, i_cue_num, i_dmx_vals,i_up_time, i_down_time, i_desc_str):
        self.CUE_NUM = copy.deepcopy(i_cue_num) #do nothing if we're in standby (steady state)
        self.DMX_VALS = copy.deepcopy(map(int,map(round,i_dmx_vals)))
        self.UP_TIME = copy.deepcopy(max(i_up_time, c_sec_per_frame)) #can't actually have zero transition time
        self.DOWN_TIME = copy.deepcopy(max(i_down_time, c_sec_per_frame)) #can't actually have zero transition time
        self.DESCRIPTION = copy.deepcopy(i_desc_str)
        
########################################################################
### END CUE DEFINITION
########################################################################

########################################################################
### CUE LIST FUNCTION DEFINITION
########################################################################
#the Cue List is a python list. These functions are used to insert or remove cues from the list

def insert_cue(cue_num, dmx_vals,up_time, down_time, desc_str):
    global g_cur_cue_index
    #case, insert only cue
    if(len(g_cue_list) == 0):
        print("Inserting cue into empty list")
        g_cue_list.append(Cue(cue_num, dmx_vals,up_time,down_time,desc_str))
        g_cur_cue_index = 0
    #case, insert first cue
    elif(cue_num < g_cue_list[0].CUE_NUM):
        print("inserting cue into the first slot in the list")
        g_cue_list.insert(0, Cue(cue_num, dmx_vals,up_time,down_time,desc_str))
        g_cur_cue_index = 0
    #case, insert last cue
    elif(cue_num > g_cue_list[len(g_cue_list)-1].CUE_NUM):
        print("Inserting cue into last slot in list")
        g_cue_list.append(Cue(cue_num, dmx_vals,up_time,down_time,desc_str))
        g_cur_cue_index = len(g_cue_list)-1
    #case, replace last cue
    elif(cue_num == g_cue_list[len(g_cue_list)-1].CUE_NUM):
        print("Overwriting last cue in list")
        g_cue_list[len(g_cue_list)-1] = Cue(cue_num, dmx_vals,up_time,down_time,desc_str)
        g_cur_cue_index = len(g_cue_list)-1
    #case, insert cue in middle of list
    else:
        for i in range(0,len(g_cue_list)-1):
    	    if(cue_num == g_cue_list[i].CUE_NUM):#case, overwrite existing cue
                print("Overwriting Cue #" + str(g_cue_list[i].CUE_NUM))
    	        g_cue_list[i] = Cue(cue_num, dmx_vals,up_time,down_time,desc_str)
                g_cur_cue_index = i
                break
    	    elif(cue_num > g_cue_list[i].CUE_NUM and cue_num < g_cue_list[i+1].CUE_NUM):
                print("Inserting cue after #" + str(g_cue_list[i].CUE_NUM) + " and before #" + str(g_cue_list[i+1].CUE_NUM))
    	        g_cue_list.insert(i+1, Cue(cue_num, dmx_vals,up_time,down_time,desc_str))
                g_cur_cue_index = i+1
                break
    print(len(g_cue_list))
         		   
 
def remove_cue(cue_num):
    for i in range(0,len(g_cue_list)): #linearly traverse list until cue is found
        if(g_cue_list[i].CUE_NUM == cue_num):
            print "removing cue..."
            g_cue_list.pop(i)

def lookup_cue_index(cue_num):
    for i in range(0,len(g_cue_list)): #linearly traverse list until cue is found
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

def update_ch_states_array(prev_cue_index, next_cue_index):
    for i in range(0,c_max_dmx_ch):
        if(g_ch_states_array[i] != c_CH_STATE_CAPTURED): #captured channels should remain captured
            if(g_cue_list[prev_cue_index].DMX_VALS[i] == g_cue_list[next_cue_index].DMX_VALS[i]):
                g_ch_states_array[i] = c_CH_STATE_NO_CHANGE
            elif(g_cue_list[prev_cue_index].DMX_VALS[i] > g_cue_list[next_cue_index].DMX_VALS[i]):
                g_ch_states_array[i] = c_CH_STATE_DEC
            elif(g_cue_list[prev_cue_index].DMX_VALS[i] < g_cue_list[next_cue_index].DMX_VALS[i]):
                g_ch_states_array[i] = c_CH_STATE_INC

def snap_to_cue(cue_index):
    global g_cur_dmx_output
    if(cue_index >= 0 and cue_index < len(g_cue_list)-1):
        g_dmx_vals_lock.acquire()
        for i in range(0, c_max_dmx_ch):
            g_cur_dmx_output[i] = g_cue_list[cue_index].DMX_VALS[i]
        g_dmx_vals_lock.release()
        app.update_displayed_vals()

#get a suggestion for the next cue number to use
def get_next_available_cue_num(i_cur_cue_index):
    if(i_cur_cue_index == len(g_cue_list) - 1):
        return min(math.floor(g_cue_list[i_cur_cue_index].CUE_NUM + 1), 999.9)
    if(i_cur_cue_index < len(g_cue_list)-1):
        if(g_cue_list[i_cur_cue_index+1].CUE_NUM > g_cue_list[i_cur_cue_index].CUE_NUM + 1):
            return math.floor(g_cue_list[i_cur_cue_index].CUE_NUM + 1)
        elif(g_cue_list[i_cur_cue_index+1].CUE_NUM > g_cue_list[i_cur_cue_index].CUE_NUM + 0.2):
            return round((g_cue_list[i_cur_cue_index+1].CUE_NUM + g_cue_list[i_cur_cue_index].CUE_NUM)/2, 1)
    else:
        return g_cue_list[i_cur_cue_index].CUE_NUM
########################################################################
### END CUE LIST FUNCTION DEFINITION
########################################################################



########################################################################
### APPLICATION DEFINITION
########################################################################

#main application
class Application(Frame):

    #Button action definitions
    def goto_but_act(self):
        GotoCueDialog(root, title = "GoTo Cue")

            
    def go_but_act(self):
        global g_prev_dmx_output
        global g_cur_cue_index
        global g_state
        global g_sec_into_transition
        g_button_action_lock.acquire()
        if(g_cur_cue_index < len(g_cue_list)-1): 
            print "Go!"
            update_ch_states_array(g_cur_cue_index, g_cur_cue_index+1)
            self.set_ch_colors() 
            g_dmx_vals_lock.acquire()
            g_prev_dmx_output = copy.deepcopy(g_cur_dmx_output)
            g_dmx_vals_lock.release()
            g_cur_cue_index = g_cur_cue_index+1
            self.update_displayed_cue_list()
            g_sec_into_transition = 0.0
            g_state = c_STATE_TRANSITION_FWD
        g_button_action_lock.release()

    def back_but_act(self):
        global g_prev_dmx_output
        global g_cur_cue_index
        global g_state
        global g_sec_into_transition
        g_button_action_lock.acquire()
        if(g_cur_cue_index > 0):   
            print "Back..."
            update_ch_states_array(g_cur_cue_index, g_cur_cue_index-1)
            self.set_ch_colors() 
            g_dmx_vals_lock.acquire()
            g_prev_dmx_output = copy.deepcopy(g_cur_dmx_output)
            g_dmx_vals_lock.release()
            g_cur_cue_index = g_cur_cue_index-1
            self.update_displayed_cue_list()
            g_state = c_STATE_TRANSITION_BKW
            g_sec_into_transition = 0.0
        g_button_action_lock.release()
    
    def record_cue_but_act(self):
        RecCueDialog(root, title = "Record Cue")

    def release_all_captured_ch(self):
        global g_ch_states_array
        global g_state
        global g_cur_cue_index
        global g_cue_list
        global g_cur_dmx_output
        g_button_action_lock.acquire()
        if(g_state == c_STATE_STANDBY):
            g_dmx_vals_lock.acquire()
            for i in range(0, c_max_dmx_ch):
                if(g_ch_states_array[i] == c_CH_STATE_CAPTURED):
                    g_cur_dmx_output[i] = g_cue_list[g_cur_cue_index].DMX_VALS[i] #restore old value
                    g_ch_states_array[i] = c_CH_STATE_NO_CHANGE #reset ch state
            g_dmx_vals_lock.release()
            self.set_ch_colors()
            self.update_displayed_vals()
            self.update_displayed_cue_list()
        g_button_action_lock.release()
          
    #GUI interaction functions 
    # def read_gui_input(self): #actions to do whenever a text box is changed in the GUI
        # global g_cur_dmx_output
        # global g_prev_dmx_output
        # global g_entered_cue_num
        # global g_entered_up_time
        # global g_entered_down_time
        # global g_ch_states_array
        # l_update_colors = 0
        # try:
            # if(g_state == c_STATE_STANDBY):
                # g_prev_dmx_output = copy.deepcopy(g_cur_dmx_output)
                # g_entered_cue_num = min(round(abs(float(self.CUE_NUM_DISP_STR.get())),1),999.9)
                # g_entered_up_time = min(round(abs(float(self.CUE_TIME_UP_DISP_STR.get())),1), 99.9)
                # g_entered_down_time = min(round(abs(float(self.CUE_TIME_DOWN_DISP_STR.get())),1), 99.9)
                # for i in range(0,c_max_dmx_ch):
                    # try: #sanitize inputs
                        # g_cur_dmx_output[i]=max(0,min(abs(int(round(float(self.DMX_VALS_STRS[i].get())))),255))
                        # if(g_cur_dmx_output[i] != g_prev_dmx_output[i]):
                            # print("ch"+str(i)+" has changed")
                            # l_update_colors = 1
                            # g_ch_states_array[i] = c_CH_STATE_CAPTURED
                    # except ValueError:
                        # print "Val Error reading from GUI"
        # except ValueError:
            # print"Val Error Reading from GUI"
        # if(l_update_colors == 1):
            # self.set_ch_colors()
     
    def set_ch_colors(self):
        global g_ch_states_array
        try:
            for i in range(0, c_max_dmx_ch):
                if(g_ch_states_array[i] == c_CH_STATE_NO_CHANGE):
                    self.DMX_VALS_DISPS[i]["fg"] = "white"
                elif(g_ch_states_array[i] == c_CH_STATE_INC):
                    self.DMX_VALS_DISPS[i]["fg"] = "orange"
                elif(g_ch_states_array[i] == c_CH_STATE_DEC):    
                    self.DMX_VALS_DISPS[i]["fg"] = "light blue"
                elif(g_ch_states_array[i] == c_CH_STATE_CAPTURED):
                    self.DMX_VALS_DISPS[i]["fg"] = "yellow"
        except:
            print "something stupid happened while changing colors..."
        
    def update_displayed_cue_list(self):
        l_new_string = ""
        min_draw_cue_index = max(0,g_cur_cue_index-3)
        max_draw_cue_index = min(min_draw_cue_index+10,len(g_cue_list)-1)
        for cue_index_iter in range(min_draw_cue_index,max_draw_cue_index+1): 
            if(cue_index_iter == g_cur_cue_index): #place marker if we're on this cue
                l_new_string +=">"
            else:
                l_new_string += " "
            
            #write the cue number and up/dn time
            l_new_string += "{: ^5.1f} | {: ^4.1f}/{: ^4.1f} | ".format(g_cue_list[cue_index_iter].CUE_NUM, g_cue_list[cue_index_iter].UP_TIME, g_cue_list[cue_index_iter].DOWN_TIME)
            
            #write the description
            l_new_string += g_cue_list[cue_index_iter].DESCRIPTION
            #newline
            l_new_string += "\n"
        
        #end of list marker    
        l_new_string += "--------------------------------------------------"
        
        #set the string
        self.CUE_LIST_TEXT_STR.set(l_new_string)
            
    def update_displayed_vals(self):
        g_dmx_vals_lock.acquire()
        for i in range(0,c_max_dmx_ch):
            self.DMX_VALS_STRS[i].set(str(int(g_cur_dmx_output[i])))
        g_dmx_vals_lock.release()
        self.CUE_NUM_DISP_STR.set(str(g_cue_list[g_cur_cue_index].CUE_NUM))
        self.CUE_TIME_UP_DISP_STR.set((g_cue_list[g_cur_cue_index].UP_TIME))
        self.CUE_TIME_DOWN_DISP_STR.set((g_cue_list[g_cur_cue_index].DOWN_TIME))
        
    def set_dmx_vals_but_act(self):
        ChSetDialog(root, title = "Set DMX Vals")

    def keypress_handler(self, event):
        input = event.char
        if(input == " "):
            self.go_but_act()
        elif(input == "b"):
            self.back_but_act()
        elif(input == "r"):
            RecCueDialog(root, title = "Record Cue")
        elif(input == "s"):
            ChSetDialog(root, title = "Set DMX Vals")
        elif(input == "g"):
            GotoCueDialog(root, title = "GoTo Cue")
            
    
 
    #GUI Creation
    def create_widgets(self):
        #dmx ch displays will be arranged in a grid. 
        #calculate this grid's size
        max_row = int(math.floor(c_max_dmx_ch/32)*2)+1
        if(c_dmx_disp_row_width < c_max_dmx_ch):
            max_col = int(c_dmx_disp_row_width)
        else:
            max_col = int(c_max_dmx_ch)
        
        #keybindings
        root.bind("<Key>", self.keypress_handler)
        root.bind("<Control-s>", save_show_file)
        root.bind("<Control-o>", open_show_file)
        root.bind("<Control-n>", new_show)
        
        #grab focus
        self.focus_set()
        
        #define DMX vals display variables
        self.DMX_VALS_FRAME = Frame(self) #a frame to hold them all
        self.DMX_VALS_FRAME["bd"] = 3
        self.DMX_VALS_FRAME["relief"] = "groove"
        self.DMX_VALS_FRAME.grid(row = 0, column = 0)
        self.DMX_VALS_DISPS = ['']*c_max_dmx_ch
        self.DMX_VALS_STRS = ['']*c_max_dmx_ch
        self.DMX_CH_LABELS = ['']*c_max_dmx_ch
        self.DMX_VALS_ROW_FRAMES = ['']*max_row
        
        #dmx vals label
        self.DMX_VALS_LABEL = Label(self.DMX_VALS_FRAME)
        self.DMX_VALS_LABEL.grid(row = 0, column = 0)
        self.DMX_VALS_LABEL["text"] = "DMX Output"
        
        
        #set up the per-row frames
        for i in range(0,max_row):
            self.DMX_VALS_ROW_FRAMES[i] = Frame(self.DMX_VALS_FRAME)
            self.DMX_VALS_ROW_FRAMES[i].grid(row = i+1, column = 0)
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
            self.DMX_VALS_DISPS[i] = Label(self.DMX_VALS_ROW_FRAMES[int(math.floor(i/c_dmx_disp_row_width))], textvariable=self.DMX_VALS_STRS[i])
            self.DMX_VALS_DISPS[i]["bg"] = "black"
            self.DMX_VALS_DISPS[i]["fg"] = "white"
            self.DMX_VALS_DISPS[i]["width"] = 3
            self.DMX_VALS_STRS[i].set(str(g_cur_dmx_output[i])) #set default val for each box
            self.DMX_VALS_DISPS[i].grid(row=1, column=(i%c_dmx_disp_row_width))
        
        #set up a frame for the cue info
        self.CUE_INFO_FRAME= Frame(root)
        self.CUE_INFO_FRAME.grid(row = 2, column = 0)

        self.CUE_NUM_DISP_LABEL = Label(self.CUE_INFO_FRAME, text = "Cue")
        self.CUE_NUM_DISP_LABEL.grid(row=0, column=0)
        self.CUE_NUM_DISP_STR = StringVar() #create a string variable for the cue number
        self.CUE_NUM_DISP = Label(self.CUE_INFO_FRAME, textvariable=self.CUE_NUM_DISP_STR)
        self.CUE_NUM_DISP["bg"] = "navy"
        self.CUE_NUM_DISP["fg"] = "white"
        self.CUE_NUM_DISP["width"] = 4
        self.CUE_NUM_DISP.grid(row=0, column=1)
        self.CUE_NUM_DISP_STR.set(str(g_entered_cue_num))
        
        self.CUE_TIME_UP_DISP_LABEL = Label(self.CUE_INFO_FRAME, text = "Time Up")
        self.CUE_TIME_UP_DISP_LABEL.grid(row=1, column=0) 
        self.CUE_TIME_UP_DISP_STR = StringVar() #create a string variable for the cue number        
        self.CUE_TIME_UP_DISP = Label(self.CUE_INFO_FRAME, textvariable=self.CUE_TIME_UP_DISP_STR)
        self.CUE_TIME_UP_DISP["bg"] = "navy"
        self.CUE_TIME_UP_DISP["fg"] = "white"
        self.CUE_TIME_UP_DISP["width"] = 4
        self.CUE_TIME_UP_DISP.grid(row=1, column=1)        
        self.CUE_TIME_UP_DISP_STR.set(str(g_entered_up_time))
       
        self.CUE_TIME_DOWN_DISP_LABEL = Label(self.CUE_INFO_FRAME, text = "Time Down")
        self.CUE_TIME_DOWN_DISP_LABEL.grid(row=2, column=0) 
        self.CUE_TIME_DOWN_DISP_STR = StringVar() #create a string variable for the cue number        
        self.CUE_TIME_DOWN_DISP = Label(self.CUE_INFO_FRAME, textvariable=self.CUE_TIME_DOWN_DISP_STR)
        self.CUE_TIME_DOWN_DISP["bg"] = "navy"
        self.CUE_TIME_DOWN_DISP["fg"] = "white"
        self.CUE_TIME_DOWN_DISP["width"] = 4
        self.CUE_TIME_DOWN_DISP.grid(row=2, column=1)        
        self.CUE_TIME_DOWN_DISP_STR.set(str(g_entered_down_time))
        
        #define cue list frame and display
        self.CUE_LIST_FRAME = Frame(root)
        self.CUE_LIST_FRAME.grid(row = 1, column = 0)
        self.CUE_LIST_FRAME["relief"] = "groove"
        self.CUE_LIST_FRAME["bd"] = 3
        
        self.CUE_LIST_TEXT_LABEL1 = Label(self.CUE_LIST_FRAME)
        self.CUE_LIST_TEXT_LABEL1.grid(row = 0, column = 0)
        self.CUE_LIST_TEXT_LABEL1["text"] = "Cue List"
        
        self.CUE_LIST_TEXT_LABEL2 = Label(self.CUE_LIST_FRAME)
        self.CUE_LIST_TEXT_LABEL2["justify"] = LEFT
        self.CUE_LIST_TEXT_LABEL2.grid(row = 1, column = 0)
        self.CUE_LIST_TEXT_LABEL2["width"] = 50
        self.CUE_LIST_TEXT_LABEL2["anchor"] = W
        self.CUE_LIST_TEXT_LABEL2["font"] = "TkFixedFont"
        self.CUE_LIST_TEXT_LABEL2["text"] = " Cue  |  Up/Dn   |  Description"
        
        self.CUE_LIST_TEXT = Label(self.CUE_LIST_FRAME)
        self.CUE_LIST_TEXT.grid(row = 2, column = 0)
        self.CUE_LIST_TEXT_STR = StringVar()
        self.CUE_LIST_TEXT["bg"] = "black"
        self.CUE_LIST_TEXT["fg"] = "white"
        self.CUE_LIST_TEXT["height"] = 10
        self.CUE_LIST_TEXT["width"] = 50
        self.CUE_LIST_TEXT["anchor"] = NW
        self.CUE_LIST_TEXT["justify"] = LEFT
        self.CUE_LIST_TEXT["font"] = "TkFixedFont"
        self.CUE_LIST_TEXT["padx"] = 5
        self.CUE_LIST_TEXT["pady"] = 5
        self.CUE_LIST_TEXT["textvariable"] = self.CUE_LIST_TEXT_STR
        self.CUE_LIST_TEXT_STR.set("")
        
        
        #set up a frame for the programming buttons
        self.PROG_BTN_FRAME = Frame(root)
        self.PROG_BTN_FRAME.grid(row = 2, column = 1)
        
        #define Record Cue Button
        self.RECCUE = Button(self.PROG_BTN_FRAME)
        self.RECCUE["text"] = "Record Cue"
        self.RECCUE["fg"]   = "black"
        self.RECCUE["command"] =  self.record_cue_but_act
        self.RECCUE.grid(row = 0, column = 0)
        
        self.RELEASE_ALL = Button(self.PROG_BTN_FRAME)
        self.RELEASE_ALL["text"] = "Release All"
        self.RELEASE_ALL["fg"]   = "black"
        self.RELEASE_ALL["command"] =  self.release_all_captured_ch
        self.RELEASE_ALL.grid(row = 1, column = 0)
        
        self.SET_CH_VALS = Button(self.PROG_BTN_FRAME)
        self.SET_CH_VALS["text"] = "Set Ch..."
        self.SET_CH_VALS["fg"]   = "black"
        self.SET_CH_VALS["command"] = self.set_dmx_vals_but_act
        self.SET_CH_VALS.grid(row = 2, column = 0)
        
        #set up a frame for the show control buttons
        self.SHOW_CTRL_BTNS = Frame(root)
        self.SHOW_CTRL_BTNS.grid(row = 0, column = 1)
    
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

        #set up the top level menu
        self.MENU_BAR = Menu(root)
        self.FILE_MENU = Menu(self.MENU_BAR, tearoff = 0)
        self.FILE_MENU.add_command(label = "New Show", command = new_show )
        self.FILE_MENU.add_command(label = "Open Show", command = open_show_file)
        self.FILE_MENU.add_command(label = "Save Show", command = save_show_file)
        self.FILE_MENU.add_separator()
        self.FILE_MENU.add_command(label = "Exit", command = app_exit_graceful)
        self.MENU_BAR.add_cascade(label = "File", menu = self.FILE_MENU)
                       
    #what to do when initalized...
    def __init__(self, master=None):
        Frame.__init__(self, master) #make its own master frame
        self.grid() #set in grid mode
        self.create_widgets() #create everything within the frame
        self.update_displayed_cue_list() #update displayed cue list (nowhere better to initialize this...)

#channel set dialog box
class ChSetDialog(tkSimpleDialog.Dialog):
    def body(self, master):
        Label(master, text="Enter Channel and Level").grid(row=0,column=0)
        self.USER_ENTRY = Entry(master)
        self.USER_ENTRY.grid(row = 1, column = 0)
        return self.USER_ENTRY #initial focus
        
    def apply(self): #what to do when OK is hit - process user string to set channels accordingly.
        #allowed entry syntax:
        # <ch> * <val> - set ch to val
        # <ch1>-<ch2> * <val> - set all channels between ch1 and ch2 inclusive to val (RANGE)
        # <ch1>+<ch2>+<ch3> * <val> - set all of ch1, ch2, and ch3 to a val (AND)
        # <ch1>-<ch2>+<ch3> * <val> - combo of AND/RANGE
        # / * <val> - set all dmx channels to a val       
        ch_to_set_list = [] #list of all channels we will want to set
        input_str = "".join(str(self.USER_ENTRY.get()).split()) #remove all whitespace
        (channels_str, part_char, val_str) = input_str.partition('*')
        if(part_char != "*" or channels_str == "*"):
            print("Syntax Error while setting ch values: input must have exactly one '*'")
            return
        else:
            #attempt to read in dmx value to set
            try:
                dmx_val_to_set = max(0,min(abs(int(round(float(val_str)))),255)) #get and sanitize user input
                print("setting to " + str(dmx_val_to_set))
            except ValueError:
                print("Error while trying to convert the value input to a dmx value")
                return
            #parse the channels to change
            if(channels_str == "/"):
                print("set all ch...")
                g_dmx_vals_lock.acquire()
                for ch_iter in range(0, c_max_dmx_ch):
                     g_cur_dmx_output[i] = dmx_val_to_set
                     g_ch_states_array[i] = c_CH_STATE_CAPTURED
                g_dmx_vals_lock.release()
            else:
                ch_range_strs = re.findall("[0-9]{1,3}[-][[0-9]{1,3}",channels_str)
                ch_and_strs = re.findall("[0-9]{1,3}",channels_str)
                #print(ch_range_strs) 
                #print(ch_and_strs)
                
                try:
                    for str_iter in ch_range_strs:
                        (lower_limit_str,upper_limit_str) = str_iter.split('-')
                        upper_limit = max(2,min(abs(int(round(float(upper_limit_str)))),512))
                        lower_limit = max(1,min(abs(int(round(float(lower_limit_str)))),512))
                        if(upper_limit < lower_limit): #if the user enters them backwards, that's ok, just flip them
                            temp = upper_limit
                            upper_limit = lower_limit
                            lower_limit = temp
                        for ch_num in range(lower_limit, upper_limit):
                            ch_to_set_list.append(ch_num)
                except ValueError:
                    print("Syntax Error while trying to set ch values: {} is not recognized as a channel range".format(str(str_iter)))
                    return
                
                try:
                    for str_iter in ch_and_strs:
                        ch_to_set_list.append(max(1,min(abs(int(round(float(str_iter)))),512)))
                except ValueError:
                    print("Syntax Error while trying to set ch values: {} is not recognized as a channel number".format(str(str_iter)))
                    return
                #print(ch_to_set_list)
                #sanitize list
                for ch_iter in range(0, len(ch_to_set_list)):
                    ch_to_set_list[ch_iter] = max(1,min(abs(int(round(float(ch_to_set_list[ch_iter])))), c_max_dmx_ch))
                #set channels    
                g_dmx_vals_lock.acquire()
                g_button_action_lock.acquire()
                for ch_iter in ch_to_set_list:
                     g_cur_dmx_output[ch_iter-1] = dmx_val_to_set
                     g_ch_states_array[ch_iter-1] = c_CH_STATE_CAPTURED
                g_button_action_lock.release()
                g_dmx_vals_lock.release()
            
            app.update_displayed_vals()
            app.set_ch_colors()
        
#channel set dialog box
class RecCueDialog(tkSimpleDialog.Dialog):
    def body(self, master):
        Label(master, text="Enter Cue Number", width = 15).grid(row=0,column=1)
        self.CUE_ENTRY = Entry(master)
        self.CUE_ENTRY["width"] = 5
        self.CUE_ENTRY.grid(row = 1, column = 1)
        self.CUE_ENTRY.insert(0,str(get_next_available_cue_num(g_cur_cue_index)))
        
        
        Label(master, text="UpTime", width = 6).grid(row=0,column=0)
        self.UP_TIME_ENTRY = Entry(master)
        self.UP_TIME_ENTRY["width"] = 5
        self.UP_TIME_ENTRY.grid(row = 1, column = 0)
        self.UP_TIME_ENTRY.insert(0,"1.0")
        
        Label(master, text="DnTime", width = 6).grid(row=0,column=2)
        self.DOWN_TIME_ENTRY = Entry(master)
        self.DOWN_TIME_ENTRY["width"] = 5
        self.DOWN_TIME_ENTRY.grid(row = 1, column = 2)
        self.DOWN_TIME_ENTRY.insert(0,'1.0')
        
        Label(master, text="Description", width = 15).grid(row=3,column=1)
        self.CUE_DESC_ENTRY = Entry(master)
        self.CUE_DESC_ENTRY["width"] = 15
        self.CUE_DESC_ENTRY.grid(row = 4, column = 1)
        
        return self.CUE_ENTRY #initial focus
        
    def apply(self):
        global g_ch_states_array
        g_button_action_lock.acquire()
        if(g_state == c_STATE_STANDBY):
            try:
                l_entered_cue_num = min(round(abs(float(self.CUE_ENTRY.get())),1),999.9)
                l_entered_up_time = min(round(abs(float(self.UP_TIME_ENTRY.get())),1), 99.9)
                l_entered_down_time = min(round(abs(float(self.DOWN_TIME_ENTRY.get())),1), 99.9)
                l_entered_cue_desc = str(self.CUE_DESC_ENTRY.get())
            except ValueError:
                print("Error, could not save cue because inputs were not numbers.")
                g_button_action_lock.release()
                return
            #reset all ch states to NO-Change
            for i in range(0, c_max_dmx_ch):
                g_ch_states_array[i] = c_CH_STATE_NO_CHANGE
            app.set_ch_colors()
            insert_cue(l_entered_cue_num, g_cur_dmx_output, l_entered_up_time, l_entered_down_time, l_entered_cue_desc)
            app.update_displayed_cue_list()
        g_button_action_lock.release()

class GotoCueDialog(tkSimpleDialog.Dialog):
    def body(self, master):
        Label(master, text="Goto Cue Number", width = 15).grid(row=0,column=0)
        self.CUE_ENTRY = Entry(master)
        self.CUE_ENTRY["width"] = 5
        self.CUE_ENTRY.grid(row = 1, column = 0)

        return self.CUE_ENTRY #initial focus
        
    def apply(self):
        global g_prev_dmx_output
        global g_cur_cue_index
        global g_state
        global g_sec_into_transition 
        
        g_button_action_lock.acquire()
        try:
            l_entered_cue_num = min(round(abs(float(self.CUE_ENTRY.get())),1),999.9)
        except ValueError:
            print("Error, could not go to cue because inputs were not numbers.")
            g_button_action_lock.release()
            return
        l_temp = lookup_cue_index(l_entered_cue_num) #determine if the cue even exists, and what index it is
        if(l_temp != -1):
            print "Goto..."
            update_ch_states_array(g_cur_cue_index, l_temp)
            g_cur_cue_index = l_temp
            app.set_ch_colors() 
            g_dmx_vals_lock.acquire()
            g_prev_dmx_output = copy.deepcopy(g_cur_dmx_output)
            g_dmx_vals_lock.release()
            g_cur_cue_index = l_temp
            app.update_displayed_cue_list()
            g_sec_into_transition = 0.0        
            g_state = c_STATE_TRANSITION_FWD
        g_button_action_lock.release()
        
########################################################################
### END APPLICATION DEFINITION
########################################################################

########################################################################
### THREAD INTERACTION FUNCTIONS
########################################################################
def app_exit_graceful():
    global g_kill_timed_thread
    #global g_gui_access_lock
    global Timed_Thread_obj
    global app
    #set the TIMED kill variable, wait for it to end
    g_kill_timed_thread = 1
    g_gui_access_lock.acquire(blocking=1) #block here until we have the lock
    #having the lock means the timed thread is not touching the gui, we can kill it at any time now
    Timed_Thread_obj.join() #wait for the timed thread to exit
    root.destroy() #kill the gui application.
    g_ser_port.close() #close serial port
    
    #return to os at some point...

   
########################################################################
### END THREAD INTERACTION FUNCTIONS
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
        global g_kill_timed_thread
        #global g_gui_access_lock
        
        timedif = 0
        
        time.sleep(1)#ensure GUI starts
        print "Starting " + self.name
        while(g_kill_timed_thread != 1):
            time.sleep(c_sec_per_frame - timedif) #start by waiting
            starttime = datetime.datetime.now().microsecond #mark time we start the loop at
            #calculate current DMX frame
           
            #if we're transitioning, the current dmx frame is dependant on how long we've been transitioning 
            if(g_state == c_STATE_TRANSITION_FWD or g_state == c_STATE_TRANSITION_BKW):
                g_dmx_vals_lock.acquire()
                for i in range(0, c_max_dmx_ch): #calculate each dmx value based on how far we are through the fade
                    if(g_ch_states_array[i] == c_CH_STATE_INC): #captured channels should not change
                        g_cur_dmx_output[i] = int(round(float(g_prev_dmx_output[i])*(1.0-min(1,(g_sec_into_transition/g_cue_list[g_cur_cue_index].UP_TIME)))+float(g_cue_list[g_cur_cue_index].DMX_VALS[i])*min(1,(g_sec_into_transition/g_cue_list[g_cur_cue_index].UP_TIME))))
                    elif(g_ch_states_array[i] == c_CH_STATE_DEC): #captured channels should not change
                        g_cur_dmx_output[i] = int(round(float(g_prev_dmx_output[i])*(1.0-min(1,(g_sec_into_transition/g_cue_list[g_cur_cue_index].DOWN_TIME)))+float(g_cue_list[g_cur_cue_index].DMX_VALS[i])*min(1,(g_sec_into_transition/g_cue_list[g_cur_cue_index].DOWN_TIME))))
                    elif(g_ch_states_array[i] == c_CH_STATE_NO_CHANGE):
                        g_cur_dmx_output[i] = int(round(g_cue_list[g_cur_cue_index].DMX_VALS[i])) #required in case the user is mashing go/back buttons so channels don't hang
                g_dmx_vals_lock.release()
                
                #get the gui lock and update the displayed values               
                while(g_gui_access_lock.acquire(blocking = 0) == False): #attempt to acquire the lock, spin on checking the kill_thread flag while waiting
                    if(g_kill_timed_thread == 1): #if the lock is acquired, it means the main app is trying to exit. This thread should exit too then.
                        return
                g_button_action_lock.acquire()
                app.update_displayed_vals() #update the displayed vals on the screen
                g_button_action_lock.release()
                g_gui_access_lock.release() #we're done here, release the lock
                           
                
                #calculate the next state and appropriate transition actions
                if(g_sec_into_transition >= max(g_cue_list[g_cur_cue_index].UP_TIME,g_cue_list[g_cur_cue_index].DOWN_TIME)-c_sec_per_frame/2): #catch if the fade is done, and end it
                    g_button_action_lock.acquire()#atomic so seconds into transition & state dont get changed underneath us.
                    g_state = c_STATE_STANDBY
                    g_sec_into_transition = 0
                    g_button_action_lock.release()
                    g_dmx_vals_lock.acquire()  
                    for i in range(0,c_max_dmx_ch): #account for discrete timestep issues by ensuring the last loop in transition sets the outputs right
                        if(g_ch_states_array[i] != c_CH_STATE_CAPTURED):
                            g_cur_dmx_output[i] = int(round(g_cue_list[g_cur_cue_index].DMX_VALS[i]))
                    g_dmx_vals_lock.release()  #atomic so seconds into transition doesn't get changed underneath us.
                else:
                    g_button_action_lock.acquire()#atomic so seconds into transition doesn't get changed underneath us.
                    g_sec_into_transition = g_sec_into_transition + c_sec_per_frame #update how far we are through the fade
                    g_button_action_lock.release()

            #tx current dmx frame
            for i in range(0, c_max_dmx_ch):
                if(g_cur_dmx_output[i] == 0x10):
                    g_dmx_vals_lock.acquire()
                    g_cur_dmx_output[i] = 0x11 #make sure we don't tx the start-of-frame char
                    g_dmx_vals_lock.release()
            chars_to_tx = ''.join(chr(b) for b in g_cur_dmx_output)
            try:
               g_ser_port.write('\x10') #write start byte
               g_ser_port.write(chars_to_tx)
            except:
               print("Error while trying to write to serial port!!!")
            

            #calculate how well we did keeping time and correct for it
            endtime = datetime.datetime.now().microsecond #mark how long the timed loop took
            if(endtime > starttime):
                timedif = float(endtime-starttime)/1000000.0 #calculate a sleep correction factor
            if(timedif > c_sec_per_frame ):
                timedif = c_sec_per_frame  #but warn the user if we missed the deadline
                print("WARNING MISSED TIMED LOOP DEADLINE")

        print("RTThread: got kill signal, exiting")
        return
    
########################################################################
### END TIMED THREAD
########################################################################


########################################################################
### FILE IO FUNCTIONS
########################################################################
def open_show_file():
    global g_state
    global g_cue_list
    global g_cur_cue_index
    if(g_state == c_STATE_STANDBY):
        g_state = c_STATE_NOT_READY
        print("Opening...") #open default dialogue box for file open
        init_global_data()
        fname = tkFileDialog.askopenfilename(defaultextension = ".plx", filetypes = [("Show Files", ".plx"), ("All Files", "*")], title = "Open Show File")
	if(fname != ''):
            g_cue_list = cPickle.load(open(fname, "rb"))
            g_cur_cue_index = 0
            snap_to_cue(g_cur_cue_index)
            app.update_displayed_vals()
            app.update_displayed_cue_list()
	    g_state = c_STATE_STANDBY

def save_show_file():
    global g_state
    global g_cue_list
    if(g_state == c_STATE_STANDBY):
        print("Saving...")
        fname = tkFileDialog.asksaveasfilename(defaultextension = ".plx", filetypes = [("Show Files", ".plx"),("All Files", "*")], title = "Save Show File")
        if(fname != ''): #make sure user did not hit cancel
            cPickle.dump(g_cue_list, open(fname, "wb"))

def new_show():
    global g_state
    global g_cur_cue_index
    global g_cue_list
    print("Creating New Show!")
    init_global_data()
    g_cue_list.append(Cue(0,[0]*c_max_dmx_ch,1,1,"Put a short note here"))
    g_cur_cue_index = 0
    app.update_displayed_vals() #update the displayed vals on the screen
    app.update_displayed_cue_list()
    g_state = c_STATE_STANDBY

########################################################################
### END FILE IO FUNCTIONS
########################################################################


########################################################################
### MAIN FUNCTION
########################################################################
#initialize internal data
init_global_data()

#set up cue list. default to empty
g_cue_list.append(Cue(0,[0]*c_max_dmx_ch,1,1,"Put a short note here"))
g_cur_cue_index = 0


#set up GUI
root = Tk()
app = Application(master=root)
root.config(menu=app.MENU_BAR) #set the top menu bar
root.protocol("WM_DELETE_WINDOW", app_exit_graceful) #set custom close handle

#initialize DMX Hardware
try:
    if(_platform == "linux" or _platform == "linux2"):
        g_ser_port = serial.Serial('/dev/ttyACM0', 115200)# Serial port COM7 on windows. We need a dynamic way of selecting...
    else:
         g_ser_port = serial.Serial(6, 115200)# Serial port COM7 on windows. We need a dynamic way of selecting...
        
except:
    print("Error opening serial port to DMX TX Module, is it plugged in and unused?")
    sys.exit(-1)

#run timed Thread
g_state = c_STATE_STANDBY
g_kill_timed_thread = 0;
Timed_Thread_obj= Timed_Thread(1) #thread id 1
Timed_Thread_obj.start()

#run GUI
app.mainloop() #sit here while events happen
#User has exited, tear things down

########################################################################
### END MAIN FUNCTION
########################################################################

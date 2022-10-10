#!/usr/bin/env python3
"""
Library to provide input functions (see __all__) using gui or console (if guify_disable_gui() is called).

Be advised that doing "import *" from this module will replace the built-in "input" function.
"""

import tkinter as tk
import tkinter.scrolledtext
import tkinter.simpledialog
import tkinter.filedialog
import tkinter.messagebox
import tkcalendar, babel.numbers

# Used in nogui funs
import getpass
import os

import datetime
import re
import sys
import os, os.path
import json

guify_flag= True

# Call this function to use all the console ("no_gui") versions of the dialog functions.
def guify_disable_gui():
    global guify_flag
    guify_flag= False

def guify_enable_gui():
    global guify_flag
    guify_flag= True

# Fix blurry text on windows 10 with high DPI
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except ImportError:
    pass

__all__= ["guify_disable_gui", "guify_enable_gui",
          "input_str", "input",
          "input_password",
          "input_pick_option", "input_date_dmy",
          "input_open_file", "input_save_file",
          "input_Yn_str", "input_yN_str", "input_Yn", "input_yN"]

# Unused for now.
def echo_result(func):
    def new_func(*args, **kwargs):
        result= func(*args, **kwargs)
        print(result)
        return result
    return new_func

# "nogui" version of the input functions. Used when the gui_flag is not set.

def input_password_nogui(prompt):
    password= getpass.getpass(prompt)
    return password

def input_pick_option_nogui(options, prompt=""):
    option_list= list(options)
    options_with_nums= [ f"[{i+1}] {option_list[i]}" for i in range(len(option_list))]
    all_s= "   ".join(options_with_nums)
    print(prompt)
    if len(all_s) <= 80:
        print(all_s)
    else:
        print("\n".join(options_with_nums))
    choice_max= len(options_with_nums)
    choice_num= -1
    while True:
        try:
            choice_num= int(input(f"Choose an option (1 to {choice_max}) "))
            if 1 <= choice_num <= choice_max:
                break
        except ValueError:
            pass
        print("Invalid choice")
    return option_list[choice_num - 1]

def input_open_file_nogui(prompt, **kwargs):
    answer= input(prompt)
    if not os.path.isfile(answer):
        print(f"File {answer} does not exist")
        return ""
    return answer

def input_save_file_nogui(prompt, **kwargs):
    answer= input(prompt)
    return answer
    
def input_Yn_nogui(prompt=""):
    choice_s= input(prompt + " [Y/n] ")
    choice_s= choice_s.strip()
    if choice_s in ["n", "N", "no", "No", "NO"]:
        return False
    else:
        return True

def input_Yn_str_nogui(prompt=""):
    if input_Yn_nogui(prompt):
        return "y"
    else:
        return "n"
    
def input_yN_nogui(prompt=""):
    choice_s= input(prompt + " [y/N] ")
    choice_s= choice_s.strip()
    if choice_s in ["y", "Y", "yes", "Yes", "YES"]:
        return True
    else:
        return False

def input_yN_str_nogui(prompt=""):
    if input_yN_nogui(prompt):
        return "y"
    else:
        return "n"
    
def input_date_dmy_nogui(prompt="Enter a date:"):
    date= ""
    date_re= re.compile(r"\d\d/\d\d/\d\d\d\d")
    while not date:
        date= input(prompt + " Format is DD/MM/YYYY. ")
        date= date.strip()
        if not re.fullmatch(date_re, date):
            print("Invalid date format")
            date= ""
    return date

def guify_fun(nogui_version):
    def decorator(func):
        def new_func(*args, **kwargs):
            if (not guify_flag) and nogui_version:
                return nogui_version(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        return new_func
    return decorator

def center_and_hide_window(win):
    # The new two lines are necessary so avoid "blinking" the window once before withdraw takes effect
    win.overrideredirect(1) # remove borders
    win.attributes('-alpha', 0) # Hide inside borders.
    positionRight = int(win.winfo_screenwidth()/2)
    positionDown = int(win.winfo_screenheight()/2)
    win.geometry("0x0+{}+{}".format(positionRight, positionDown))  # Win does not move yet
    win.update_idletasks()  # Run "mainloop" one time. Changes win location. Do before children
    #win.deiconify() # Attempt to solve focus issues on windows. Does not work.
    win.withdraw() # hide. Cannot be run before idletasks, otherwise children get wrong pos.
    
invisible_root= None

def _add_ir(d):
    global invisible_root
    if invisible_root is None:
        # This root is necessary to allow simpledialog (and other?) standalone windows
        # to attach to something (which is surprising since they should stand alone (with _get_temp_root)
        invisible_root = tk.Tk()
        center_and_hide_window(invisible_root)
        invisible_root.title("")
    d["parent"]= invisible_root

@guify_fun(input)
def input_str(prompt):
    kwargs= {}
    _add_ir(kwargs)
    return tk.simpledialog.askstring("", prompt, **kwargs)

# Do not use echo_result decorator (for password privacy)
@guify_fun(input_password_nogui)
def input_password(prompt="Password:"):
    kwargs= {}
    _add_ir(kwargs)
    return tk.simpledialog.askstring("", prompt, show='*', **kwargs)

class SimpleOptionMenu(tk.simpledialog.Dialog):
    def __init__(self, option_list, prompt="", title="", parent= None):
        self.prompt= prompt
        self.option_list= option_list
        self.choice = tk.StringVar()
        if option_list:
            self.choice.set(option_list[0])
        else:
            self.choice.set("")
        tk.simpledialog.Dialog.__init__(self, parent, title)
        
    def body(self, master):
        w = tk.Label(master, text=self.prompt, justify=tk.LEFT)
        w.grid(row=0, padx=5, sticky=tk.W)
        self.dropdown = tk.OptionMenu(master, self.choice, *self.option_list)
        self.dropdown.grid(row=1, padx=5, sticky=tk.W+tk.E)
        return self.dropdown

    def validate(self):
        self.result= self.choice.get()
        return 1
    
    def destroy(self):
        self.dropdown = None
        tk.simpledialog.Dialog.destroy(self)

def askoptions(options, **kwargs):
    _add_ir(kwargs)
    if not "__getitem__" in options.__dir__():
        # Not subscriptable, try to convert to a list (works for dict.keys())
        options= list(options)
    d= SimpleOptionMenu(options, **kwargs)
    return d.result

class SimpleDateEntry(tk.simpledialog.Dialog):
    def __init__(self, default=None, prompt="", title="", parent= None, locale= None, date_pattern= None):
        self.prompt= prompt
        if default is None:
            self.default= datetime.date.today()
            #self.default= datetime.date.fromisoformat("2012-10-12")
        else:
            self.default= default
        self.locale= locale
        self.date_pattern= date_pattern
        tk.simpledialog.Dialog.__init__(self, parent, title)
        
    def body(self, master):
        w = tk.Label(master, text=self.prompt, justify=tk.LEFT)
        w.grid(row=0, padx=5, sticky=tk.W)
        self.cal = tkcalendar.DateEntry(master=master,
                                        year=self.default.year,
                                        month=self.default.month,
                                        day=self.default.day,
                                        locale= self.locale,
                                        date_pattern= self.date_pattern)
        self.cal.grid(row=1, padx=5, sticky=tk.W+tk.E)
        return self.cal

    def validate(self):
        self.result= self.cal.get()
        return 1
    
    def destroy(self):
        self.cal = None
        tk.simpledialog.Dialog.destroy(self)        

def askdate(**kwargs):
    _add_ir(kwargs)
    d= SimpleDateEntry(**kwargs)
    return d.result


@guify_fun(input_pick_option_nogui)
def input_pick_option(options, prompt=""):
    return askoptions(options, prompt=prompt)

@guify_fun(input_date_dmy_nogui)
def input_date_dmy(prompt="", **kwargs):
    _add_ir(kwargs)
    #date_o= askdate(prompt=prompt, locale="fr")
    date_s= askdate(prompt=prompt, date_pattern= "dd/mm/yyyy", **kwargs)
    return date_s

@guify_fun(input_open_file_nogui)
def input_open_file(prompt, **kwargs):
    _add_ir(kwargs)
    '''Example args: filetypes=[("CSV files", ".csv"), ("all files", "*")]
    
    '''
    if "initialdir" not in kwargs:
        kwargs["initialdir"]= os.getcwd()
    if "title" not in kwargs:
        kwargs["title"]= prompt
    else:
        kwargs["title"]+= ": " + prompt
    r= tk.filedialog.askopenfilename(**kwargs)
    if not r:
        r= ""
    return r

@guify_fun(input_save_file_nogui)
def input_save_file(prompt, **kwargs):
    _add_ir(kwargs)
    '''Example args: filetypes=[("Text files", ".txt"), ("all files", "*")], defaultextension=".txt"
    '''
    if "initialdir" not in kwargs:
        kwargs["initialdir"]= os.getcwd()
    if "title" not in kwargs:
        kwargs["title"]= prompt
    else:
        kwargs["title"]+= ": " + prompt
    r= tk.filedialog.asksaveasfilename(**kwargs)
    if not r:
        r= ""
    return r

# Define 4 versions of "input yes or no",
# based on return type (str or bool) and default (yes or no)
# Converts to str then back (for echoing).
def input_Yn_or_yN_str(prompt="", default="yes", title=""):
    kwargs={}
    _add_ir(kwargs)
    r= tk.messagebox.askyesno(title=title, message=prompt, default=default)
    if r:
        return "y"
    else:
        return "n"

@guify_fun(input_Yn_str_nogui)
def input_Yn_str(prompt=""):
    return input_Yn_or_yN_str(prompt=prompt, default="yes")

@guify_fun(input_yN_str_nogui)
def input_yN_str(prompt=""):
    return input_Yn_or_yN_str(prompt=prompt, default="no")

def input_Yn_or_yN(prompt="", default="yes", title=""):
    r= input_Yn_or_yN_str(title=title, prompt=prompt, default=default)
    if r in ["n", "N", "no", "No", "NO"]:
        return False
    else:
        return True
    
@guify_fun(input_Yn_nogui)
def input_Yn(prompt=""):
    return input_Yn_or_yN(prompt=prompt, default="yes")

@guify_fun(input_Yn_nogui)
def input_yN(prompt=""):
    return input_Yn_or_yN(prompt=prompt, default="no")

# Careful, replaces builtin.input
input= input_str

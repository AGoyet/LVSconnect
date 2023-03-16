#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scripting for an Axess website.

Downloads the time schedule for each room then displays the ones which are free at a given date and time.
"""

from lvs_module import *

import datetime
from bs4 import BeautifulSoup
import pickle

add_url("room", "/vsn.main/temps/salle")
add_url("select_date", "/vsn.main/temps/semaineDate")

def get_room_ids(s):
    url= get_url("room")
    r= s.get(url)
    r.raise_for_status()
    soup= BeautifulSoup(r.text, 'html.parser')
    rooms={}
    try:
        sel= soup.find_all("select", id="idSalle")[0]
        for opt in sel.find_all("option"):
            v= opt["value"]
            room_name= opt.text
            if v == "null":
                continue
            rooms[room_name]= v
    except:
        raise RuntimeError("Unexpected format for classroom selection menu")
    return rooms

def get_time_schedule(s, room_id):
    url= get_url("room")
    params= {"idSalle":str(room_id)}
    r= s.post(url, params=params)
    r.raise_for_status()
    soup= BeautifulSoup(r.text, 'html.parser')
    date_regex= r'Cours du \w+ (\d{2}) (\w+) (\d{4})'
    month_list= ["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre"]
    time_range_regex= r'de (\d\d)h(\d\d) à (\d\d)h(\d\d)'
    classes= soup.find_all("div", id="infosCoursEleve")
    schedule_list= []
    for c in classes:
        gs= re.search(date_regex, c.text).groups()
        if len(gs) != 3:
            continue
        day= int(gs[0]) # regex gives two digits
        month= 1 + month_list.index(gs[1])
        year= int(gs[2])
        date_tuple= day,month,year
        gs= re.search(time_range_regex, c.text).groups()
        if len(gs) != 4:
            continue
        start_time= int(gs[0]), int(gs[1])
        end_time= int(gs[2]), int(gs[3])
        if not (start_time and end_time):
            continue
        slot= (start_time, end_time)
        schedule_list.append((date_tuple, slot))
    return schedule_list

# time_slots is a dict of day : { slot : room_name_list }
def get_all_time_slots(s, rooms, excluded=set()):
    # Get time schedule for each room
    time_slots= {}
    always_free= set()
    print("Downloading room schedules")
    for (room_name, room_id) in rooms.items():
        if room_name in excluded:
            continue
        # flush=True to use this output as a kind of progress bar.
        print(room_name, end=" ", flush=True)
        schedule_list= get_time_schedule(s, room_id)
        if not schedule_list:
            always_free.add(room_name)
        for (date_tuple, slot) in schedule_list:
            if not date_tuple in time_slots:
                time_slots[date_tuple]= {}
            if not slot in time_slots[date_tuple]:
                time_slots[date_tuple][slot]= set()
            time_slots[date_tuple][slot].add(room_name)
    # Empty line
    print()
    always_free= list(always_free)    
    return time_slots, always_free

def s_of_date_tuple(date_tuple):
    return f"{date_tuple[0]:02d}/{date_tuple[1]:02d}/{date_tuple[2]}"

# Operations on time tuples ("tt") and slots.
# The built-in comparison operations on tuples are used extensively.
def s_of_tt(tt):
    return f"{tt[0]:02d}h{tt[1]:02d}"

def s_of_slot(slot):
    return f"{s_of_tt(slot[0])} to {s_of_tt(slot[1])}"

def add_tt(tt1, tt2):
    h1, m1= tt1
    h2, m2= tt2
    return ( h1 + h2 + (m1 + m2) // 60 ,
             (m1 + m2) % 60 )

def is_in_slot(tt, slot):
    return slot[0] <= tt <= slot[1]

def is_contained(slot1, slot2):
    return slot2[0] <= slot1[0] and slot1[1] <= slot2[1]

# Use strict inequalities so that 8h-9h00 and 9h00-10h don't overlap.
def overlap(slot1, slot2):
    if slot1[0] < slot2[0]:
        return slot2[0] < slot1[1]
    else:
        return slot1[0] < slot2[1]

def request_date_change(s, date_tuple):
    day, month, year= date_tuple
    url= get_url("select_date")
    params= {"dateSemaine" : f"{day:02d}/{month:02d}/{year}"}
    r= s.post(url, params=params)
    r.raise_for_status()

# Unused
# Returns a "reasonnable" list of non overlapping time slots, that might correspond to the actual
# "normal" time slots of the school.
# The start time of each base slot is the start of an actual slot, and the same for the end time.
# This should avoid recess times.
def guess_base_time_slots(time_slots):
    # Get all existing slots for all days
    all_slots= set()
    for date_tuple in time_slots:
        for slot in time_slots[date_tuple]:
            all_slots.add(slot)
    # Get start and end (sorted)
    start_times= list({ slot[0] for slot in all_slots})
    end_times=   list({ slot[1] for slot in all_slots})
    start_times.sort()
    end_times.sort()
    # Get base slots
    base_slots= []
    si= 0
    ei= 0
    while si < len(start_times):
        while ei < len(end_times) and end_times[ei] < start_times[si]:
            ei+= 1
        if ei >= len(end_times):
            print(f"Unexpected times in schedules, ignoring start time {s_of_tt(start_times[si])}")
            break
        base_slots.append((start_times[si], end_times[ei]))
        si+= 1
        # Keep moving the start time until after the current end time.
        while si < len(start_times) and end_times[ei] > start_times[si]:
            si+= 1
        if si >= len(start_times):
            break
        ei+= 1
    return base_slots

# Returns a free room set
# Defaults to a 21m duration (should avoid any recess time slots of <= 20m)
def find_free_rooms_sub(time_slots, rooms, date_tuple, start_tt, duration=21):
    duration= max(0, int(duration))
    assert date_tuple in time_slots
    end_tt= add_tt(start_tt, (0, duration))
    requested_slot= (start_tt, end_tt)
    # Get all time slots that overlap the requested slot
    relevant_slots= set();
    for slot in time_slots[date_tuple].keys():
        if overlap(slot, requested_slot):
            relevant_slots.add(slot)
    # Get all free rooms at that slot (by elimination)
    free_rooms= set(rooms.keys())
    for slot in relevant_slots:
        free_rooms -= set(time_slots[date_tuple][slot])
    return free_rooms

# Returns a dict of start_tt : free room set
# The max_delay is how patient the user is (in minutes).
def find_free_rooms(time_slots, rooms, date_tuple, start_tt, excluded=set(), duration=21, max_delay=30):
    # Get possible starting times when the room we are looking for is free (from now to delay).
    possible_starts= {start_tt}
    last_start_tt= add_tt(start_tt, (0, max_delay))
    # Get those that will soon be free (looking at time slots that end soon and might free a room).
    for slot in time_slots[date_tuple]:
        slot_end= slot[1]
        if start_tt < slot_end < last_start_tt:
            possible_starts.add(slot_end)
    possible_starts= list(possible_starts)
    possible_starts.sort()
    # Find rooms starting at those possible times
    free_rooms_by_start= {}
    for tt in possible_starts:
        free_rooms_by_start[tt]= find_free_rooms_sub(time_slots, rooms, date_tuple, tt, duration=duration)
    # Return a pruned version that skips the rooms already free at the previous time
    # (of the unpruned version, to still show rooms that are occupied then free again)
    pruned= {}
    prev_tt= None
    for tt in possible_starts:
        pruned[tt]= free_rooms_by_start[tt] - free_rooms_by_start.get(prev_tt, set()) - excluded
        # Remove empty times
        if not pruned[tt]:
            del pruned[tt]
        prev_tt= tt
    return pruned

# Returns a string with, the longest free slot for each room around the start time.
# Goes through each start time in order.
def s_of_free_rooms(free_rooms_by_start, date_tuple, room_schedule, whole_day, are_all_free, always_free=[]):
    r= ""
    first_it= True
    for start_tt in free_rooms_by_start:
        start_s= f"on {s_of_date_tuple(date_tuple)} at {s_of_tt(start_tt)}"
        if first_it:
            r+= f"Rooms free {start_s}:\n"
            first_it= False
        else:
            r+= f"\nRooms (soon) free {start_s}:\n"
        free_slot_rooms= []
        for room_name in free_rooms_by_start[start_tt]:
            # Maximal free time slot
            free_start, free_end= whole_day
            # Get actual free time slot starting at start_tt
            for slot in room_schedule[room_name]:
                # slot ends before now; at best the free slot starts after that
                if free_start <= slot[1] <= start_tt:
                    free_start = slot[1]
                # slot starts after now; at best the free slot ends before that
                if free_end >= slot[0] >= start_tt:
                    free_end = slot[0]
            free_slot_rooms.append(((free_start, free_end), room_name))
        if are_all_free:
            r+= "(All rooms are free at that time.)\n"
        # Multiple sorts to make it a total order
        # Sort alphabetically first (least important)
        free_slot_rooms.sort(key= lambda p : p[1])
        # Then by start time
        free_slot_rooms.sort(key= lambda p : p[0][0])
        # Sort with latest end_time in first place (most time left from now)
        free_slot_rooms.sort(reverse= True, key= lambda p : p[0][1])
        char_nb= max([len(room_name) for slot, room_name in free_slot_rooms])
        for slot, room_name in free_slot_rooms:
            end_of_day_s= ""
            if slot[1] == whole_day[1]:
                end_of_day_s= "+"
            r+= f"{room_name.ljust(char_nb)}   {s_of_slot(slot)}{end_of_day_s}\n"
    if always_free:
        r+= "\nRooms with no schedule for the week:\n"
        r+= "\n".join(always_free)
    return r

def save_time_slots(fname, time_slots, always_free, update_times, rooms):
    curr_d= datetime.datetime.now()
    curr_d_str= curr_d.strftime("%d/%m/%Y at %H:%M")
    for d in time_slots.keys():
        if not d in update_times:
            update_times[d]= curr_d_str
    data= {"time_slots":time_slots, "always_free":always_free, "update_times":update_times, "rooms":rooms}
    print(f"Writing data to file {fname}")
    with open(fname, 'wb') as f:
        pickle.dump(data, f)

# Updates the dicts.
def load_time_slots(fname, time_slots, always_free, update_times, rooms):
    print(f"Loading data from {fname}")
    try:
        with open(fname,'rb') as f:
            data= pickle.load(f)
        a,b,c,d= data["time_slots"], data["always_free"], data["update_times"], data["rooms"]
    except (KeyError, TypeError, pickle.UnpicklingError):
        raise RuntimeError(f"Error load data from file {fname}. This file must be empty or contain data created by this program.")
    time_slots.update(a)
    update_times.update(c)
    rooms.update(d)
    for room in b:
        always_free.remove(room)

# Returns result as text
def find_and_display_free_rooms(s, date_tuple, start_tt,
                                excluded=set(), duration=21, max_delay=30,
                                load_file=None, save_file=None):
    time_slots, always_free, update_times, rooms= {}, [], {}, {}
    if save_file and os.path.isfile(save_file):
        load_time_slots(save_file, time_slots, always_free, update_times, rooms)
    # Potentially update save file with load file (without checking update times; TODO?)
    if load_file:
        load_time_slots(load_file, time_slots, always_free, update_times, rooms)
    else:
        # Do the requests
        request_date_change(s, date_tuple)
        rooms= get_room_ids(s)
        new_time_slots, new_always_free= get_all_time_slots(s, rooms, excluded=excluded)
        for d in new_time_slots:
            # The absence of a date in update_times represents the fact that it has been updated in
            # the current execution (so the warning for cached data will not trigger).
            update_times.pop(d, None)
        time_slots.update(new_time_slots)
        always_free= list( set(always_free) - set(new_always_free))
    if save_file:
        save_time_slots(save_file, time_slots, always_free, update_times, rooms)
        return ""
    if not date_tuple in time_slots:
        print(date_tuple)
        print(time_slots.keys())
        return "No data for that date in the cache."
    # Find free rooms (using data)
    excluded_from_search= excluded.copy()
    excluded_from_search.update(always_free)
    free_rooms_by_start= find_free_rooms(time_slots, rooms, date_tuple, start_tt,
                                        excluded=excluded_from_search,
                                        duration=duration, max_delay=max_delay)
    nb_free_rooms= sum([len(free_rooms_by_start[k]) for k in free_rooms_by_start])
    are_all_free= nb_free_rooms + len(excluded_from_search) == len(rooms)
    # Reorganize the time slots by room (could have been computed at the same time as time_slots).
    room_schedules= {}
    for d in time_slots:
        room_schedules[d]= {}
        for room_name in rooms:
            schedule= [ slot for slot in time_slots[d] if room_name in time_slots[d][slot] ]
            schedule.sort()
            room_schedules[d][room_name]= schedule
    # Get First and last possible times of day (for the whole week)
    all_slots= set()
    for d in time_slots:
        for slot in time_slots[d]:
            all_slots.add(slot)
    whole_day= (min([slot[0] for slot in all_slots]), max([slot[1] for slot in all_slots]))
    # Display result
    result_s= ""
    result_s+= s_of_free_rooms(free_rooms_by_start, date_tuple, room_schedules[date_tuple], whole_day,
                               are_all_free, always_free=always_free)
    result_s+= "\n"
    if date_tuple in update_times:
        result_s+= f"The data for this date was downloaded on {update_times[date_tuple]}.\nIf the time schedule has been modified since, it might be incorrect.\n"
    return result_s

def tuple_of_date_dmy(date_s):
    date_dmy_regex= r'(\d{1,2})/(\d{1,2})/(\d{1,4})'
    try:
        r= re.search(date_dmy_regex, date_s)
        if not r:
            return None
        gs= r.groups()
        return int(gs[0]), int(gs[1]), int(gs[2])
    except TypeError:
        return None

def tuple_of_time_hhmm(time_s):
    if not time_s:
        return None
    time_hhmm_regex= r'(\d{1,2})(\:|h)(\d{1,2})'
    try:
        r= re.search(time_hhmm_regex, time_s)
        if not r:
            return None
        gs= r.groups()
        return int(gs[0]), int(gs[2])
    except TypeError:
        return None

# Returns a str HH:MM
def input_time_hhmm(prompt="Enter a time."):
    while True:
        time= input_str(prompt=prompt + " Format is HH:MM")
        if not time:
            return ""
        t= tuple_of_time_hhmm(time)
        if t:
            return f"{t[0]:02d}:{t[1]:02d}"
        print("Invalid time format. Format is HH:MM")

def main():
    try:
        s= None
        arg_descs=[
            #(('-H','--hour'), {'type':int}),
            #(('-M','--minute'), {'type':int}),
            (('--now',), {'action':'store_true', 'help':'Use current date and time, without any dialog.'}),
            (('-T','--time'), {'type':str, 'help':'Format is HH:MM'}),
            (('-d','--date',), {'metavar':'DATE',
                                'help':'Format is DD/MM/YYYY.'}),
            (('--excluded-rooms',), {'type':str, 'nargs':'*', 'metavar':'ROOM',
                               'help':'A list of names of rooms to exclude from the search, separated by spaces.'}),
            (('--duration',), {'type':int, 'default':21, 'help':'How long the room is needed in minutes. Low values might lead to include recess time. Default is 21.'}),
            (('--max-delay',), {'type':int, 'default':30, 'help':'The program displays additional rooms after those that are free now. This sets the maximum amount of time (in minutes) to look for those rooms. Default is 30.'}),
            (('--output',), {'metavar':'FILE', 'type':str, 'help':'Write the final result at the end of the given file.'}),
            (('--load',), {'metavar':'FILE', 'type':str, 'help':'Load data from the given file instead of downloading from the website.'}),
            (('--save',), {'metavar':'FILE', 'type':str, 'help':'Save the data downloaded from the website to the given file then exit. If the file already exists, it will be updated.'}),
        ]
        shared_args=[]
        
        args= lvs_get_args(arg_descs=arg_descs, shared_args= shared_args, description='Downloads the time schedule for each room then displays the ones which are free at a given date and time. Without any arguments, asks for date and time.')
        start_tt= None
        date_tuple= None
        curr_d= datetime.datetime.now()
        if args["now"]:
            args["date"]= None
            args["time"]= None
        elif (not args["now"]) and (args["date"] is None) and (args["time"] is None):
            choice= input_Yn(prompt="Use the current date and time?")
            if not choice:
                # Ask for date
                args["date"]= input_date_dmy(prompt="Enter the date for which to check for free rooms.")
                # Ask for time
                Args["time"]= input_time_hhmm()
        if args["date"]:
            date_tuple= tuple_of_date_dmy(args["date"])
            if not date_tuple:
                raise RuntimeError(f"Invalid format for date string (should be DD/MM/YYYY): {args['date']}")
            if date_tuple[2] < 100:
                date_tuple[2]+= 2000 #Y2.1K
        if not date_tuple:
            date_tuple= (curr_d.day, curr_d.month, curr_d.year)
            print(f"Using current date {s_of_date_tuple(date_tuple)}")
        if args["time"]:
            start_tt= tuple_of_time_hhmm(args["time"])
            if not start_tt:
                raise RuntimeError(f"Invalid format for time string (should be HH:MM): {args['time']}")
        if not start_tt:
            start_tt= (curr_d.hour, curr_d.minute)
            print(f"Using current time {s_of_tt(start_tt)}")
        excluded= set()
        if args["excluded_rooms"]:
            excluded= set(args["excluded_rooms"])
        # Done processing args
        s= None
        if not args["load"]:
            s= open_session(args["user"], args["password"])
            
        result_s= find_and_display_free_rooms(s, date_tuple, start_tt,
                                    excluded=excluded, duration=args["duration"],
                                    max_delay=args["max_delay"],
                                    load_file= args["load"], save_file= args["save"])
        print(result_s)
        output_file= args["output"]        
        if output_file and result_s:
            print(f"Writing output to {output_file}")
            with open(output_file, 'a') as f:
                f.write(result_s)
    finally:
        if s is not None:
            s.close()

if __name__ == '__main__' :
    display_errors(main)
    show_message("Done.")


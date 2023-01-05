#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scripting for an Axess website.

Downloads the time schedule for each room then displays the ones which are free at a given date and time.
"""

from lvs_module import *

import datetime
from bs4 import BeautifulSoup


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
    date_regex= r'Cours du \w+ (\d{2})'
    time_range_regex= r'de (\d\d)h(\d\d) à (\d\d)h(\d\d)'
    classes= soup.find_all("div", id="infosCoursEleve")
    schedule_list= []
    for c in classes:
        gs= re.search(date_regex, c.text).groups()
        if len(gs) != 1:
            continue
        date= int(gs[0]) # regex gives two digits
        gs= re.search(time_range_regex, c.text).groups()
        if len(gs) != 4:
            continue
        start_time= int(gs[0]), int(gs[1])
        end_time= int(gs[2]), int(gs[3])
        if not (start_time and end_time):
            continue
        slot= (start_time, end_time)
        schedule_list.append((date, slot))
    return schedule_list

def get_all_time_slots(s, rooms, excluded=set()):
    # Get time schedule for each room
    time_slots= {}
    always_free= set()
    print("Downloading room schedules")
    for (room_name, room_id) in rooms.items():
        if room_name in excluded:
            continue
        print(room_name)
        schedule_list= get_time_schedule(s, room_id)
        if not schedule_list:
            always_free.add(room_name)
        for (day, slot) in schedule_list:
            if not day in time_slots:
                time_slots[day]= {}
            if not slot in time_slots[day]:
                time_slots[day][slot]= set()
            time_slots[day][slot].add(room_name)
    return time_slots, always_free

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

def request_date_change(s, year, month, day):
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
    for day in time_slots:
        for slot in time_slots[day]:
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
def find_free_rooms_sub(time_slots, rooms, day, start_tt, duration=21):
    duration= max(0, int(duration))
    assert day in time_slots
    end_tt= add_tt(start_tt, (0, duration))
    requested_slot= (start_tt, end_tt)
    # Get all time slots that overlap the requested slot
    relevant_slots= set();
    for slot in time_slots[day].keys():
        if overlap(slot, requested_slot):
            relevant_slots.add(slot)
    # Get all free rooms at that slot (by elimination)
    free_rooms= set(rooms.keys())
    for slot in relevant_slots:
        free_rooms -= set(time_slots[day][slot])
    return free_rooms

# Returns a dict of start_tt : free room set
# The max_delay is how patient the user is (in minutes).
def find_free_rooms(time_slots, rooms, day, start_tt, excluded=set(), duration=21, max_delay=30):
    # Get possible starting times when the room we are looking for is free (from now to delay).
    possible_starts= {start_tt}
    last_start_tt= add_tt(start_tt, (0, max_delay))
    # Get those that will soon be free (looking at time slots that end soon and might free a room).
    for slot in time_slots[day]:
        slot_end= slot[1]
        if start_tt < slot_end < last_start_tt:
            possible_starts.add(slot_end)
    possible_starts= list(possible_starts)
    possible_starts.sort()
    # Find rooms starting at those possible times
    free_rooms_by_start= {}
    for tt in possible_starts:
        free_rooms_by_start[tt]= find_free_rooms_sub(time_slots, rooms, day, tt, duration=duration)
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
def s_of_free_rooms(free_rooms_by_start, room_schedule, whole_day, always_free=set(), start_is_now= True):
    r= ""
    first_it= True
    for start_tt in free_rooms_by_start:
        start_s= f"at {s_of_tt(start_tt)}"
        if first_it:
            if start_is_now:
                start_s= f"now ({s_of_tt(start_tt)})"
        if first_it:
            r+= f"Rooms free {start_s}:\n"
            first_it= False
        else:
            r+= f"\nAdditional rooms free {start_s}:\n"
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

def find_and_display_free_rooms(s, year, month, day, start_tt,
                                excluded=set(), duration=21, max_delay=30, start_is_now= True):
    ## Do the requests
    # This means that year, month and day are ignored if start_is_now is True
    if not start_is_now:
        request_date_change(s, year, month, day)
    rooms= get_room_ids(s)
    time_slots, always_free= get_all_time_slots(s, rooms, excluded=excluded)
    # Find free rooms (using downloaded data)
    excluded_from_search= excluded.copy()
    excluded_from_search.update(always_free)
    free_rooms_by_start= find_free_rooms(time_slots, rooms, day, start_tt,
                                        excluded=excluded_from_search,
                                        duration=duration, max_delay=max_delay)
    # Reorganize the time slots by room (could have been computed at the same time as time_slots).
    room_schedules_days= {}
    for d in time_slots:
        room_schedules_days[d]= {}
        for room_name in rooms:
            schedule= [ slot for slot in time_slots[d] if room_name in time_slots[d][slot] ]
            schedule.sort()
            room_schedules_days[d][room_name]= schedule
    # Get First and last possible times of day (for the whole week)
    all_slots= set()
    for d in time_slots:
        for slot in time_slots[d]:
            all_slots.add(slot)
    whole_day= (min([slot[0] for slot in all_slots]), max([slot[1] for slot in all_slots]))
    # Display result
    result_s= s_of_free_rooms(free_rooms_by_start, room_schedules_days[day], whole_day,
                              always_free=always_free, start_is_now=start_is_now)
    print(result_s)

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
            (('--max-delay',), {'type':int, 'default':30, 'help':'The program displays additional rooms after those that are free now. This sets the maximum amount of time (in minutes) to look for those rooms. Default is 30.'})
        ]
        shared_args=[]
        args= lvs_get_args(arg_descs=arg_descs, shared_args= shared_args, description='Downloads the time schedule for each room then displays the ones which are free at a given date and time. Without any arguments, asks for date and time.')
        start_is_now= True  # Will stay True only if we guessed the current date and time
        start_tt= None
        def all_None(args, names):
            for name in names:
                if name in args and (not args[name] is None):
                    return False
            return True
        if args["now"]:
            args["date"]= None
            args["time"]= None
        if (not args["now"]) and all_None(args, ["date","time"]):
            choice= input_Yn(prompt="Use the current date and time?")
            if not choice:
                # Ask for date
                args["date"]= input_date_dmy(prompt="Enter the date for which to check for free rooms.")
                # Ask for time
                args["time"]= input_time_hhmm()
        if args["date"]:
            date_tuple= tuple_of_date_dmy(args["date"])
            if not date_tuple:
                raise RuntimeError(f"Invalid format for date string (should be DD/MM/YYYY): {args['date']}")
            args["day"], args["month"], args["year"]= date_tuple
            if args["year"] < 100:
                args["year"]+= 2000 #Y3K
            start_is_now= False
        if args["time"]:
            start_tt= tuple_of_time_hhmm(args["time"])
            if not start_tt:
                raise RuntimeError(f"Invalid format for time string (should be HH:MM): {args['time']}")
            start_is_now= False
        d= datetime.datetime.now()
        if not start_tt:
            start_tt= (d.hour, d.minute)
            print(f"Using current time {s_of_tt(start_tt)}")
        def set_if_None(args, defaults):
            for k,v in defaults.items():
                if not k in args or args[k] is None:
                    args[k]= v
        if not all_None(args, ["day", "month", "year"]):
            start_is_now= False
        set_if_None(args, {"day":d.day,
                           "month":d.month,
                           "year":d.year})
        excluded= set()
        if args["excluded_rooms"]:
            excluded= set(args["excluded_rooms"])
        # Done processing args
        s= open_session(args["user"], args["password"])
        find_and_display_free_rooms(s, args["year"], args["month"], args["day"], start_tt,
                                    excluded=excluded, duration=args["duration"],
                                    max_delay=args["max_delay"], start_is_now=start_is_now)
        show_message("Done.")
    finally:
        if s is not None:
            s.close()

if __name__ == '__main__' :
    display_errors(main)


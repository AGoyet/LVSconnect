#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scripting for an Axess website.

Cecks for student's attendance for a given test or date.
"""

from lvs_module import *

from bs4 import BeautifulSoup

# Use website names instead of english meaning as it makes it easier to compare with network trace.
add_url("attendance_choixClasseEleveStrater", '/vsn.main/absence/choixClasseEleveStrater')
add_url("attendance_choixClasseEleve", '/vsn.main/absence/choixClasseEleve')
add_url("attendance_calendrierAbsenceEleve", '/vsn.main/absence/calendrierAbsenceEleve')
add_url("attendance_calendrierEleve", '/vsn.main/absence/calendrierEleve')
add_url("attendance_calendrierClasse", '/vsn.main/absence/calendrierAbsenceClasse')
def all_indices(L, elem):
    indices= []
    start=0
    while True:
        try:
            i= L.index(elem, start)
            indices.append(i)
            start= i+1
        except ValueError:
            break
    return indices

def get_lsl_appr_cols_and_discs(csv_fname):
    rows= get_csv_rows(csv_fname)
    if len(rows) < 1:
        raise RuntimeError("Empty csv file")
    if len(rows) < 2:
        raise RuntimeError("Unexpected csv file format (no second line with test descriptions)")
    indices= all_indices(rows[1], lsl_sub_header)
    if not indices:
        raise RuntimeError(f"Error: CSV file must contain columns with the name of the discipline in the first cell and the text\"{lsl_sub_header}\" in the second cell.")
    return { rows[0][i] : i for i in indices }

# returns dict of group_name : group_id
def mandatory_get_attendance_classgroups(s):
    # These requests (r1 to r3) are mandatory as they redirects through a "/vsn.main/main/externalOpen"
    # with an "extautolog" encrypted parameter.
    # Without it the important request (in get_attendance_student) fails with 500.
    r1= s.post("https://lyceepaullapie92.la-vie-scolaire.fr/vsn.main/WSMenu/getModuleUrl?mod=ABSENCES&minuteEcartGMTClient=-120")
    r1.raise_for_status()
    r2= s.get(json.loads(r1.text)["location"]) # redirects
    r2.raise_for_status()
    r3= s.get("https://lyceepaullapie92.la-vie-scolaire.fr/vsn.main/absence/absenceStart?actionEnd=calendrierAbsenceEleve&type=absence&idEleve=&accesDeMenu=true") # also mandatory
    r3.raise_for_status()
    # End of mandatory requests. No response is used (but auth is done).
    r= s.get(get_url("attendance_choixClasseEleveStrater"))
    r.raise_for_status()
    soup= BeautifulSoup(r.text, 'html.parser')
    elems= soup.find_all(id="chooseMenuForm")
    if not elems:
        raise RuntimeError("Unexpected format for attendance index on website")
    e= elems[0]
    options= e.find_all("option")
    d= { option.text : option["value"] for option in e.find_all("option") if option["value"] != "null" }
    return d

# returns a dict of student_name : (classgroup_id, student_id)
def get_all_students_ids(s, classgroup_id):
    student_ids= {}
    data= {"idClasse": classgroup_id,
           "clean_resteList":"true",
           "actionEnd":"calendrierAbsenceEleve",
           "controllerEnd":""}
    r= s.post(get_url("attendance_choixClasseEleve"), data=data)
    r.raise_for_status()
    soup= BeautifulSoup(r.text, 'html.parser')
    selects= soup.find_all("select", id="idEleve")
    if len(selects) != 1:
        raise RuntimeError("Unexpected format for attendance initial display on website")
    options= selects[0].find_all("option")
    for option in options:
        if option["value"] == "null":
            continue
        student_name= option.text
        student_id= option["value"]
        student_ids[student_name]= (classgroup_id, student_id)
    return student_ids

def get_all_students_class_and_ids(s, classgroups):
    student_class_and_ids= {}
    for classgroup_id in classgroups.values():
        student_class_and_ids.update(get_all_students_ids(s, classgroup_id))
    return student_class_and_ids

# Not used.
# Works by requesting the calendar view for a whole classgroup; unfortunately this only gives the last month.
# (Would need to iterate over months by requesting "prev month" each time.)
def get_attendance_for_last_month(attendance_dict, s, classgroup_id):
    student_names_of_ids= {}
    attendance_dict= {}
    # Re compilation done here for clarity over "speed".
    # DD/MM/YYYY
    date_re= re.compile(r"\d\d/\d\d/\d\d\d\d")
    # One non whitespace char, then anything on the same line, ending with a non whitespace. 
    # Example: 'De 10h10 à 11h00 - Maladie sans certif/rdv med'
    motive_re= re.compile(r"\S.*\S")    
    data= {"idClasse": classgroup_id,
           "clean_resteList":"true",
           "actionEnd":"calendrierAbsenceEleve",
           "controllerEnd":""}
    r= s.post(get_url("attendance_calendrierClasse"), data=data)
    r.raise_for_status()
    soup= BeautifulSoup(r.text, 'html.parser')
    tables= soup.find_all("table", class_="tabCalendrierEleve")
    if len(tables) != 1:
        raise RuntimeError("Unexpected format of student calendar view (table tag)")
    tbodys= tables.find_all("tbody")
    if len(tbodys) != 1:
        raise RuntimeError("Unexpected format of student calendar view (tbody tag)")
    trs= tbodys.find_all("tr")
    for tr in trs:
        student_name= " ".join(tr.find("th").text.split())
        spans= tr.find_all("span", class_="corp")
        for span in spans :
            m= re.search(date_re, span.text)
            if m is None:
                raise RuntimeError("Unexpected format of student calendar view (couldn't find date in cell)")
            date= m.group()
            rest= span.text[m.span()[1]:]
            motive_list= re.findall(motive_re, rest)
            # Update dict
            if not date in attendance_dict:
                attendance_dict[date]= {}
            attendance_dict[date][student_name]= motive_list
    return attendance_dict

def get_student_attendance(s, classgroup_id, student_id):
    data= {"idClasse": classgroup_id,
           "idEleve":student_id,
           "clean_resteList":"", # ""
           "actionEnd":"calendrierAbsenceEleve",
           "controllerEnd":""}
    # This request redirects (302 into a get with a jwtClaim data)    
    r= s.post(get_url("attendance_calendrierAbsenceEleve"), data=data)
    r.raise_for_status()
    soup= BeautifulSoup(r.text, 'html.parser')   
    return soup

# Updates the attendance_dict
def parse_student_calendar(attendance_dict, soup, student_name):
    # Re compilation done here for clarity over "speed".
    # DD/MM/YYYY
    date_re= re.compile(r"\d\d/\d\d/\d\d\d\d")
    # One non whitespace char, then anything on the same line, ending with a non whitespace. 
    # Example: 'De 10h10 à 11h00 - Maladie sans certif/rdv med'
    motive_re= re.compile(r"\S.*\S")
    tables= soup.find_all("table", class_="tabCalendrierEleve")
    if len(tables) != 1:
        raise RuntimeError("Unexpected format of student calendar view (no table tag found)")
    spans= tables[0].find_all("span", class_="corp")
    for span in spans :
        m= re.search(date_re, span.text)
        if m is None:
            raise RuntimeError("Unexpected format of student calendar view (couldn't find date in cell)")
        date= m.group()
        rest= span.text[m.span()[1]:]
        motive_list= re.findall(motive_re, rest)
        # Update dict
        if not date in attendance_dict:
            attendance_dict[date]= {}
        attendance_dict[date][student_name]= motive_list

def should_check_grade(grade_s):
    if not is_csv_number(grade_s):
        return True
    try:
        f= float(grade_s)
        return f == 0
    except ValueError:
        return True

def get_student_names_to_check_from_csv(csv_fname, test_name= None):
    student_names= []
    grades_dict= {}
    rows= get_csv_rows(csv_fname)
    if len(rows[0]) < 2:
        raise RuntimeError("CSV file does not contain any evaluations (tests).")
    if test_name is None:
        test_names= [ cell for cell in rows[0][1:] if cell.strip() != "" ]
        if not test_names:
            raise RuntimeError("CSV file does not contain any evaluations (tests).")
        test_name= input_pick_option(test_names, prompt= "Evaluation (test) name not provided. Choose one:")
    test_col= -1
    for i in range(1, len(rows[0])):
        if rows[0][i] == test_name:
            if test_col != -1:
                raise RuntimeError(f"Evaluation {test_name} appears more than once in CSV file.")
            test_col= i
    if test_col == -1:
        raise RuntimeError(f"Evaluation {test_name} does not appear in CSV file.")
    student_rows= student_rows_of_csv_rows(rows)
    for row in student_rows:
        student_name= row[0]
        grade= row[test_col]
        grades_dict[student_name]= grade
        if should_check_grade(grade):
            student_names.append(student_name)
    return student_names, grades_dict, test_name

def get_student_names_to_check_from_json(s, json_grades, test_id):
    student_names_to_check= []
    grades_dict= {}
    grades_website= grades_dict_of_json(json_grades)
    student_names_of_ids= get_student_names_of_ids(json_grades)
    for student_id, student_name in student_names_of_ids.items():
        key= (test_id, student_id)
        if not key in grades_website:
            raise RuntimeError(f"Unexpected website response (valid student id has no grade for a valid test id ({key}))")
        grade= grades_website[key]
        grades_dict[student_name]= grade
        if should_check_grade(grade):
            student_names_to_check.append(student_name)
    return student_names_to_check, grades_dict

def convert_date_from_ymd(date_ymd):
    return re.sub(r"^(\d\d\d\d)-(\d\d)-(\d\d)$", r"\3/\2/\1", date_ymd)

# Uses a combination of requests, CSV, and interactive user input to get params.
# Returns student_names_to_check, grades_dict, test_date, group_name, test_name
# student_names_to_check and grades_dict are returned as None if do_all_students was True
def collect_all_necessary_params(s, classgroups, group_name=None, test_name=None, csv_fname=None, do_all_students=False, trimester=None, test_date=None):
    student_names_to_check= None
    grades_dict= None
    # Get group name
    json_grades= None
    json_groups= None
    json_groups= get_groups(s)
    service_id_of_group_name= get_services(json_groups)
    if group_name is None:
        if csv_fname is not None:
            get_group_name_from_csv(csv_fname)
        else:
            group_name= input_pick_option(service_id_of_group_name.keys(),
                                          prompt="Group name not provided. Choose one:")
    # Get test name
    if (not test_name) and (not do_all_students):
        # Maybe the user actually wanted to get all students from the class?
        # We need to know now to let user pick between classes instead of groups (there are more groups).
        choice= input_Yn('Select evaluation form a list? (Choosing "No" will get attendance from all students from a group.)')
        do_all_students= not choice
    if do_all_students:
        if not test_date:
            print("No date provided.")
            test_date= input_date_dmy(prompt="Please input the date for which to check attendance.")
            if not test_date:
                raise RuntimeError("No date provided. Aborting.")
        service_id= service_id_of_group_name[group_name]
        json_grades= get_grades(s, service_id, 1) # It should be ok to get grades from trimester=1 every time.
        student_names_to_check= list(get_student_names_of_ids(json_grades).values())
    else:
        # Since we don't do all students, we need to know which test to use;
        service_id= service_id_of_group_name[group_name]
        grades_dict= None
        # Get test_name and student_names_to_check. At this point test_name can be None
        if csv_fname:
            # Will get test_name from csv if needed
            r= get_student_names_to_check_from_csv(csv_fname, test_name=test_name)
            student_names_to_check, grades_dict, test_name= r
        if (not student_names_to_check) or (not grades_dict) or (not test_date):
            if trimester is None:
                if json_groups is None:
                    json_groups= get_groups(s)
                trimester= guess_trimester_from_date()
                choice= input_Yn(f"No trimester provided. Guessed trimester {trimester} based on current date. Is this correct?")
                if not choice:
                    choice2= input_pick_option(["Trimester 1", "Trimester 2", "Trimester 3"], prompt="Choose trimester:")
                    trimester= int(choice2[-1:])
            # We have service_id
            json_grades= get_grades(s, service_id, trimester)
            test_id_of_name= {devoir["titre"]:devoir["id"] for devoir in json_grades["evaluations"]}
            if not test_name:
                options= test_id_of_name.keys()
                if not options:
                    raise RuntimeError("No evaluation (test) for that group.")
                test_name= input_pick_option(options,
                                             prompt="Evaluation (test) name not provided. Choose one:")
            if not test_name in test_id_of_name:
                raise RuntimeError(f"Provided evaluation (test) name {test_name} not found on website. If the name is correct, either create it on the website or provide a CSV file that includes this evaluation name.")
            test_id= test_id_of_name[test_name]
            # We now have test_name and test_id
            if (not student_names_to_check) or (not grades_dict):
                student_names_to_check, grades_dict= get_student_names_to_check_from_json(s, json_grades, test_id)
            if not test_date:
                date_ymd= get_date_from_json_ymd(json_grades, test_id)
                test_date= convert_date_from_ymd(date_ymd)
                choice= input_Yn(f"Evaluation (test) date not provided. Guessed date {test_date} from website. Is this correct?")
                if not choice:
                    test_date= input_date_dmy(prompt="Please input the date for which to check attendance.")
    return student_names_to_check, grades_dict, test_date, group_name, test_name

# Returns (attendance_dict, students_not_found, test_date)
# attendance_dict is a dict of date_DD/MM/YYYY : dict of student_name : motive_list
# students_not_found is a set of student names
# test_date is returned because of the arg processing 
def get_attendances(s, classgroups, student_names_to_check):
    attendance_dict= {}
    students_not_found= []
    student_class_and_ids= get_all_students_class_and_ids(s, classgroups)
    for student_name in student_names_to_check:
        if not student_name in student_class_and_ids:
            students_not_found.append(student_name)
        else:
            classgroup_id, student_id= student_class_and_ids[student_name]            
            print("Reading calendar for student", student_name)
            soup= get_student_attendance(s, classgroup_id, student_id)
            parse_student_calendar(attendance_dict, soup, student_name)
    if students_not_found:
        print(f"Warning: The following students were not on the attendance lists: {nicer_str(students_not_found)}")
    return (attendance_dict, students_not_found)

def output_attendance_sub(attendance_dict, test_date, group_name, test_name,
                          students_not_found=None,
                          student_names_to_check=None,
                          grades_dict=None):
    test_name_output= ""
    if test_name:
        test_name_output= ", " + test_name
    output_s= f"**** {test_date} ({group_name}{test_name_output}):\n\n"
    indent= 4
    indent_s= " "*indent
    if not test_date in attendance_dict:
        output_s+= "Aucunes"
        return output_s
    if students_not_found is None:
        students_not_found= set()
    day= attendance_dict[test_date]
    if student_names_to_check is None:
        student_names= list(day.keys())
    else:
        student_names= student_names_to_check.copy()
    student_names.sort()
    for student_name in student_names:
        if grades_dict is not None:
            assert student_name in grades_dict
            grade= comma_number_str(grades_dict[student_name])
            output_s+= f"{student_name} (note: \"{grade}\"): \n"
        else:
            output_s+= f"{student_name}: \n"
        if student_name in day:
            for motive in day[student_name]:
                output_s+= indent_s + motive + "\n"
            if len(day[student_name]) > 0: # Should be true with expected format
                output_s+= "\n"
        else:
            if student_name in students_not_found:
                output_s+= indent_s + "Pas de calendrier d'absences pour cet élève\n"
    return output_s

def output_attendance(attendance_dict, test_date, group_name, test_name,
                      students_not_found=None,
                      student_names_to_check=None,
                      grades_dict=None,
                      output_file=None):
    output_s= output_attendance_sub(attendance_dict, test_date, group_name, test_name,
                                    students_not_found= students_not_found,
                                    student_names_to_check=student_names_to_check,
                                    grades_dict=grades_dict)
    if output_file is None or output_file == "":
        print("\n" + output_s) # Leave empty line before and after in stdout for readability.
    if output_file is None:        
        choice= input_yN(prompt="The output is being displayed. Save it to a file?")
        if choice:
            output_file= input_save_file("Chose a file to save the output:",
                                         filetypes=[("Text files", ".txt"), ("all files", "*")],
                                         defaultextension=".txt")
    if output_file is not None:
        if output_file == "":
            print("Empty filename given for output file, skipping.")
        print(f"Writing output to {output_file}")
        try:
            f= open(output_file, "w")
            f.write(output_s)
            f.close()
        except Exception as e:
            print(f"Error: Couldn't write to file {str(e)}.")
            print("Falling back to standard output:")
            print("\n", output_s) # Leave empty line before and after in stdout for readability.

def main():
    try:
        s= None
        arg_descs= [
            (('test_date',), {'metavar':'DATE', 'nargs':"?",
                                'help':'The date for which to check attendance. Format is DD/MM/YYYY.'}),
            (('-f', '--csv_file'), {'metavar':'FILE', 'dest':'csv_fname', 'nargs':"?",
                                    'help':'This should be a CSV file generated by the website. If provided, group name and trimester can be omitted.'}),
            (('-a', '--all-students'), {'dest':'do_all_students', 'action':'store_true',
                                        'help':'Check attendance for all students in a group. In this case, the evaluation name can be omitted.'}),
            (('-e', '--evaluation'), {'dest': 'test_name', 'metavar':'EVAL',
                                      'help':'The name of the evaluation (test}) for which to check attendance. If given, only students who do not have a numeric non zero grade will be checked. For example, an empty cell or "ABS" will be checked. Grades are taken from the CSV file if provided, or from the website.'}),
             (('-o', '--output-file'), {'dest': 'output_file',
                                        'help':'Write attendance to this file instead of standard output.'})
             ]
        shared_args=["group", "trimester"]
        # Set dont_process="csv_fname" because we do more than the default processing here.
        args= lvs_get_args(arg_descs=arg_descs, shared_args= shared_args, description='Checks for student\'s attendance on an axess website. Will interactively prompt for most arguments if not given.', prompt_csv=False, silent_csv= True, confirm_csv= True)
        s= open_session(args["user"], args["password"])
        classgroups= mandatory_get_attendance_classgroups(s)
        params= collect_all_necessary_params(s, classgroups,
                                             group_name= args["group_name"],
                                             test_name= args["test_name"],
                                             csv_fname= args["csv_fname"],
                                             do_all_students= args["do_all_students"],
                                             trimester= args["trimester"],
                                             test_date= args["test_date"])
        student_names_to_check, grades_dict, test_date, group_name, test_name = params
        attendance_dict, students_not_found= get_attendances(s, classgroups, student_names_to_check)
        output_attendance(attendance_dict, test_date, group_name, test_name,
                          students_not_found=students_not_found,
                          output_file= args["output_file"],
                          student_names_to_check=student_names_to_check,
                          grades_dict= grades_dict)
        print("Done.")
    finally:
        if s is not None:
            s.close()
        
if __name__ == '__main__' :
    display_errors(main)

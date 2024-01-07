#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Utilities built on top of pronotepy. The pronotepy module is not imported if a pronote backend is not detected.

Provides reimplementations for the pronote backend of functions from the lvs modules (through the @reimpl decorator).

The "initialize" function must be run before any calls to the reimplemented functions. If not (or if the backend is not detected or set to be pronote), the base functions will be run.

To make it transparent to the calling module, the functions take the same argument in the same order. However, the content (and often type) of those arguments are different. In particular:
- The LVS backend uses a request.session called "s". In pronote this will actually be a pronote_py.Client object, called "client" by the pronote version.  
- The LVS backend uses "service_id" value. In pronote this will be a "group_data" json object.
"""

import logging
#logging.basicConfig()
logging.basicConfig(level=logging.DEBUG)

import re
import functools

# Should not be set manualy
__is_pronote_backend__= None

# See functions cache_possible_recipients and clear_possible_recipients_cache
cached_possible_recipient_data_list= None

# Should not be called manualy
def set_is_pronote_backend(value):
    global __is_pronote_backend__
    __is_pronote_backend__= value
    if __is_pronote_backend__:
        global pronotepy
        import pronotepy

# Must be called first
def initialize(login_url=None, is_pronote_backend=None):
    if login_url is None:
        assert not is_pronote_backend is None
        set_is_pronote_backend(is_pronote_backend)
    else:
        # Keep the validation regex simple for future proofing
        login_url_regex= r"^https://[^/]+\.[^/]+/pronote/.*"
        is_valid_url= bool(re.match(login_url_regex, login_url))
        if is_pronote_backend and login_url and not is_valid_url:
            raise RuntimeError("Incorrect url provided, aborting")            
        set_is_pronote_backend(is_valid_url)

# Use this decorator in lvs modules for functions reimplemented here.
def reimplemented(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # if None or False, no reimplementation occurs
        if __is_pronote_backend__ != True:
            return func(*args, **kwargs)
        else:
            return globals()[func.__name__](*args, **kwargs)
    return wrapper

# Use this decorator in lvs modules for functions that should not be called in the case of a pronote backend.
def notimplemented(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # if None or False, proceed as normal
        if __is_pronote_backend__ != True:
            return func(*args, **kwargs)
        else:
            raise RuntimeError(f"{func.__name__}: not implemented for pronote")
    return wrapper

# reimplementation
def set_base_url(url):
    # Nothing to do, the client gets the login url in open_session then remembers it.
    pass

# reimplementation
def grade_parse(grade):
    return pronotepy.Util.grade_parse(grade)

# Reverse of grade_parse from pronotepy.dataClasses.Util
def grade_compose(string):
    grade_translate= pronotepy.dataClasses.Util.grade_translate
    if string in grade_translate:
        return "|" + str(grade_translate.index(string))
    else:
        # The replace is here in case of a spreadsheet conversion.
        return string.replace(".",",") 

trimester_regex= r"Trimestre (?:1|2|3)"

def donnees(r):
    return r["donneesSec"]["donnees"]

def get_response_data(r, key=None):
    d= r["donneesSec"]["donnees"]
    keys= list(d.keys())
    if not key:
        assert len(keys) == 1
        key= keys[0]
    return d[key]["V"]

def find_in_data(data_list, key=None, substr=False, exactly_one=False, **kwargs):
    output = []
    for data in data_list:
        for attr in kwargs: 
            if not attr in data:
                break
            # test substr, but only for string keys
            if substr and type(kwargs[attr]) == str:
                if not kwargs[attr] in data[attr]:
                    break
            else:
                if kwargs[attr] != data[attr]:
                    break
        else:
            output.append(data)
    if exactly_one:
        assert len(output) == 1
        return output[0]
    return output

# Does not modify args. Creates shallow copy.
def filter_dict(d, keys):
    return { k:d[k] for k in keys }

# Does not modify args. Creates shallow copy.
def union_dict(d1, d2):
    d= d1.copy()
    d.update(d2)
    return d

# reimplementation
# Returns a pronotpy.Client object (instead of a request.session object)
def open_session(user, password, login_url):
    try:
        client= pronotepy.Client(login_url, username=user, password=password)
    except Exception as e:
        raise RuntimeError(str(e))
    if not client.logged_in:
        raise RuntimeError("Authentification failure")
    return client

# reimplementation
def close_session(client):
    # client.post("SaisieDeconnexion", 8)
    client.communication.session.close()
    pass

def request_default_period(client):
    r= client.post("ListePeriodes", 23)
    period_data= get_response_data(r, key="periodeParDefaut")
    return period_data

def request_period_from_trimester_nb(client, trimester_nb):
    r= client.post("ListePeriodes", 23)
    trimester_key= f"Trimestre {trimester_nb}"
    period_data= find_in_data(get_response_data(r, key= "listePeriodes"),
                              L=trimester_key, exactly_one=True)
    return period_data

def get_user_teacher(client):
    teacher_data= donnees(client.parametres_utilisateur)["ressource"]
    return teacher_data

# reimplementation
def get_groups(client):
    r= client.post("listeClassesGroupes", 23)
    group_data_list= get_response_data(r)
    return group_data_list

request_group_list= get_groups

# reimplementation
def trimester_regex():
    return r"Trimestre (?:1|2|3)"

def request_group_service(client, group_data, period_data=None, teacher_data=None):
    if teacher_data is None:
        teacher_data= get_user_teacher(client)
    if period_data is None:
        period_data= request_default_period(client)
    # Get service for that specific group
    r= client.post("ListeServices", 23, {'Eleve':None, 'Pilier':None, 'Periode':period_data, 'Ressource':group_data,
                                         'Professeur': filter_dict(teacher_data, ["G","L","N"])} )
    service_data= get_response_data(r, "services")
    assert len(service_data) == 1
    service_data= service_data[0]
    return service_data

# For pronote it is the group_data that will be necessary instead of service_id
# reimplementation
def get_service_id(group_name, group_data_list):
    group_data= find_in_data(group_data_list, G=2, L=group_name, exactly_one=True)
    return group_data

# reimplementation
def get_grades(client, group_data, trimester_nb):
    period_data= request_period_from_trimester_nb(client, trimester_nb)
    teacher_data= get_user_teacher(client)
    service_data= request_group_service(client, group_data, period_data=period_data, teacher_data=teacher_data)
    r= client.post("PageNotes", 23, {'periode': union_dict(period_data, {"G":2}),
                                     'ressource': filter_dict(group_data, ["G","N"]),
                                     'service': filter_dict(service_data, ["N"])}
                   )
    grades_data= donnees(r)
    return grades_data

# reimplementation
def get_apprs(client, group_data, trimester_nb):
    period_data= request_period_from_trimester_nb(client, trimester_nb)
    teacher_data= get_user_teacher(client)
    service_data= request_group_service(client, group_data, period_data=period_data, teacher_data=teacher_data)
    r= client.post("PageApprBulletin", 25, {'periode': union_dict(period_data, {"G":2}),
                                     'ressource': filter_dict(group_data, ["G","N"]),
                                     'service': filter_dict(service_data, ["L", "N"])}
                   )
    apprs_data= donnees(r)
    return apprs_data

# returns a dict of (evaluation_id, student_id) : grade, where grade is a str
# reimplementation
def grades_dict_of_json(grades_data):
    grades= {}
    for evaluation in grades_data["listeDevoirs"]["V"]:
        evaluation_id= evaluation["N"]
        for student in evaluation["listeEleves"]["V"]:
            student_id= student["N"]
            grade= grade_parse(student["Note"]["V"])
            grades[(evaluation_id, student_id)]= grade
    return grades

# returns a dict of student_id : appr_data
def get_appr_of_student_ids(apprs_data):
    appr_data_of_student_ids= {}
    for line in apprs_data["listeLignes"]["V"]:
        student= line["eleve"]["V"]
        student_id= student["N"]
        # If there is no appreciation yet for that student, the appA dict has no "L" key.
        appr_data= line["appA"]["V"]
        appr_data_of_student_ids[student_id]= appr_data
    return appr_data_of_student_ids

# returns a dict of student_id : appr
# reimplementation
def appr_dict_of_json(apprs_data):
    appr_of_student_ids= get_appr_of_student_ids(apprs_data)
    apprs= {}
    for student_id, appr_data in appr_of_student_ids.items():
        appr= appr_data.get("L","")
        apprs[student_id]= appr
    return apprs

# returns a dict of student_id : student_data
def get_student_of_ids(grades_data):
    d= {}
    for student in grades_data["listeEleves"]["V"]:
        student_id= student["N"]
        d[student_id]= student
    return d

# This is "class", not "group". Each student belongs to a single class.
# returns a dict of student_id : class_data
def get_class_of_student_ids(grades_data):
    student_data_of_ids= get_student_of_ids(grades_data)
    d= {}
    for student_id, student_data in student_data_of_ids.items():
        class_data= student_data["classe"]["V"]
        d[student_id]= class_data
    return d

# returns a dict of student_id : student_name
# reimplementation
def get_student_names_of_ids(grades_data):
    student_data_of_ids= get_student_of_ids(grades_data)
    d= {}
    for student_id, student_data in student_data_of_ids.items():
        d[student_id]= student_data["L"]
    return d

def create_grade_csv_file(group_data, period_data, teacher_data):
    period_name= period_data["L"]
    group_name= group_data["L"]
    service_data= request_group_service(group_data)
    grades_data= request_grades(group_data, period_data=period_data, service_data=service_data)

    student_names_of_ids= { d["N"]:d["L"] for d in grades_data["listeEleves"]["V"] }
    student_names= sorted(list(student_names_of_ids.values()))
    nb_students= len(student_names)

    csv_first_row= [group_name]
    csv_second_row= [f"{nb_students} élèves"]

    for evaluation in grades_data["listeDevoirs"]["V"]:
        title= evaluation["commentaire"]
        bareme= csv_number_of_s(evaluation["bareme"]["V"])
        coefficient= csv_number_of_s(evaluation["coefficient"]["V"])
        date= evaluation["date"]["V"]
        desc= f"/{bareme} - Coef : {coefficient}"
        csv_first_row.append(title)
        csv_second_row.append(desc)

    csv_rows= [csv_first_row, csv_second_row]

    row_i_of_names= {}

    for student_name in student_names:
        row= [""] * len(csv_first_row)
        row[0]= student_name
        csv_rows.append(row)
        row_i_of_names[student_name]= len(csv_rows) - 1

    evaluation_col= 0
    for evaluation in grades_data["listeDevoirs"]["V"]:
        evaluation_col+= 1
        for student in evaluation["listeEleves"]["V"]:
            grade= Util.grade_parse(student["Note"]["V"])
            if grade:
                csv_rows[row_i_of_names[student["L"]]][evaluation_col]= csv_number_of_s(grade)

    csv_fname= f"{group_name}_{period_name}.csv"
    with open(csv_fname, "w") as csv_file:
        csv_writer= csv.writer(csv_file, delimiter=';', quotechar='"', quoting=csv.QUOTE_ALL)
        csv_writer.writerows(csv_rows)


# Without only_this_group_name, does all groups
def create_grade_csv_files(only_this_group_name= None):

    period_data= request_default_period(client)
    teacher_data= get_user_teacher(client)
    group_data_list= request_group_list(client)
    
    for group_data in group_data_list:
        # Only do groups, not classes
        if group_data["G"] != 2:
            continue
        if only_this_group_name and group_data["L"] != only_this_group_name:
            continue
        create_grade_csv_file(group_data, period_data, teacher_data)


def send_new_grades(new_grades_dict, evaluation_data=None, evaluation_name=None, grades_data=None, group_data=None, group_data_list=None, group_name=None):
    # Get all necessary data 
    if grades_data is None:
        if group_data is None:
            if group_data_list is None:
                group_data_list= request_group_list(client)
            assert group_name
            group_data= find_in_data(group_data_list, G=2, L=group_name, exactly_one=True)
        grades_data= request_grades(group_data)
    if evaluation_data is None:
        assert evaluation_name
        evaluation_data= find_in_data(grades_data["listeDevoirs"]["V"],
                                      commentaire=evaluation_name, exactly_one=True)
    # Prepare post data
    new_students_data= []
    for k in new_grades:
        student_name= k
        student_data= find_in_data(grades_data["listeEleves"]["V"],
                                   L=student_name, exactly_one=True)
        new_grade= new_grades_dict[k]
        new_grade= new_grade.replace(".",",")
        new_grade_data= { "_T":10, "V": Util.grade_compose(new_grade) }
        new_student_data= union_dict(filter_dict(student_data, "NL"), {"note":new_grade_data})
        new_students_data.append(new_student_data)

    post_data= {"listeDevoirs":[{"N": evaluation_data["N"],
                                 "listeEleves":new_students_data
                                 }]}
    # Do post request
    r= client.post("SaisieNotesUnitaire", 23, post_data)

# returns a dict of evaluation_name : (col, max_grade, coefficient, evaluation_id)    
def get_evaluation_website_descs(grades_data):
    website_descs= {}
    for evaluation in grades_data["listeDevoirs"]["V"]:
        evaluation_name= evaluation["commentaire"]
        max_grade= evaluation["bareme"]["V"]
        coefficient= evaluation["coefficient"]["V"]
        evaluation_id= evaluation["N"]
        date= evaluation["date"]["V"]
        website_descs[evaluation_name]= (max_grade, coefficient, evaluation_id)
    return website_descs

# group_data is not used
# reimplementation
def send_grades_dopost(client, trimester, grades_data, group_data, new_grades_dict):
    # Prepare post data
    new_evaluation_data_list= []
    for evaluation_id in new_grades_dict:
        new_student_data_list= []
        for student_id in new_grades_dict[evaluation_id]:
            student_data= find_in_data(grades_data["listeEleves"]["V"],
                                       N=student_id, exactly_one=True)
            new_grade= grade_compose(new_grades_dict[evaluation_id][student_id])
            new_grade_data= { "_T":10, "V": new_grade }
            new_student_data= union_dict(filter_dict(student_data, "NL"), {"note":new_grade_data})
            new_student_data_list.append(new_student_data)
        new_evaluation_data= {"N": evaluation_id, "listeEleves": new_student_data_list}
        new_evaluation_data_list.append(new_evaluation_data)
    post_data= {"listeDevoirs": new_evaluation_data_list}
    # Do post request
    r= client.post("SaisieNotesUnitaire", 23, post_data)
    
# reimplementation
def send_apprs_dopost(client, trimester, student_names, grades_data, apprs_data,
                      group_data, new_apprs_dict):
    period_data= request_period_from_trimester_nb(client, trimester)
    student_data_of_ids= get_student_of_ids(grades_data)
    class_data_of_student_ids= get_class_of_student_ids(grades_data)
    appr_of_student_ids= get_appr_of_student_ids(apprs_data)
    service_data= request_group_service(client, group_data)
    # Used by the web client as id for newly created apprs. Decremented by 2 each time
    new_appr_sequence_number= -1001
    for student_id, appr in new_apprs_dict.items():
        appr_id= appr_of_student_ids[student_id].get("N", None)
        E_value= 2
        no_web_appr= appr_id is None
        if no_web_appr:
            appr_id= new_appr_sequence_number
            E_value= 1
            new_appr_sequence_number -= 2
        appr_data= {"E":E_value, "G":1, "L":appr, "N": appr_id}
        class_data= class_data_of_student_ids[student_id]
        student_data= student_data_of_ids[student_id]
        post_data= {"appreciation": appr_data,
                    # "G":1 for a "class" (?), "G":? for a "group"
                    "classe": union_dict( {"G":1}, filter_dict(class_data, "LN") ),
                    "eleve": union_dict( {"G":4}, filter_dict(student_data, "LN") ),
                    "periode": filter_dict(period_data, "GLN"),
                    "service": filter_dict(service_data, "LN"),
                    "typeGenreAppreciation":0}
        student_name= student_names[student_id]
        print(f"Uploading {student_name}...")
        # Do post request
        r= client.post("SaisieAppreciation", 25, post_data)
        from pprint import pprint
        if "_messagesErreur_" in str(r):
            print("Error:")
            pprint(post_data)
            print("response:")
            pprint(r)
            print("debug stop")
            return
        if no_web_appr:
            try:
                appr_id= r["donneesSec"]["RapportSaisie"]["appreciation"]["V"]["N"]
            except KeyError:
                print("Error creating new appreciation")
                pprint(r)
                return
            E_value= 2
            appr_data= {"E":E_value, "G":1, "L": appr, "N": appr_id}
            post_data["appreciation"]= appr_data
            r= client.post("SaisieAppreciation", 25, post_data)            
            if "_messagesErreur_" in str(r):
                print("Error:")
                pprint(post_data)
                print("response:")
                pprint(r)
                print("debug stop")
                return

# Slow. Consider using function cached_possible_recipients
def get_possible_recipients(client, recipient_types=None):
    V_of_recipient_type= {"teacher": "[3]",
                          "staff": "[34]",
                          "student": "[4]",
                          "parent": "[5]"}
    if recipient_types is None:
        recipient_types= ["teacher","staff"]
    assert type(recipient_types) == list
    possible_recipient_data_list= []
    for recipient_type in recipient_types:
        post_data= {"genres":{"_T":26,"V":V_of_recipient_type[recipient_type]},
                    "pourMessagerie":True,"sansFiltreSurEleve":True,"avecFonctionPersonnel":True}
        r= client.post("ListePublics", 131, post_data)
        possible_recipient_data_list.extend(get_response_data(r, "listePublics"))
    return possible_recipient_data_list


# Since get_possible_recipients is slow, it is useful to cache.
# BUT the cache becomes outdated after a few minutes.
# This should be used for a batch of queries, then cleared.
# reimplementation
def cache_possible_recipients(client, dest_types=None):
    global cached_possible_recipient_data_list
    cached_possible_recipient_data_list= get_possible_recipients(client, dest_types)

    
# reimplementation
def clear_possible_recipients_cache():
    global cached_possible_recipient_data_list
    cached_possible_recipient_data_list= None


def find_recipient(client, recipient_name, possible_recipient_data_list=None,
                   recipient_type=None, recipient_function=None,
                   **other_filters):
    G_of_recipient_type= {"teacher": 3,
                          "staff": 34,
                          "student": 4,
                          "parent": 5}
    if possible_recipient_data_list is None:
        if cached_possible_recipient_data_list:
            possible_recipient_data_list= cached_possible_recipient_data_list
        else:
            assert recipient_type
            possible_recipient_data_list= get_possible_recipients(client, recipient_types= [recipient_type])
    if recipient_type is None:
        raw_l= find_in_data(possible_recipient_data_list, substr=True, L=recipient_name,
                            **other_filters)
    else:
        raw_l= find_in_data(possible_recipient_data_list, substr=True, L=recipient_name,
                            G=G_of_recipient_type[recipient_type], **other_filters)
    if not recipient_function:
        l= raw_l
    else:
        l= []
        for data in raw_l:
            if ( not "fonction" in data ) or data["fonction"]["V"]["L"] != recipient_function:
                continue
            l.append(data)
    if not l :
        raise ValueError(f"Partial recipient name {recipient_name} not found in list")
    if len(l) > 1 :
        raise ValueError(f"Partial recipient name {recipient_name} matches mutliple recipients:" +"\n" + '\n'.join([r['L'] for r in l]))
    recipient_data= l[0]
    return recipient_data


# reimplementation
def get_mess_dest_json(client, dest_search_s, dest_type= "student"):
    recipient_data= find_recipient(client, dest_search_s, recipient_type=dest_type)
    return recipient_data


# Website generates html from text in a very specific (and terrible) way.
# reimplementation
def convert_to_terrible_html_message(text_s):
    html_s= ""
    for line in text_s.split("\n"):
        html_s+= '<div style="font-family: Arial; font-size: 13px;">'
        html_s+= line
        if not line.strip():
            html_s+= '&nbsp;'
        html_s+= '</div>'
    return html_s


# Starts discussion with ONE person
def new_discussion(client, subject, message, recipient_data=None, recipient_name=None,
                   possible_recipient_data_list=None):
    if recipient_data is None:
        assert recipient_name
        recipient_data= find_recipient(recipient_name, possible_recipient_data_list=possible_recipient_data_list)
    # Try to prevent multiple recipients
    assert "L" in recipient_data
    recipients= [recipient_data]
    recipients_post_data = [ filter_dict(r, "NGL") for r in recipients ]
    message_html= convert_to_terrible_html_message(message)
    post_data= {
        "objet": subject,
        "contenu": { "_T": 21, "V": message_html},
        "listeDestinataires": recipients_post_data,
    }
    r_json= client.post("SaisieMessage", 131, post_data)
    return r_json


# reimplementation
def send_message(client, dest_search_s, subject, message, dest_type="student", enseigne=None):
    if enseigne is None:
        recipient_data= find_recipient(client, dest_search_s, recipient_type=dest_type)        
    else:
        recipient_data= find_recipient(client, dest_search_s, recipient_type=dest_type,
                                       enseigne=enseigne)
    r_json= new_discussion(client, subject, message, recipient_data=recipient_data)
    # pronotepy does not let us acess r itself, only r_json, so we can't access r.status_code
    # However it will throw if there is an error (which we should catch somewhere else)
    return 0 # no error detected


# reimplementation
def send_student_line_as_discussion(subject, message, student_name, possible_recipient_sutdents):
    recipient_data= find_recipient(student_name, possible_recipient_sutdents, enseigne=True)
    new_discussion(subject, message, recipient_data=recipient_data)



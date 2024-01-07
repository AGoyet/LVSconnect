# -*- coding: utf-8 -*-
"""
Scripting for an Axess website.
"""

from guify import *
import pronote

import requests
import json
import csv
import base64
import os, sys
import datetime
import os.path
import re
import time
import getpass
import argparse
import appdirs
import functools

appname= "LVSconnect"
config_fname= appname + "_config.json"

# Will be read from config or input
base_url= ''

urls={}

@pronote.reimplemented
def set_base_url(url):
    global base_url
    m= re.match("^(https://[^/]+).*$", url)
    if not m:
        raise RuntimeError("Incorrect url provided, aborting")
    base_url= m.group(1)

def add_url(name, rel_url):
    global urls
    urls[name]= rel_url

def get_url(name):
    return base_url + urls[name]

# login
add_url("login", '/login')
add_url("connexion", '/vsn.main/WSAuth/connexion')

# messages
add_url("new_message", '/vsn.main/WSmessagerie/mails/new')
add_url("dest", '/vsn.main/WSmessagerie/destinataires')
add_url("dest_add", '/vsn.main/WSmessagerie/mails/{}/destinataires/a')
add_url("compose", '/vsn.main/WSmessagerie/mails/{}')
add_url("send", '/vsn.main/WSmessagerie/mails/{}/envoyer')
add_url("recus", '/vsn.main/WSmessagerie/avecpages/2/0')

# grades
add_url("get_groups", "/vsn.main/WSCompetences/loadServicesProf")
add_url("get_grades", "/vsn.main/WSCompetences/loadDevoirsNotesMoyennes")

def update_config_from_file(config_dict, fname, silent= False):
    try:
        ffname= os.path.abspath(fname)
        if not silent:
            print(f"Reading config file {ffname}")
        with open(ffname) as f:
            j= json.load(f)
            config_dict.update(j)
    except (json.decoder.JSONDecodeError, PermissionError) as e:
        print(f"Warning: error reading config file {ffname}:\n  {e}")

# Reads in order from install dir, to site config, to user config, to current dir
def get_config_dict_from_files():
    dirs= appdirs.AppDirs(appname, appauthor=False)
    # Read from left to right, updating config as it goes.
    config_locations= [ os.path.dirname(os.path.abspath(sys.argv[0])), # dir in which program file is located
                        dirs.site_config_dir,
                        dirs.user_config_dir,
                        os.path.abspath(os.curdir), # dir in which command is launched
                       ]
    config_dict= json.loads("{}")
    files_read= []
    for location in config_locations:
        ffname= os.path.join(location, config_fname)
        if os.path.isfile(ffname) and (not ffname in files_read):
            update_config_from_file(config_dict, ffname)
            files_read.append(ffname)
    return config_dict

def update_config_file(config_dict):
    dirs= appdirs.AppDirs(appname, appauthor=False)
    try:
        ffname= os.path.join(os.path.abspath(dirs.user_config_dir), config_fname)
        if os.path.isfile(ffname):
            d= {}
            update_config_from_file(d, ffname, silent=True)
            # config_dict has priority
            d.update(config_dict)
            config_dict= d
        else:
            os.makedirs(os.path.dirname(ffname), exist_ok=True)
        with open(ffname, "w") as f:
            json.dump(config_dict, f, indent=2)
    except PermissionError as e:
        print(f"Warning: error writing config file {ffname}:\n  {e}")

## We warp argparse to avoid duplicating code.

# Passed each as parser.add_argument(*a, **ka)
# First element MUST be a tuple
shared_arg_descs= [
    (('-t', '--trimester'), {'type': int, 'choices': [1,2,3], 'help':'Trimester. Must be 1, 2 or 3. Default is to guess from the csv file name or current date.'}),
    (('-g', '--group'), {'dest': 'group_name',
                            'help':'The name of the group (or class) of students for the evaluation. Default is to guess from the csv file content (top left cell).'}),
    (('-d', '--dry-run'), {'action':'store_true',
                            'help':'Do not upload anything to the website.'}),
    (('-u', '--user'), {'help':'The user for login. Without this option, the program will prompt for login info.'}),
    (('-p', '--password'), {'help':'The password for login. Without this option, the program will prompt for login info.'}),
    (('--login-url',), {'dest': 'login_url',
                       'help':'The login url of the website to connect to. If not provided, will look for a config file containing the login url, or will prompt for it.'}),
    (('-c', '--cli',), {'action':argparse.BooleanOptionalAction, 'help':'Command line interface (launch without graphical dialog).'})
    ]

def lvs_get_args(arg_descs=[], shared_args=[], description="", dont_process=[], required=[],
                 prompt_csv=True, silent_csv= False, confirm_csv= False):
    shared_args= set(shared_args)
    # Always included for all calling programs
    common_arg_names= ["user", "password", "login-url", "cli"]
    shared_args.update(common_arg_names)
    parser = argparse.ArgumentParser(description=description)
    arg_names= set()
    # Place shared args first
    for desc in shared_arg_descs:
        for arg_name in shared_args:
            if arg_name in desc[0] or "-" + arg_name in desc[0] or "--" + arg_name in desc[0]:
                parser.add_argument(*desc[0], **desc[1])
                arg_names.add(arg_name)
    # Non shared args second
    for desc in arg_descs:
        parser.add_argument(*desc[0], **desc[1])
        # From "--name" to "name"
        arg_name= desc[0][-1]
        arg_name= arg_name.split("-")[-1]
        arg_names.add(arg_name)
    config_dict= get_config_dict_from_files()
    # Actually parse args (get args from argv)
    # Args overwrite config file
    args= parser.parse_args().__dict__
    # Remove args with None value if we got a value for them in config
    args2= { k:v for (k,v) in args.items() if (not k in config_dict) or (not v is None) }
    args= {}
    args.update(config_dict)
    args.update(args2)
    # Process args (logic)
    def should_process(arg_name):
        return (arg_name in arg_names) and not (arg_name in dont_process)
    if should_process("cli"):
        if args["cli"]:
            guify_disable_gui()
    if should_process("dry-run"):
        if args["dry_run"] is None:
            args["dry_run"]= False
    if should_process("login-url"):
        if args["login_url"] is None:
            url= input("No url provided. Please type the url you use to login on the website,\nfor example \"https://exemple.la-vie-scolaire.fr/login\" or\n\"https://0123456a.index-education.net/pronote/professeur.html\"")
            if not url:
                raise RuntimeError("Empty url provided, aborting")
            args["login_url"]= url
        url= args["login_url"]
        url= url.strip(" /")
        if not url.startswith("https://"):
            raise RuntimeError("Incorrect url provided, aborting")
        print("Using login url " + url)
        if not "login_url" in config_dict:
            print("Writing login url to config file ")
            update_config_file({"login_url":url})
        args["login_url"]= url
        pronote.initialize(login_url=url)
    if should_process("csv_fname") or should_process("csv_file"):
        if args["csv_fname"] is None:
            args["csv_fname"]= get_csv_filename(prompt_if_notfound=prompt_csv,
                                                silent=silent_csv, confirm=confirm_csv)
            if not args["csv_fname"]:
                if "csv_fname" in required:
                    raise RuntimeError("Unable to find or guess CSV file.")
                else:
                    args["csv_fname"]= None
    if should_process("group"):
        if args["group_name"] is None:
            if args.get("csv_fname"):
                args["group_name"]= get_group_name_from_csv(args["csv_fname"])
    if should_process("trimester"):
        if args["trimester"] is None:
            if args.get("csv_fname"):
                args["trimester"]= get_trimester_from_csv_fname(args["csv_fname"])
    return args

# The login_url is ignored for the LVS backend.
@pronote.reimplemented
def open_session(user, password, login_url):
    if user is None:
        user= input("Username:\n")
    if password is None:
        password= input_password("Password:\n")
    json_payload= json.loads('{}')
    json_payload["externalentpersjointure"]= None
    json_payload["login"]= user
    json_payload["password"]= password
    try:
        s= requests.Session()
        r= s.post(get_url("connexion"), json= json_payload)
    except Exception as e:
        raise RuntimeError(f"Connexion error: \n{e}")
    r.raise_for_status()
    json_response= json.loads(r.text)
    if not "auth" in json_response:
        raise RuntimeError("Unexpected authentification request response")
    if not json_response["auth"] == "ok":
        raise RuntimeError("Authentification failure")
    print("Authentification success")
    return s

@pronote.reimplemented
def close_session(s):
    return s.close()

def base64_pad(s):
    pad = len(s)%4
    return s + "="*pad

@pronote.notimplemented
# This id is needed in some requests, and only given through the initial session cookie.
def get_teacher_id(s):
    if not 'JWT-LVS' in s.cookies:
        raise RuntimeError("Session error: No JWT in cookies.")
    cs= s.cookies['JWT-LVS']
    payload64= cs.split(".")[1]
    payload= base64.b64decode(base64_pad(payload64))
    payload_json= json.loads(payload)
    if not 'pid' in payload_json:
        raise RuntimeError("Session error: No pid in JWT cookie.")
    teacher_id= payload_json["pid"]
    return teacher_id

@pronote.reimplemented
def get_groups(s):
    teacher_id= get_teacher_id(s)
    url= get_url("get_groups")
    payload='{"idprof":0}'
    json_payload= json.loads(payload)
    json_payload["idprof"]= teacher_id
    r= s.post(url, json= json_payload)
    r.raise_for_status()
    json_groups= r.json()
    return json_groups

def is_csv_filename(fname):
    return fname.endswith(".csv")

@pronote.reimplemented
def trimester_regex():
    return r"(?:1er|2ème|3ème) Trimestre"

def is_lvs_trimester_csv(fname):
    return is_csv_filename(fname) and bool(re.search(trimester_regex(), fname))

def get_csv_filename(prompt_if_notfound= True, silent= False, confirm= False):
    csv_fname=""
    multiple_csv_flag= False
    for fname in os.listdir():
        if not os.path.isfile(fname):
            continue
        if is_csv_filename(fname):
            if csv_fname != "":
                if is_lvs_trimester_csv(fname) == is_lvs_trimester_csv(csv_fname):
                    multiple_csv_flag= True
                    # Keep csv_fname unchanged (no point changing)
                else:
                    if is_lvs_trimester_csv(fname):
                        csv_fname= fname
            else:
                csv_fname= fname
    if not prompt_if_notfound:
        if csv_fname == "":
            return ""
        if multiple_csv_flag:
            if not silent:
                print("Warning: Multiple CSV files found. Proceeding without picking one")
            return ""
    got_from_dialog_flag= False
    if csv_fname == "":
        print(f"No csv file specified as an argument, and none found in working directory {os.getcwd()}.")
        csv_fname= input_open_file("Enter the name of the CSV file:\n",
                                   filetypes=[("CSV files", ".csv"), ("all files", "*")])
        got_from_dialog_flag= True
        if csv_fname == "":
            return csv_fname
    elif multiple_csv_flag:
        print(f"No csv file specified as an argument, and multiple files found in working directory {os.getcwd()}.")
        answer= input_open_file(f"Enter the name of the CSV file. Default is to use \"{csv_fname}\":\n",
                                filetypes=[("CSV files", ".csv"), ("all files", "*")])
        if answer != "":
            csv_fname= answer
    if not silent:
        print("Using csv file ", csv_fname)
    if confirm and not got_from_dialog_flag:
        choice= input_Yn(f"Use CSV file {csv_fname}?")
        if not choice:
            return ""
    return csv_fname

def get_csv_rows(csv_fname):
    with open(csv_fname, encoding='utf-8') as csv_f:
        lines= csv_f.readlines()
        csv_f.seek(0)
        dialect= csv.Sniffer().sniff("\n".join(lines[:4]))
        csv_reader= csv.reader(csv_f, dialect=dialect)
        rows= list(csv_reader)
        if rows and rows[0]:
            # \ufeff is the utf-8 BOM character.
            # It is sometimes inserted at the sart of CSV files, causing problems.
            if rows[0][0] and rows[0][0][0] == "\ufeff":
                rows[0][0]= rows[0][0][1:]
        csv_f.close()
        return rows

def get_group_name_from_csv(csv_fname):
    rows= get_csv_rows(csv_fname)
    if len(rows) < 1:
        raise RuntimeError("Empty csv file")
    group_name_csv= rows[0][0]
    group_name_csv= group_name_csv.strip()
    group_name_csv= group_name_csv.replace("\"","")
    group_name_csv= group_name_csv.replace("\ufeff","") # utf-8 BOM
    print("Using group name from csv:", group_name_csv)
    return group_name_csv

# Returns a value to include as a number in the json.
# This needs to be int or float, but the float "2." should be the int 2 instead
# Also there should me a max of 3 decimals.
def correct_number_style(f):
    if int(f) == f:
        return int(f) # which is not the same as f.
    else:
        s= "{:.3f}".format(f)
        return float(s)

def comma_number_str(f0):
    if f0 is None:
        return ""
    f= f0
    try:
        f= float(f)
    except ValueError:
        # Do not modify pure strings
        return f0
    try:
        i= int(f)
    except ValueError:
        # Treat "nan" etc as pure string and not floats
        return f0
    if int(f) == float(f):
        return str(int(f))
    else:
        s= str(correct_number_style(float(f)))
        s= s.replace(".",",") # comma numbers
        return s

def is_csv_number(cell):
    cell_s= str(cell)
    cell_s= cell_s.replace(",", ".")
    try:
        f= float(cell_s)
        # This works for "1.2" but fails for "nan"
        i= int(f)
        return True
    except ValueError:
        return False

def csv_number_of_s(s):
    #return str(s).replace(",",".")
    return s
    
def nicer_str(obj):
    r= ""
    if type(obj) == dict :
        strs = [ str(a) + ":" + str(b) for a,b in obj.items() ]
    elif hasattr(obj, '__iter__'):
        strs= [ str(e) for e in obj ]
    else:
        strs= [str(obj)]
    return ", ".join(strs)

# Returns a str formated in the way used by the website
def get_current_date_s():
    # Example: 2022-04-22T22:46:59.516Z
    d= datetime.datetime.utcnow()
    s= d.strftime("%Y-%m-%dT%H:%M:%S.%f")
    # Now s is 2022-04-22T22:46:59.516123, need to cut last 3 microseconds digits and add Z:
    s= s[:-3]+"Z"
    return s

# returns a dict of group_name : service_id
@pronote.notimplemented
def get_services(json_groups):
    service_id_of_group_name= {}
    for group in json_groups:
        service_id_of_group_name[group["libelle"]] = group["id"]
    return service_id_of_group_name

@pronote.notimplemented
def match_group_name_in_json(group_name, json_groups):
    service_id_of_group_name= get_services(json_groups)
    for group_name_web, service_id in service_id_of_group_name.items():
        if group_name_web.find(group_name.strip()) != -1 :
            return group_name_web, service_id
    raise RuntimeError("Couldn't match group name " + group_name + " in website.")

@pronote.reimplemented
def get_service_id(group_name, json_groups):
    group_name_web, service_id= match_group_name_in_json(group_name, json_groups)
    return service_id

@pronote.notimplemented
def get_trimester_from_json(json_groups):
    if len(json_groups) == 0:
        raise RuntimeError("No groups found on website")
    group= json_groups[0]
    default_t= 0
    all_locked= True
    for periode in group["periodes"]:
        print(json.dumps(periode))
        t= periode["numero"]
        if periode["isParDefaut"] == True:
            default_t= t
        if len(periode["verrouillages"]) != 0 and periode["verrouillages"][0]["verrouille"] == False:
            all_locked= False
    if default_t == 0:
        raise RuntimeError("Unexpected format on website. Unable to get trimesters information.")
    if all_locked:
        print(f"No trimester provided. Guessing trimester 3 from website (all trimesters are locked, so assuming year has ended).")
        return 3
    print(f"No trimester provided. Guessing trimester {default_t} from website.")
    return default_t

# This is pure heuristic and should not be trusted.
# The dates choosen for trimester threshold vary per year and school; an arbitrary choice was made.
def guess_trimester_from_date(date_ymd= None):
    if date_ymd is None:
        d= datetime.date.today()
    else:
        d= datetime.date.fromisoformat(date_ymd)
    # School years span over two calendar years, like 2021-2022.
    # If date d is in 2022, we need to know if it's part of 2021-2022 or 2022-2023.
    # For this we compare to midsummer.
    midsummer= datetime.date(d.year, 8, 1) # august first
    if d < midsummer:
        # If d is in 2022, this means school year is 2021-2022
        t2_start= datetime.date(d.year - 1, 12, 1) # december 1, 2021
        t3_start= datetime.date(d.year, 3, 1)      # march 1, 2022
    else:
        # If d is in 2022, this means school year is 2022-2023
        t2_start= datetime.date(d.year, 12, 1)     # december 1, 2022
        t3_start= datetime.date(d.year + 1, 3, 1)  # march 1, 2023
    if   d < t2_start:
        return 1
    elif d < t3_start:
        return 2
    else:
        return 3

# Parse from website (str to str)
@pronote.reimplemented
def grade_parse(grade):
    return grade

@pronote.reimplemented
def get_grades(s, service_id, trimester):
    url= get_url("get_grades")
    payload='{"serviceId":0,"periodeId":0,"devoirId":null,"profId":0}'
    json_payload= json.loads(payload)
    teacher_id= get_teacher_id(s)
    json_payload["periodeId"]= trimester
    json_payload["profId"]= teacher_id
    json_payload["serviceId"]= service_id
    r= s.post(url, json= json_payload)
    r.raise_for_status()
    json_grades= r.json()
    return json_grades

@pronote.reimplemented
def get_apprs(s, service_id, trimester):
    url= get_url("get_apprs")
    payload='{"idService":0,"idPeriode":0}'
    json_payload= json.loads(payload)
    json_payload["idService"]= service_id
    json_payload["idPeriode"]= trimester
    r= s.post(url, json= json_payload)
    r.raise_for_status()
    json_apprs= r.json()
    return json_apprs

# returns a dict of student_id : student_lastname
@pronote.notimplemented
def get_student_lastnames_of_ids(json_grades):
    d= {}
    for student in json_grades["eleves"]:
        student_id= student["eleveid"]
        student_lastname= student["nom"]
        d[student_id]= student_lastname
    return d

# returns a dict of student_id : student_name
@pronote.reimplemented
def get_student_names_of_ids(json_grades):
    d= {}
    for student in json_grades["eleves"]:
        student_id= student["eleveid"]
        student_name= student["nom"] + " " + student["prenom"]
        d[student_id]= student_name
    return d

# returns a dict of (evaluation_id, student_id) : grade, where grade is a str
@pronote.reimplemented
def grades_dict_of_json(json_grades):
    grades= {}
    for student in json_grades["eleves"]:
        student_id= student["eleveid"]
        for evaluation in student["notes"]:
            evaluation_id= evaluation["iddevoir"]
            grade= grade_parse(evaluation["note"])
            grades[(evaluation_id, student_id)]= grade
    return grades

# returns a dict of student_id : appr
@pronote.reimplemented
def appr_dict_of_json(json_apprs):
    apprs= {}
    for student in json_apprs["eleves"]:
        student_id= student["id"]
        if (not "appreciation" in student) or not student["appreciation"]:
            continue
        appr= student["appreciation"].get("appreciation","")
        if not appr:
            appr= ""
        apprs[student_id]= appr.strip()
    return apprs

@pronote.notimplemented
def get_date_from_json_ymd(json_grades, evaluation_id):
    for e in json_grades["evaluations"]:
        if e["id"] == evaluation_id:
            return e["dateDevoir"]
    raise RuntimeError(f"Evaluation id {evaluation_id} not on website.")

def get_trimester_nb(s):
    m= re.search(trimester_regex(), s)
    if not m:
        return None
    trimester_s= m.group()
    trimester_nb= int(re.search("\d", trimester_s).group())
    return trimester_nb

def get_trimester_from_csv_fname(csv_fname):
    trimester= get_trimester_nb(csv_fname)
    if trimester is None:
        raise RuntimeError(f'Unable to guess trimester from csv file name "{csv_fname}". The trimester must be explicitely given. Launch the program with -h to see usage.')
    print("Using trimester from csv file name:", trimester)
    return trimester

@pronote.reimplemented
def get_mess_dest_json(s, dest_search_s, dest_type="student"):
    # typeRecherche: 0= tous, 1= personnes, 2= groupes
    payload_dest_search= '{"niveaux":[],"profils":[2],"groupes":[],"maxrows":50,"typeRecherche":1,"page":1}'
    json_payload_dest_search= json.loads(payload_dest_search)
    json_payload_dest_search['keyword']= dest_search_s
    dest_types={"staff":0, "teacher":1, "student":2, "parent":3, "all":5}
    if not dest_type in dest_types:
        raise Exception(f'Incorrect destinatory type (should be in {list(dest_type.keys())})')
    json_payload_dest_search['profils'][0]= dest_types[dest_type]
    r= s.post(get_url("dest"), json= json_payload_dest_search)
    r.raise_for_status()
    json_dest_search_res= r.json()
    if len(json_dest_search_res) < 1:
        raise Exception('No result for destinatory search "' + dest_search_s + '"')
    if len(json_dest_search_res) > 1:
        raise Exception('Multiple results for destinatory search "' + dest_search_s + '"')
    return json_dest_search_res[0]

# Website generates html from text in a very specific (and terrible) way.
@pronote.reimplemented
def convert_to_terrible_html_message(text_s):
    r= ''
    for line in text_s.splitlines():
        r+= '<p>'
        for i in range(len(line)):
            if i+1 < len(line) and line[i] == line[i+1] == ' ':
                r+= '&nbsp;'
            else:
                r+= line[i]
        r+= '</p>'
    return r

@pronote.reimplemented
def cache_possible_recipients(s, dest_types=None):
    # No caching for lvs
    pass

@pronote.reimplemented
def clear_possible_recipients_cache():
    # No caching for lvs
    pass

# "enseigne" (enseigné) is an optional parameter used in the pronote backend to only search
# for students taught by the user (will only work with dest_type="student").
@pronote.reimplemented
def send_message(s, dest_search_s, message_subject, message_body, dest_type="student",
                 enseigne=None):
    r= s.post(get_url("new_message"))
    r.raise_for_status()
    json_new_message= r.json()
    json_payload_dest_add= get_mess_dest_json(s, dest_search_s, dest_type=dest_type)
    r= s.post(get_url("dest_add").format(json_new_message['id']), json= json_payload_dest_add)
    r.raise_for_status()
    json_dest_add_res= r.json()
    json_payload_compose= json_new_message
    json_payload_compose['a']= json_dest_add_res
    json_payload_compose['objet']= message_subject
    json_payload_compose['message']= convert_to_terrible_html_message(message_body)
    r= s.post(get_url("compose").format(json_new_message['id']), json= json_payload_compose)
    r.raise_for_status()
    r= s.post(get_url("send").format(json_new_message['id']))
    r.raise_for_status()
    res_json= r.json()
    if r.status_code == 200 and int(res_json['nbenvoi']) == 1:
        errors= 0
    elif int(res_json['nbenvoi']) != 1:
        print('Error: Nb of messages sent:', res_json['nbenvoi'])
        errors= 1
    else:
        print('Error: Message NOT sent successfully')
        errors= 2
    return errors

@pronote.notimplemented
def pretty_print_inbox(json_inbox):
    # Reverse to display latest email at the bottom for easier testing.
    l= list(json_inbox['mails'])
    l.reverse()
    for mail in l:
        print("From:", mail['expediteur'])
        print("Received:", mail['dateCreationStr'])
        print("Subject:", mail['objet'])
        soup = BeautifulSoup(mail['message'], 'html.parser')
        for br in soup.find_all("br"):
            br.replace_with("\n")
        print(soup.text)
        print()

@pronote.notimplemented
def show_messages(s):
    r= s.get(get_url("inbox"))
    r.raise_for_status()
    json_inbox= r.json()
    print("Nb of mails:", json_inbox['nbMails'])
    pretty_print_inbox(json_inbox)

# Filters out the rows in the website generated csv which do not represent students (typically the first two and last two).
def student_rows_of_csv_rows(rows):
    student_rows= []
    # Skip the first row no matter what
    for row in rows[1:] :
        csv_name= row[0]
        # Second line of website generated csv
        if csv_name.endswith("élèves"):
            continue
        if csv_name.strip() == "":
            continue
        # No numbers in names (I hope)
        if re.search(r"\d", csv_name):
            continue
        # Last two lines of website generated csv
        if csv_name == "Moyenne" or csv_name == "Note min | Note max" or csv_name == "Moy. du groupe :" :
            break
        student_rows.append(row)
    return student_rows

# Show a preview of some students (e.g thoses that will be affected by a change).
def students_preview(student_names, student_ids):
    names= [student_names[sid] for sid in student_ids]
    if len(names) > 4:
        names= names[:4] + ["..."]
    return "For student(s): "+", ".join(names)

# Returns (error_flag, row_of_student_id). The second is a dict of student_id:row.
def match_students_to_rows(s, csv_fname, json_grades= None, student_names_of_ids= None):
    row_of_student_id={}
    rows= get_csv_rows(csv_fname)
    if student_names_of_ids is None:
        assert not json_grades is None
        student_names_of_ids= get_student_names_of_ids(json_grades)
    id_of_names= { student_names_of_ids[i] : i for i in student_names_of_ids.keys() }
    not_matched_csv= []
    rows= student_rows_of_csv_rows(rows)
    for row in rows:
        csv_name= row[0]
        if csv_name in id_of_names:
            student_id= id_of_names[csv_name]
            row_of_student_id[student_id]= row
            del id_of_names[csv_name]
        else:
            if re.search("[0-9]", csv_name):
                # If the "name" contains a digit, it's probably not a name;
                # don't count it as unmatched
                continue
            not_matched_csv.append(csv_name)
    not_matched_website= list(id_of_names.keys())
    print("Matched ", len(row_of_student_id), " students from website to csv.")
    error_flag= False
    if not_matched_website :
        error_flag= True
        print("Warning: Not all students from website matched to names in csv file")
        print("*** Students from website not matched:")
        for s in not_matched_website:
            print(s)
        print("***")
    if not_matched_csv :
        error_flag= True
        print("Warning: Not all lines from csv matched to names on the website")
        print("*** Lines from csv not matched:")
        for name in not_matched_csv:
            print(name)
        print("***")
    return (error_flag, row_of_student_id)

# Looks for group_name as a substring of one of the classgroups.
def match_group_to_classgroup(classgroups, group_name):
    for classgroup_name, group_id in classgroups.items():
        if group_name.find(classgroup_name) != -1:
            return (classgroup_name , group_id)
    # Couldn't match, prepare error message
    classgroup_names= ','.join(list(classgroups.keys()))
    raise RuntimeError(f"Unable to match group name \"{group_name}\" to one of the possible class group names (full list: {classgroup_names}). You can specify which class group to use with the -g option, or by modifying the first cell of the CSV.")

def display_errors(f):
    try:
        return f()
    except RuntimeError as e:
        print("Error:", str(e))
        return
    except requests.RequestException as e:
        print("Error with request:", e.response.text)
        return

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scripting for an Axess website.
"""

from lvs_module import *

import requests
import json
import csv
import os, sys
import re
import random, time # for delays

add_url("send_grades", "/vsn.main/WSCompetences/saveBatchEvaluations")
add_url("create_test", "/vsn.main/WSCompetences/creerEvaluation")
add_url("modify_test", "/vsn.main/WSCompetences/modifierDevoir")

# Returns a dict of test_name : (col, max_grade, coefficient)
def get_tests_from_csv(csv_fname):
    rows= get_csv_rows(csv_fname)
    if len(rows) < 1:
        raise RuntimeError("Empty csv file")
    if len(rows) < 2:
        raise RuntimeError("Unexpected csv file format (no second line with test descriptions)")
    test_descs={}
    for i in range(1, len(rows[1])):
        desc_s= rows[1][i]
        float_re= r'\d+(?:\.\d*)?'  # (?: ... ) is non capturing grouping
        float_group= '(' + float_re + ')'
        match= re.search('/' + float_group + ' - Coef : ' + float_group, desc_s)
        if match is None:
            continue
        # This line should not raise any error given "float_re".
        desc= (i, float(match.groups()[0]), float(match.groups()[1]))
        test_name= rows[0][i]
        if test_name.strip() == "":
            raise RuntimeError("Detected a test description \"" + desc + "\" in column" + str(i+1) + " (starting from 1), but the cell above is empty (expected a valid test name).")
        if test_name in test_descs.keys():
            raise RuntimeError("Test name \""+test_name+"\" appears multiple times in first row of csv file.")
        test_descs[test_name]= desc
    print("Found",len(test_descs),"tests in the csv file: ", ", ".join(test_descs.keys()))
    return test_descs

# "service_id" is 1-to-1 to group_name for a given teacher (there is a different notion
# of "group_id", which is independent from teachers, and used for messages).
# Grades are assigned to a given service_id (so that each teacher can assigne their own
# grades to each group)
def create_test(s, service_id, trimester, test_name, desc, hidden= False):
    url= get_url("create_test")
    payload='{"evaluation":{"dateDevoir":"","competenceIds":[],"titre":"","publie":true,"coefficient":0,"enseignantId":0,"noteMaximalEvaluation":20,"typeEvaluation":"NOTE","serviceId":0,"periodeId":0}}'
    json_payload= json.loads(payload)
    json_eval= json_payload["evaluation"]
    teacher_id= get_teacher_id(s)
    (_, max_grade, coefficient)= desc
    json_eval["dateDevoir"]= get_current_date_s()
    json_eval["titre"]= test_name
    json_eval["coefficient"]= correct_number_style(coefficient)
    json_eval["enseignantId"]= teacher_id
    json_eval["noteMaximalEvaluation"]= correct_number_style(max_grade)
    json_eval["serviceId"]= service_id
    json_eval["periodeId"]= trimester
    if hidden:
        json_eval["publie"]= False
    print("Creating", test_name)
    r= s.post(url, json= json_payload)
    r.raise_for_status()
    json_created= r.json()
    test_id= json_created["id"]
    desc_full= desc + (test_id,)
    return desc_full

def modify_test_desc(s, json_grades, service_id, trimester, test_name, max_grade, coefficient):
    devoir= None
    for devoir in json_grades["evaluations"]:
        if devoir["titre"] == test_name:
            break
    assert devoir
    # The json "devoir" will be our basis for the payload.
    # We first need to trim the keys we don't need from it.
    payload_keys= {'id', 'verrouille', 'sousServiceId', 'publie', 'enseignantId', 'noteMaximalEvaluation', 'periodeId', 'titre', 'typeEvaluation', 'competenceIds', 'serviceId', 'coefficient', 'dateDevoir', 'typeDevoir'}
    json_eval= devoir.copy()
    for k in devoir:
        if not k in payload_keys:
            del json_eval[k]
    # Now add the keys not in devoir
    json_eval["competenceIds"]= []
    json_eval["periodeId"]= trimester
    json_eval["serviceId"]= service_id
    # Now modify the remaining keys to match csv desc.
    json_eval["noteMaximalEvaluation"]= max_grade
    json_eval["coefficient"]= coefficient
    json_payload=json.loads('{}')
    json_payload["evaluation"]=json_eval
    print("Modifying max grade or coefficient for", test_name)
    r= s.post(get_url("modify_test"), json= json_payload)
    r.raise_for_status()

# Returns (created_flag, test_descs_full),
# Where test_descs_full is a dict of test_name : (col, max_grade, coefficient, test_id)
def get_test_id_and_create_tests(s, service_id, trimester, json_grades, test_descs,
                                 create_tests= False, hidden= False):
    created_flag= False
    test_descs_full= {}
    tests_not_in_website= []
    tests_with_new_desc= []
    website_descs= {devoir["titre"]:(devoir["noteMaximalEvaluation"], devoir["coefficient"], devoir["id"]) for devoir in json_grades["evaluations"]}
    tests_not_in_csv= set(website_descs.keys())
    for (test_name, desc) in test_descs.items():
        if test_name in website_descs.keys():
            max_grade, coefficitent, test_id= website_descs[test_name]
            # tuple addition (new tuple with one more element)
            test_descs_full[test_name] = desc + (test_id,)
            if (not grade_equality(max_grade, desc[1])) or coefficitent != desc[2]:
                tests_with_new_desc.append(test_name)
            tests_not_in_csv.remove(test_name)
        else:
            tests_not_in_website.append(test_name)
    if tests_not_in_csv:
        print("WARNING: "+str(len(id_of_name))+" test(s) are present on the website but not in the csv file: " + ", ".join(tests_not_in_csv))
    if tests_not_in_website:
        print("Found "+str(len(tests_not_in_website))+" test(s) not present on the website: " + ", ".join(tests_not_in_website))
        if create_tests:
            first_it= True
            for test_name in tests_not_in_website:
                if first_it:
                    first_it= False
                else:
                    time.sleep(.1)
                desc= test_descs[test_name]
                desc_full= create_test(s, service_id, trimester, test_name, desc, hidden=hidden)
                test_descs_full[test_name] = desc_full
                created_flag= True
    if created_flag:
        print("Test(s) successfully created. Note that their creation date has been set to today.")
    if tests_with_new_desc:
        print("Found "+str(len(tests_with_new_desc))+" test(s) with max grade or coefficient different than on the website: " + ", ".join(tests_with_new_desc))
        if create_test:
            dialog_s= "Upload the modified max grades and coefficients? ("+str(len(tests_with_new_desc))+" test(s) will be modified.)"
            answer= input_Yn(dialog_s)
            if answer:
                first_it= True
                for test_name in tests_with_new_desc:
                    if first_it:
                        first_it= False
                    else:
                        time.sleep(.1)
                    (col, max_grade, coefficient)= test_descs[test_name]
                    modify_test_desc(s, json_grades, service_id, trimester, test_name, max_grade, coefficient)
    return (created_flag, test_descs_full)

def str_of_translated_list(d, L):
    return ', '.join([d[a] for a in L])

# Grades are strings, which can represent float (but not necessarly)
# If they represent float, they should be considered equal if the floats are
def grade_equality(g1, g2):
    # Identify "" and None (so as not to uselessly overwrite None with "").
    if g1 is None:
        g1= ""
    if g2 is None:
        g2= ""
    if g1 == g2:
        # string equality
        return True
    if g1 is None or g2 is None:
        # we already know g1 != g2
        return False
    try:
        g1= float(g1)
        g2= float(g2)
        return g1 == g2
    except ValueError:
        # At leaset one is not a float, and they are not string equal
        return False
    
# Defaults to dry run
def send_grades(s, csv_fname, trimester, group_name,
                create_tests= False, hidden= False,
                ask_to_write= True, never_write= False,
                ask_to_delete= True, never_delete= False):
    test_descs= get_tests_from_csv(csv_fname)
    json_groups= get_groups(s)
    service_id= get_service_id(group_name, json_groups)
    json_grades= get_grades(s, service_id, trimester)
    created_flag, test_descs_full= get_test_id_and_create_tests(s, service_id, trimester, json_grades, test_descs, create_tests=create_tests, hidden=hidden)
    # Redownload grades after creating a test (the web app also does this)
    # (This can also avoid uploading a lot of empty grades.)
    if created_flag:
        json_grades= get_grades(s, service_id, trimester)        
    error_flag, row_of_student_id= match_students_to_rows(s, csv_fname, json_grades)
    url= get_url("send_grades")
    payload='{"saisies":[],"devoirs":[],"bonus":[],"idservice":0,"idperiode":0}'
    json_payload= json.loads(payload)
    json_payload["idperiode"]= trimester
    json_payload["idservice"]= service_id
    payload_saisie='{"ideleve":0,"competences":[],"noteToSave":true,"competencesToSave":false,"iddevoir":0,"note":""}'
    # This template will be copied multiple times.
    json_payload_saisie_template= json.loads(payload_saisie)
    grades_website= grades_dict_of_json(json_grades)
    student_lastnames= get_student_lastnames_of_ids(json_grades)
    def students_preview(student_ids):
        names= [student_lastnames[sid] for sid in student_ids]
        if len(names) > 4:
            names= names[:4] + ["..."]
        return "For student(s): "+", ".join(names)
    # A "deleted" grade is when we replace something with ''
    delete_count= 0
    overwrite_count= 0
    written_count= 0
    modified_tests= set()
    for test_name, (test_col, max_grade, coefficient, test_id) in test_descs_full.items():
        written_list= []        
        overwritten_list= []
        deleted_list= []
        for (student_id, row) in row_of_student_id.items():
            grade_csv= row[test_col]
            try:
                g= float(grade_csv)
                assert g >= 0 # csv parser shouldn't produce < 0
                if g > max_grade:
                    print(f"Warning: In test \"{test_name}\", grade \"{grade_csv}\" in csv file is greater than the maximum grade of {max_grade}. Replacing it with {max_grade}")
                    grade_csv= str(correct_number_style(max_grade))
            except (ValueError, TypeError):
                pass # Leave pure str grades alone
            if (test_id, student_id) in grades_website:
                grade_web= grades_website[(test_id, student_id)]
                if grade_equality(grade_web, grade_csv):
                    # Don't fill the request with overwrites of the existing values
                    continue
                if grade_csv == '' or grade_csv is None:
                    deleted_list.append(student_id)
                    if never_delete:
                        # Do not put deltes in the request if this option is True
                        continue
                elif not (grade_web == '' or grade_web is None):
                    overwritten_list.append(student_id)
            written_list.append(student_id)
            json_payload_saisie= json_payload_saisie_template.copy()
            json_payload_saisie["ideleve"]= student_id
            json_payload_saisie["iddevoir"]= test_id
            json_payload_saisie["note"]= grade_csv
            json_payload["saisies"].append(json_payload_saisie)
            modified_tests.add(test_id)
        if len(written_list) > 0:
            print(f"Test \"{test_name}\": {len(written_list)} grade(s) to upload.")
            print(students_preview(written_list))
            written_count+= len(written_list)
        if len(overwritten_list) > 0:
            print(f"Warning: in test \"{test_name}\": {len(overwritten_list)} grade(s) to upload would OVERWRITE an existing grade on website.")
            print(students_preview(overwritten_list))
            overwrite_count+= len(overwritten_list)
        if len(deleted_list) > 0 and not never_delete:
            print(f"Warning: in test \"{test_name}\": {len(deleted_list)} grade(s) to upload would DELETE an existing grade on website.")
            print(students_preview(deleted_list))
            delete_count+= len(deleted_list)
    for test_id in modified_tests:
        json_payload["devoirs"].append(test_id)
    if written_count == 0:
        print("No grades need to be uploaded.")
        return
    if never_write:
        print("Not uploading as per option.")
        return
    dialog_s= ""
    if delete_count + overwrite_count > 0 and ask_to_delete:
        dialog_s+= f"Uploading grades will DELETE {delete_count} and OVERWRITE {overwrite_count} grade(s) on the website.\n"
    if ask_to_write:
        dialog_s+= "Uploading will write "+str(written_count)+" grade(s) to the website.\n"
    if dialog_s != "":
        answer= input_Yn(dialog_s + "Continue?")
        if not answer:
            print("Aborting.")
            if delete_count > 0 and ask_to_delete:
                print("You can upload grades without deleting existing ones with the --no-delete option.")
            return
    print("Uploading...")
    # Actual uploading
    r= s.post(url, json= json_payload)
    r.raise_for_status()
    print("Done.")
    
def main():
    try:
        s= None
        arg_descs=[
            (('csv_fname',), {'metavar':'CSV_FILE', 'nargs':"?",
                        'help':'The csv file in which grades will be read. Can be omitted if there is only one csv file in the working directory. The program expects the file to be in the format exported by the website. In particular, test names should be on the first line, with the cell below each name describing the maximum grade and grade multiplier as in the following: "/10 - Coef : 0.5".'}),
#            (('-e', '--evaluation'), {
#                        'help':'If provided, only this evaluation (test) will be modified on the website.'}),            
            (('--write',), {'action':argparse.BooleanOptionalAction, 'help':'Write grades to the website. Default is to ask. Note that this is independent from creating new tests. However, --no-write implies --no-delete.'}),
            (('--delete', '--overwrite'), {'action':argparse.BooleanOptionalAction, 'help':'Overwrite existing grades on the website (including deleting them if they are not present in the CSV). Default is to ask. This does not delete tests.'}),
            (('--create',), {'action':argparse.BooleanOptionalAction, 'help':'Create or do not create tests if they do not exist on the website. Default is to create.'}),
            (('--hidden',), {'action':argparse.BooleanOptionalAction, 'help':'When creating tests, keep it hidden from students (corresponds to the "publish" option on the website). Default is to publish the test. Does not affect tests which already exist on the website.'})
        ]
        shared_args=["dry-run", "group", "trimester"]
        args= lvs_get_args(arg_descs=arg_descs, shared_args= shared_args, description='Upload grades from a csv file to a specific axess website.', required=["csv_fname"])
        if args["write"] is None:
            args["ask_to_write"]= True
            args["never_write"]= False
        else:
            args["ask_to_write"]= False
            args["never_write"]= not args["write"]
            if args["write"] == False:
                args["delete"]= True
        if args["delete"] is None:
            args["ask_to_delete"]= True
            args["never_delete"]= False
        else:
            args["ask_to_delete"]= False
            args["never_delete"]= not args["delete"]
        if args["create"] is None:
            args["create"]= True
        if args["hidden"] is None:
            args["hidden"]= False
        s= open_session(args["user"], args["password"])
        send_grades(s, args["csv_fname"], args["trimester"], args["group_name"],
                    create_tests= args["create"], hidden= args["hidden"],
                    ask_to_write= args["ask_to_write"], never_write= args["never_write"],
                    ask_to_delete= args["ask_to_delete"], never_delete= args["never_delete"])
        show_message("Done.")
    finally:
        if s is not None:
            s.close()


if __name__ == '__main__' :
    display_errors(main)


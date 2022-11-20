#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scripting for an Axess website.
"""

from lvs_module import *

add_url("get_apprs", "/vsn.main/WSCompetences/loadInfosFinPeriode")
add_url("send_appr", "/vsn.main/WSCompetences/saveAppreciation")

appr_header_string= "Appréciations générales"

def get_appr_col(csv_fname):
    rows= get_csv_rows(csv_fname)
    if len(rows) < 1:
        raise RuntimeError("Empty csv file")
    if len(rows) < 2:
        raise RuntimeError("Unexpected csv file format (no second line with test descriptions)")
    try:
        return rows[0].index(appr_header_string)
    except ValueError:
        raise RuntimeError("Error: CSV file must contain a column named \"" + appr_header_string + "\"")

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

# returns a dict of student_id : appr
def appr_dict_of_json(json_apprs, trimester):
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

def send_apprs(s, csv_fname, trimester, group_name,
               ask_to_write= True, never_write= False,
               ask_to_delete= True, never_delete= False):
    json_groups= get_groups(s)
    service_id= get_service_id(group_name, json_groups)
    json_grades= get_grades(s, service_id, trimester)
    json_apprs= get_apprs(s, service_id, trimester)
    apprs_web= appr_dict_of_json(json_apprs, trimester)
    appr_col= get_appr_col(csv_fname)
    error_flag, row_of_student_id= match_students_to_rows(s, csv_fname, json_grades)
    url= get_url("send_appr")
    payload='{"periodeId":0,"serviceId":0,"eleveId":0,"appreciation":"","numero":1}'
    # This template will be copied multiple times.
    json_payload_template= json.loads(payload)
    json_payload_template["periodeId"]= trimester
    json_payload_template["serviceId"]= service_id
    student_lastnames= get_student_lastnames_of_ids(json_grades)
    def students_preview(student_ids):
        names= [student_lastnames[sid] for sid in student_ids]
        if len(names) > 4:
            names= names[:4] + ["..."]
        return "For student(s): "+", ".join(names)
    # A "deleted" appr is when we replace something with ''
    delete_count= 0
    overwrite_count= 0
    write_count= 0
    write_list= []
    overwrite_list= []
    delete_list= []
    json_payloads=[]
    for (student_id, row) in row_of_student_id.items():
        student_name= row[0]
        appr_csv= row[appr_col].strip()
        if appr_csv == "":
            continue
        appr_web= apprs_web.get(student_id,"")
        if appr_csv == appr_web:
            # Don't fill the request with overwrites of the existing values
            continue
        if not appr_csv:
            # We know that appr_web != appr_csv, so this would be a deletion
            delete_list.append(student_id)
            if never_delete:
                # Do not put deletes in the request if this option is True
                continue
        elif appr_web:
            overwrite_list.append(student_id)
        write_list.append(student_id)
        json_payload= json_payload_template.copy()
        json_payload["eleveId"]= student_id
        json_payload["appreciation"]= appr_csv
        json_payloads.append((student_name, json_payload))
    if len(write_list) > 0:
        print(f"{len(write_list)} appreciation(s) to upload.")
        print(students_preview(write_list))
        write_count+= len(write_list)
    if len(overwrite_list) > 0:
        print(f"Warning: {len(overwrite_list)} appreciation(s) to upload would OVERWRITE an existing appreciation on website.")
        print(students_preview(overwrite_list))
        overwrite_count+= len(overwrite_list)
    if len(delete_list) > 0 and not never_delete:
        print(f"Warning: {len(delete_list)} appreciation(s) to upload would DELETE an existing appreciation on website.")
        print(students_preview(delete_list))
        delete_count+= len(delete_list)
    if write_count == 0:
        print("No appreciations need to be uploaded.")
        return
    if never_write:
        print("Not uploading as per option.")
        return
    dialog_s= ""
    if delete_count + overwrite_count > 0 and ask_to_delete:
        dialog_s+= "Uploading appreciations will "
        if delete_count:
            dialog_s+= f"DELETE {delete_count}"
        if delete_count and overwrite_count:
            dialog_s+= " and "
        if overwrite_count:
            dialog_s+= f"OVERWRITE {overwrite_count}"
        dialog_s+= " appreciation(s) on the website.\n"
    if ask_to_write:
        dialog_s+= "Uploading will write "+str(write_count)+" appreciation(s) to the website.\n"
    if dialog_s != "":
        answer= input_Yn(dialog_s + "Continue?")
        if not answer:
            print("Aborting.")
            if delete_count > 0 and ask_to_delete:
                print("You can upload appreciations without deleting existing ones with the --no-delete option.")
            return
    # Actual uploading
    for (student_name, json_payload) in json_payloads:
        print("Uploading: " + student_name)
        r= s.post(url, json= json_payload)
        r.raise_for_status()
    print(f"{len(json_payloads)} appreciations uploaded.")

def main():
    try:
        s= None
        arg_descs= [
            (('csv_fname',), {'metavar':'CSV_FILE', 'nargs':"?",
                              'help':'The csv file in which grades will be read. Can be omitted if there is only one csv file in the working directory. The program expects the file to be in the format exported by the website. In particular, test names should be on the first line, with the cell below each name describing the maximum grade and grade multiplier as in the following: "/10 - Coef : 0.5".'}),
            (('--write',), {'action':argparse.BooleanOptionalAction, 'help':'Write appreciations to the website. Default is to ask. --no-write implies --no-delete.'}),
            (('--delete', '--overwrite'), {'action':argparse.BooleanOptionalAction, 'help':'Overwrite existing appreciations on the website (including deleting them if they are not present in the CSV). Default is to ask.'})
        ]
        shared_args= ["group", "trimester"]
        args= lvs_get_args(arg_descs=arg_descs, shared_args= shared_args, description='Upload student appreciations from a csv file to an axess website.', required=["csv_fname"])
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
        s= open_session(args["user"], args["password"])
        send_apprs(s, args["csv_fname"], args["trimester"], args["group_name"],
                   ask_to_write= args["ask_to_write"], never_write= args["never_write"],
                   ask_to_delete= args["ask_to_delete"], never_delete= args["never_delete"])
        show_message("Done.")
    finally:
        if s is not None:
            s.close()

if __name__ == '__main__' :
    display_errors(main)

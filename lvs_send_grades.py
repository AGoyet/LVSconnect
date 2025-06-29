#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scripting for an Axess website.

Send grades from csv file to the website.
"""

from lvs_module import *

add_url("send_grades", "/vsn.main/WSCompetences/saveBatchEvaluations")
add_url("create_evaluation", "/vsn.main/WSCompetences/creerEvaluation")
add_url("modify_evaluation", "/vsn.main/WSCompetences/modifierDevoir")


# Returns a dict of evaluation_name : (colnum, max_grade, coefficient)
def get_evaluations_from_csv(csv_fname):
    rows = get_csv_rows(csv_fname)
    if len(rows) < 1:
        raise RuntimeError("Empty csv file")
    if len(rows) < 2:
        raise RuntimeError(
            "Unexpected csv file format (no second line with evaluation descriptions)"
        )
    evaluation_descs = {}
    for i in range(1, len(rows[1])):
        desc_s = rows[1][i]
        float_re = r"\d+(?:(?:\.|,)\d*)?"  # (?: ... ) is non capturing grouping
        float_group = "(" + float_re + ")"
        match = re.search("/" + float_group + " - Coef : " + float_group, desc_s)
        if match is None:
            continue
        max_grade = float(match.groups()[0].replace(",", "."))
        coefficient = float(match.groups()[1].replace(",", "."))
        desc = (i, max_grade, coefficient)
        evaluation_name = rows[0][i]
        if evaluation_name.strip() == "":
            raise RuntimeError(
                f'Detected a evaluation description "{desc}" in column {i+1} (starting from 1), but the cell above is empty (expected a valid evaluation name).'
            )
        if evaluation_name in evaluation_descs.keys():
            raise RuntimeError(
                f'Evaluation name "{evaluation_name}" appears multiple times in first row of csv file.'
            )
        evaluation_descs[evaluation_name] = desc
    print(
        "Found",
        len(evaluation_descs),
        "evaluations in the csv file: ",
        ", ".join(evaluation_descs.keys()),
    )
    return evaluation_descs


# "service_id" is 1-to-1 to group_name for a given teacher (there is a different notion
# of "group_id", which is independent from teachers, and used for messages).
# Grades are assigned to a given service_id (so that each teacher can assigne their own
# grades to each group)
@pronote.notimplemented
def create_evaluation(s, service_id, trimester, evaluation_name, desc, hidden=False):
    url = get_url("create_evaluation")
    payload = '{"evaluation":{"dateDevoir":"","competenceIds":[],"titre":"","publie":true,"coefficient":0,"enseignantId":0,"noteMaximalEvaluation":20,"typeEvaluation":"NOTE","serviceId":0,"periodeId":0}}'
    json_payload = json.loads(payload)
    json_eval = json_payload["evaluation"]
    teacher_id = get_teacher_id(s)
    (_, max_grade, coefficient) = desc
    json_eval["dateDevoir"] = get_current_date_s()
    json_eval["titre"] = evaluation_name
    json_eval["coefficient"] = correct_number_style(coefficient)
    json_eval["enseignantId"] = teacher_id
    json_eval["noteMaximalEvaluation"] = correct_number_style(max_grade)
    json_eval["serviceId"] = service_id
    json_eval["periodeId"] = trimester
    if hidden:
        json_eval["publie"] = False
    print("Creating", evaluation_name)
    r = s.post(url, json=json_payload)
    r.raise_for_status()
    json_created = r.json()
    evaluation_id = json_created["id"]
    desc_full = desc + (evaluation_id,)
    return desc_full


@pronote.notimplemented
def modify_evaluation_desc(
    s, json_grades, service_id, trimester, evaluation_name, max_grade, coefficient
):
    devoir = None
    for devoir in json_grades["evaluations"]:
        if devoir["titre"] == evaluation_name:
            break
    assert devoir
    # The json "devoir" will be our basis for the payload.
    # We first need to trim the keys we don't need from it.
    payload_keys = {
        "id",
        "verrouille",
        "sousServiceId",
        "publie",
        "enseignantId",
        "noteMaximalEvaluation",
        "periodeId",
        "titre",
        "typeEvaluation",
        "competenceIds",
        "serviceId",
        "coefficient",
        "dateDevoir",
        "typeDevoir",
    }
    json_eval = devoir.copy()
    for k in devoir:
        if not k in payload_keys:
            del json_eval[k]
    # Now add the keys not in devoir
    json_eval["competenceIds"] = []
    json_eval["periodeId"] = trimester
    json_eval["serviceId"] = service_id
    # Now modify the remaining keys to match csv desc.
    json_eval["noteMaximalEvaluation"] = max_grade
    json_eval["coefficient"] = coefficient
    json_payload = json.loads("{}")
    json_payload["evaluation"] = json_eval
    print("Modifying max grade or coefficient for", evaluation_name)
    r = s.post(get_url("modify_evaluation"), json=json_payload)
    r.raise_for_status()


# returns a dict of evaluation_name : (col, max_grade, coefficient, evaluation_id)
@pronote.reimplemented
def get_evaluation_website_descs(json_grades):
    website_descs = {
        devoir["titre"]: (
            devoir["noteMaximalEvaluation"],
            devoir["coefficient"],
            devoir["id"],
        )
        for devoir in json_grades["evaluations"]
    }
    return website_descs


# Grades and coefficients are strings, which can represent float (but not necessarly)
# If they represent float, they should be considered equal if the floats are
def float_or_repr_equality(g1, g2):
    # Identify "" and None (so as not to uselessly overwrite None with "").
    if g1 is None:
        g1 = ""
    if g2 is None:
        g2 = ""
    if g1 == g2:
        # string equality
        return True
    if g1 is None or g2 is None:
        # we already know g1 != g2
        return False
    try:
        g1f = float(str(g1).replace(",", "."))
        g2f = float(str(g2).replace(",", "."))
        return g1f == g2f
    except ValueError:
        # At leaset one is not a float, and they are not string equal
        return False


# Returns (created_flag, evaluation_descs_full),
# Where evaluation_descs_full is a dict of evaluation_name : (col, max_grade, coefficient, evaluation_id)
def get_evaluation_id_and_create_evaluations(
    s,
    service_id,
    trimester,
    json_grades,
    evaluation_descs,
    create_evaluations=False,
    hidden=False,
):
    created_flag = False
    evaluation_descs_full = {}
    evaluations_not_in_website = []
    evaluations_with_new_desc = []
    website_descs = get_evaluation_website_descs(json_grades)
    evaluations_not_in_csv = set(website_descs.keys())
    website_descs = get_evaluation_website_descs(json_grades)
    for evaluation_name, desc in evaluation_descs.items():
        if evaluation_name in website_descs.keys():
            max_grade, coefficient, evaluation_id = website_descs[evaluation_name]
            # tuple addition (new tuple with one more element)
            evaluation_descs_full[evaluation_name] = desc + (evaluation_id,)
            if (not float_or_repr_equality(max_grade, desc[1])) or (
                not float_or_repr_equality(coefficient, desc[2])
            ):
                evaluations_with_new_desc.append(evaluation_name)
            evaluations_not_in_csv.remove(evaluation_name)
        else:
            evaluations_not_in_website.append(evaluation_name)
    if evaluations_not_in_csv:
        print(
            f"WARNING: {len(evaluations_not_in_csv)} evaluation(s) are present on the website but not in the csv file: {', '.join(evaluations_not_in_csv)}"
        )
    if evaluations_not_in_website:
        print(
            f"Found {len(evaluations_not_in_website)} evaluation(s) not present on the website: {', '.join(evaluations_not_in_website)}"
        )
        if create_evaluations:
            first_it = True
            for evaluation_name in evaluations_not_in_website:
                if first_it:
                    first_it = False
                else:
                    time.sleep(0.1)
                desc = evaluation_descs[evaluation_name]
                desc_full = create_evaluation(
                    s, service_id, trimester, evaluation_name, desc, hidden=hidden
                )
                evaluation_descs_full[evaluation_name] = desc_full
                created_flag = True
    if created_flag:
        print(
            "Evaluation(s) successfully created. Note that their creation date has been set to today."
        )
    if evaluations_with_new_desc:
        print(
            f"Found {len(evaluations_with_new_desc)} evaluation(s) with max grade or coefficient different than on the website: {', '.join(evaluations_with_new_desc)}"
        )
        if create_evaluation:
            dialog_s = f"Upload the modified max grades and coefficients? ({len(evaluations_with_new_desc)} evaluation(s) will be modified.)"
            answer = input_Yn(dialog_s)
            if answer:
                first_it = True
                for evaluation_name in evaluations_with_new_desc:
                    if first_it:
                        first_it = False
                    else:
                        time.sleep(0.1)
                    (col, max_grade, coefficient) = evaluation_descs[evaluation_name]
                    modify_evaluation_desc(
                        s,
                        json_grades,
                        service_id,
                        trimester,
                        evaluation_name,
                        max_grade,
                        coefficient,
                    )
    return (created_flag, evaluation_descs_full)


def str_of_translated_list(d, L):
    return ", ".join([d[a] for a in L])


# new_grades_dict : { evaluation_id : { student_id : new_grade } }
@pronote.reimplemented
def send_grades_dopost(s, trimester, json_grades, service_id, new_grades_dict):
    payload = '{"saisies":[],"devoirs":[],"bonus":[],"idservice":0,"idperiode":0}'
    json_payload = json.loads(payload)
    json_payload["idperiode"] = trimester
    json_payload["idservice"] = service_id
    for evaluation_id in new_grades_dict:
        json_payload["devoirs"].append(evaluation_id)
    payload_saisie = '{"ideleve":0,"competences":[],"noteToSave":true,"competencesToSave":false,"iddevoir":0,"note":""}'
    # This template will be copied multiple times.
    json_payload_saisie_template = json.loads(payload_saisie)
    for evaluation_id in new_grades_dict:
        for student_id in new_grades_dict[evaluation_id]:
            new_grade = new_grades_dict[evaluation_id][student_id]
            json_payload_saisie = json_payload_saisie_template.copy()
            json_payload_saisie["ideleve"] = student_id
            json_payload_saisie["iddevoir"] = evaluation_id
            json_payload_saisie["note"] = new_grade
            json_payload["saisies"].append(json_payload_saisie)
    # Do request
    url = get_url("send_grades")
    r = s.post(url, json=json_payload)
    r.raise_for_status()


def send_grades(
    s,
    csv_fname,
    trimester,
    group_name,
    create_evaluations=False,
    hidden=False,
    ask_to_write=True,
    never_write=False,
    ask_to_delete=True,
    never_delete=False,
):
    evaluation_descs = get_evaluations_from_csv(csv_fname)
    json_groups = get_groups(s)
    service_id = get_service_id(group_name, json_groups)
    json_grades = get_grades(s, service_id, trimester)

    created_flag, evaluation_descs_full = get_evaluation_id_and_create_evaluations(
        s,
        service_id,
        trimester,
        json_grades,
        evaluation_descs,
        create_evaluations=create_evaluations,
        hidden=hidden,
    )
    # Redownload grades after creating a evaluation (the web app also does this)
    # (This can also avoid uploading a lot of empty grades.)
    if created_flag:
        json_grades = get_grades(s, service_id, trimester)

    error_flag, row_of_student_id = match_students_to_rows(s, csv_fname, json_grades)
    grades_website = grades_dict_of_json(json_grades)
    student_names = get_student_names_of_ids(json_grades)
    # A "deleted" grade is when we replace something with ''
    delete_count = 0
    overwrite_count = 0
    write_count = 0
    # A dict of evaluation_id : { student_id : new_grade }
    new_grades_dict = {}
    for evaluation_name, (
        evaluation_col,
        max_grade,
        coefficient,
        evaluation_id,
    ) in evaluation_descs_full.items():
        write_list = []
        overwrite_list = []
        delete_list = []
        for student_id, row in row_of_student_id.items():
            grade_csv = row[evaluation_col]
            # Clip grades to max_grade
            try:
                g = float(str(grade_csv).replace(",", "."))
                assert g >= 0  # csv parser shouldn't produce < 0
                if g > max_grade:
                    print(
                        f'Warning: In evaluation "{evaluation_name}", grade "{grade_csv}" in csv file is greater than the maximum grade of {max_grade}. Replacing it with {max_grade}'
                    )
                    grade_csv = str(correct_number_style(max_grade))
            except (ValueError, TypeError):
                pass  # Leave pure str grades alone
            if (evaluation_id, student_id) in grades_website:
                grade_web = grades_website[(evaluation_id, student_id)]
                if float_or_repr_equality(grade_web, grade_csv):
                    # Don't fill the request with overwrites of the existing values
                    continue
                if not grade_csv:
                    # We know that grade_web != grade_csv, so this would be a deletion
                    delete_list.append(student_id)
                    if never_delete:
                        # Do not put deletes in the request if this option is True
                        continue
                elif grade_web:
                    overwrite_list.append(student_id)
            write_list.append(student_id)
            # Add to new_grades_dict
            if not evaluation_id in new_grades_dict:
                new_grades_dict[evaluation_id] = {}
            new_grades_dict[evaluation_id][student_id] = grade_csv
        if len(write_list) > 0:
            print(
                f'Evaluation "{evaluation_name}": {len(write_list)} grade(s) to upload.'
            )
            print(students_preview(student_names, write_list))
            write_count += len(write_list)
        if len(overwrite_list) > 0:
            print(
                f'Warning: in evaluation "{evaluation_name}": {len(overwrite_list)} grade(s) to upload would OVERWRITE an existing grade on website.'
            )
            print(students_preview(student_names, overwrite_list))
            overwrite_count += len(overwrite_list)
        if len(delete_list) > 0 and not never_delete:
            print(
                f'Warning: in evaluation "{evaluation_name}": {len(delete_list)} grade(s) to upload would DELETE an existing grade on website.'
            )
            print(students_preview(student_names, delete_list))
            delete_count += len(delete_list)
    if write_count == 0:
        print("No grades need to be uploaded.")
        return
    if never_write:
        print("Not uploading as per option.")
        return
    dialog_s = ""
    if delete_count + overwrite_count > 0 and ask_to_delete:
        dialog_s += "Uploading grades will "
        if delete_count:
            dialog_s += f"DELETE {delete_count}"
        if delete_count and overwrite_count:
            dialog_s += " and "
        if overwrite_count:
            dialog_s += f"OVERWRITE {overwrite_count}"
        dialog_s += " grade(s) on the website.\n"
    if ask_to_write:
        dialog_s += f"Uploading will write {write_count} grade(s) to the website.\n"
    if dialog_s != "":
        answer = input_Yn(dialog_s + "Continue?")
        if not answer:
            print("Aborting.")
            if delete_count > 0 and ask_to_delete:
                print(
                    "You can upload grades without deleting existing ones with the --no-delete option."
                )
            return
    print("Uploading...")
    # Actual uploading
    send_grades_dopost(s, trimester, json_grades, service_id, new_grades_dict)


def main():
    try:
        s = None
        arg_descs = [
            (
                ("csv_fname",),
                {
                    "metavar": "CSV_FILE",
                    "nargs": "?",
                    "help": 'The csv file in which grades will be read. Can be omitted if there is only one csv file in the working directory. The program expects the file to be in the format exported by the website. In particular, evaluation names should be on the first line, with the cell below each name describing the maximum grade and grade multiplier as in the following: "/10 - Coef : 0.5".',
                },
            ),
            #            (('-e', '--evaluation'), {
            #                        'help':'If provided, only this evaluation (evaluation) will be modified on the website.'}),
            (
                ("--write",),
                {
                    "action": argparse.BooleanOptionalAction,
                    "help": "Write grades to the website. Default is to ask. Note that this is independent from creating new evaluations. However, --no-write implies --no-delete.",
                },
            ),
            (
                ("--delete", "--overwrite"),
                {
                    "action": argparse.BooleanOptionalAction,
                    "help": "Overwrite existing grades on the website (including deleting them if they are not present in the CSV). Default is to not delete. This does not delete evaluations.",
                },
            ),
            (
                ("--create",),
                {
                    "action": argparse.BooleanOptionalAction,
                    "help": "Create or do not create evaluations if they do not exist on the website. Default is to create.",
                },
            ),
            (
                ("--hidden",),
                {
                    "action": argparse.BooleanOptionalAction,
                    "help": 'When creating evaluations, keep it hidden from students (corresponds to the "publish" option on the website). Default is to publish the evaluation. Does not affect evaluations which already exist on the website.',
                },
            ),
        ]
        shared_args = ["group", "trimester"]
        args = lvs_get_args(
            arg_descs=arg_descs,
            shared_args=shared_args,
            description="Upload grades from a csv file to a specific axess website.",
            required=["csv_fname"],
        )
        if args["write"] is None:
            args["ask_to_write"] = True
            args["never_write"] = False
        else:
            args["ask_to_write"] = False
            args["never_write"] = not args["write"]
            if args["write"] == False:
                args["delete"] = True
        if args["delete"] is None:
            args["ask_to_delete"] = False
            args["never_delete"] = True
        else:
            args["ask_to_delete"] = False
            args["never_delete"] = not args["delete"]
        if args["create"] is None:
            args["create"] = True
        if args["hidden"] is None:
            args["hidden"] = False
        s = open_session_from_args(args)
        send_grades(
            s,
            args["csv_fname"],
            args["trimester"],
            args["group_name"],
            create_evaluations=args["create"],
            hidden=args["hidden"],
            ask_to_write=args["ask_to_write"],
            never_write=args["never_write"],
            ask_to_delete=args["ask_to_delete"],
            never_delete=args["never_delete"],
        )
    finally:
        if s is not None:
            close_session(s)


if __name__ == "__main__":
    display_errors(main)
    show_message("Done.")

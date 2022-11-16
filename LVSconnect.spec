# -*- mode: python ; coding: utf-8 -*-

'''
This .spec file creates multiple executables in a single directory, so that they all share the same libraries and files.

The variables project_name will be used for that single directory; the names in sub_names should each have a .spec file in the current directory (created beforehand with the pyi-makespec program).

It works by running all sub .spec files, but intercepting the COLLECT function. After that, a single COLLECT call is made using all the args for the intercepted calls.

This is a generalisation of the method described in https://www.zacoding.com/en/post/pyinstaller-create-multiple-executables.
'''

# Customize this
project_name= "LVSconnect"
sub_names= ["lvs_attendance", "lvs_send_grades"]


block_cipher = None

all_collect_args= []
for name in sub_names:

    with open(name + ".spec") as f:
        spec_content= f.read()

    def replaced_collect(*args, **kwargs):
        global collect_args
        collect_args= args

    l= locals().copy()
    g= globals().copy()

    g["COLLECT"]= replaced_collect
    l["COLLECT"]= replaced_collect

    exec(spec_content, g, l)

    all_collect_args+= collect_args


coll= COLLECT(
    *all_collect_args,
    strip=False,
    upx=True,
    upx_exclude=[],
    name= project_name
    )

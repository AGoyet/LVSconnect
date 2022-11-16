python.exe -m pip install --upgrade pip
python.exe -m pip install -r requirements.txt


pyi-makespec --console --hidden-import babel.numbers lvs_attendance.py
pyi-makespec --console lvs_send_grades.py

pyinstaller LVSconnect.spec

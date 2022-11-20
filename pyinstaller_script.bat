python -m pip install --upgrade pip
python -m pip install -r requirements.txt

pyi-makespec --console --hidden-import babel.numbers lvs_attendance.py
pyi-makespec --console lvs_send_grades.py
pyi-makespec --console lvs_send_appreciations.py

pyinstaller --noconfirm LVSconnect.spec

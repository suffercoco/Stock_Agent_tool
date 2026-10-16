1. set env to upload file to nas

```Shell
# Mac command
echo "export STOCH_NAS_SHARE=''" >> ~/.zshrc
echo "export STOCH_NAS_USER=''" >> ~/.zshrc
echo "export STOCH_NAS_PASSWORD=''" >> ~/.zshrc
```

```Shell
# Windows command
setx STOCH_NAS_SHARE "" 
setx STOCH_NAS_USER "" 
setx STOCH_NAS_PASSWORD ''
```
# n8n
powershell -Command "$env:STOCH_NAS_SHARE=''; $env:STOCH_NAS_USER=''; $env:STOCH_NAS_PASSWORD=''; e:/project/Stoch_Agent_tool/.venv/Scripts/python.exe e:/project/Stoch_Agent_tool/upload_to_nas.py"

2. set coordination for different solution, the coordination fit 1080p solution by default. Running get_mouse_coordination.py to get you own coordination under screen solution.
3. if data get too late when over 00:00, use change_time_slot.py to change date nto same day.
4. show_rows.py will ez get last 10 or whatever you want data in db to inspect data capture time.

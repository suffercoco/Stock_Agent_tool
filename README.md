1. set env to upload file to nas

```Shell
# Mac command
echo "export STOCH_NAS_SHARE='stock'" >> ~/.zshrc
echo "export STOCH_NAS_USER=''" >> ~/.zshrc
echo "export STOCH_NAS_PASSWORD=''" >> ~/.zshrc
```

```Shell
# Windows command
setx STOCH_NAS_SHARE "stock" 
setx STOCH_NAS_USER "stock" 
setx STOCH_NAS_PASSWORD 'e:3YFh,u'
```

2. set coordination for different solution, the coordination fit 1080p solution by default. Running get_mouse_coordination.py to get you own coordination under screen solution.
3. if data get too late when over 00:00, use change_time_slot.py to change date nto same day.
4. show_rows.py will ez get last 10 or whatever you want data in db to inspect data capture time.

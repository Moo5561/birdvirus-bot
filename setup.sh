#!/bin/bash
main() {
 echo "-- Birdvirus Bot --"
 echo -n " • Checking if files are up to date..."
 # birdvirus.db stopped being tracked in the "reorganize repo" change. pulling that
 # commit onto a host where it is still tracked deletes the live database from the
 # working tree. untrack it first so the pull leaves the file alone, and keep a
 # copy either way. safe to run forever: both commands no-op once it is untracked.
 if [ -f birdvirus.db ]; then
   cp -f birdvirus.db birdvirus.db.bak 2>/dev/null
   git rm --cached --quiet birdvirus.db > /dev/null 2>&1
 fi
 git pull --ff-only > /dev/null
 if [ ! -f birdvirus.db ] && [ -f birdvirus.db.bak ]; then
   mv birdvirus.db.bak birdvirus.db
   echo -e "\r ! restored birdvirus.db after the update removed it            "
 fi
 if [ $? -ne 0 ]; then
    echo -e "\r ✗ An error occurred in the update checker, ignoring"
 fi
 echo -e "\r ✓ Everything is up to date!                   "
 echo " • Setting up venv..."
 read -r -p $"\nEnter where your venv is located, or "new" for a new venv in ./.venv: "
 echo -e "\e[1A\e[K"
 if [ $REPLY == "new" ]; then
  python -m venv ./.venv > /dev/null
  if [ $? -ne 0 ]; then
    echo -e -n "\r ✗ An error occurred while creating the venv."
    exit
  fi
  $REPLY="./.venv"
  echo -e -n "\r ✓ venv created"
 fi
 source $REPLY/bin/activate
 echo -e "\r ✓ venv activated"
 echo " • Installing dependencies..." 
 pip install -r requirements.txt
 if [ $? -ne 0 ]; then
    echo " ✗ An error occurred while installing dependencies required for the bot."
    exit
 fi
 echo " ✓ Dependencies installed!"
 echo -n " • Installing Chromium for Playwright..."
 playwright install chromium > /dev/null
 echo -e "\r ✓ Chromium installed!"
 echo " ✓ Setup complete!"
}
main

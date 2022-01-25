#!/bin/sh
# this script is used to boot a Docker container
source venv/bin/activate
# bash wait-for-it.sh ${MYSQL_SERVER} -t 60
sleep 0
while true; do
    ### this is to avoid migrations conflicts if DB already exists
    DB_EXISTENCE=$( sqlite3 DB/app.db "SELECT EXISTS (SELECT * FROM sqlite_master WHERE type='table' AND name='user');" )
    if [ "$DB_EXISTENCE" -ne 0 ]; then
      echo "SQL databse exists";
    else
      echo "creating SQL databse ...";
      flask db init
    fi
    flask db migrate
    flask db upgrade
    if [[ "$?" == "0" ]]; then
        break
    fi
    echo Deploy command failed, retrying in 5 secs...
    sleep 5
done
exec gunicorn -b 0.0.0.0:5000 --access-logfile - --error-logfile - main:app --timeout=60

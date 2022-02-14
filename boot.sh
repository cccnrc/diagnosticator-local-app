#!/bin/sh
# this script is used to boot a Docker container
source venv/bin/activate
# bash wait-for-it.sh ${MYSQL_SERVER} -t 60
sleep 0
while true; do
    ### this is to avoid migrations conflicts if DB already exists
    DB_EXISTENCE=$( sqlite3 /home/diagnosticator/DB/app.db "SELECT EXISTS (SELECT * FROM sqlite_master WHERE type='table' AND name='user');" )
    if [ "$DB_EXISTENCE" -ne 0 ]; then
      echo " -> SQL databse exists";
      ### this is to avoid the revision mismatch
      DB_REVISION=$( sqlite3 /home/diagnosticator/DB/app.db "SELECT version_num FROM alembic_version;" )
      sqlite3 /home/diagnosticator/DB/app.db "DROP TABLE IF EXISTS alembic_version;"
      if [ ! -z $DB_REVISION ]; then
        echo "  --> revision: ${DB_REVISION} DROPPED";
      fi
    else
      echo " -> creating SQL databse ...";
    fi
    ### check migrations
    if [ ! -d /home/diagnosticator/migrations ]; then
      echo " -> migrations does not exists, initiating DB ..."
      flask db init
    else
      echo " -> migrations exists, skipping DB init ..."
    fi
    ### the rest should simply have no effect in case it already exists
    flask db migrate
    if [ "$DB_EXISTENCE" -ne 0 ]; then
      flask db stamp head
    fi
    flask db upgrade
    if [[ "$?" == "0" ]]; then
        break
    fi
    echo Deploy command failed, retrying in 5 secs...
    sleep 5
done
exec gunicorn -b 0.0.0.0:5000 --access-logfile - --error-logfile - main:app --timeout=60

### FLASK LOCAL
```
APP_DIR=<your-app-DIR>
# atom venv/bin/activate      ### store ENV variables
source venv/bin/activate
flask run
```

### GITHUB
```
atom .gitignore
git init
git add .
git commit -m "diagnosticator tutorial repo - v0.0"
git branch -M development
git remote add origin https://github.com/cccnrc/diagnosticator-tutorial.git
git push -u origin development
```


### run DOCKERs
```
UPLOAD="$(pwd)/upload"

### DX-VEP: /home/enrico/columbia/diagnosticator-AWS/docker-VEP-alpine
docker run --rm -d --name DX-VEP \
  -v $UPLOAD:/home/VEP_INPUT \
  alpine-vep:0.0 /bin/bash

docker run --rm -d --name DX-ASILO \
  -v $UPLOAD:/INPUT \
  asilo:0.0 /bin/bash

### to have REDIS as well
docker run --name redis-01 --rm \
            --dns 8.8.8.8 \
            -d -p 6377:6379 redis:latest


# redis-cli -p 6379

### to have a RQ-WORKER as well
source venv/bin/activate
rq worker diagnosticator-tasks --url redis://127.0.0.1:6377



docker stop DX-VEP DX-ASILO redis-01


docker exec -it DX-VEP /bin/bash
```








```
###################################
####### build this docker #########
###################################
docker build --no-cache -t cccnrc/diagnosticator:0.11 .
docker push cccnrc/diagnosticator:0.11


################################
####### DOCKER-COMPOSE #########
################################
docker-compose rm -v
docker volume rm diagnosticator-local-simple-algorithm-development-02-nomysql_DX-UPLOAD
docker volume rm diagnosticator-local-simple-algorithm-development-02-nomysql_DX-DB
docker-compose up --build --force-recreate --renew-anon-volumes
```

from flask import render_template, redirect, url_for, flash, request, current_app
from werkzeug.urls import url_parse
from app import db
from app.auth import bp
import datetime
from app.auth.forms import InsertPasswordRequestForm
from app.auth.functions import check_server_user, check_server_key, development_check_server_user
from flask_login import login_required, current_user, logout_user, login_user
from app.decorators import server_valid_authentication_required
from app.models import User
import requests
import os
import json


####################################################################
############ this is to check central DB authentication ############
####################################################################
@bp.route('/authenticate_on_server', methods=['GET', 'POST'])
def authenticate_on_server( ):
    next = request.args.get('next')
    if not next:
        next = url_for('main.index')
    ### if DEVELOPMENT_TESTING create a fake user and a fake token
    if current_app.config['DEVELOPMENT_TESTING'] == True:
        # flash( 'creating fake user: tester-00', 'info' )
        development_check_server_user()
        return redirect( next )
    ### if NOT DEVELOPMENT_TESTING check server authentication
    server_url = current_app.config['SERVER_ADDRESS']
    ### check stored credentials first
    try:
        DIAGNOSTICATOR_LOCAL_LIB = '/usr/lib/diagnosticator'
        if os.path.isfile(os.path.join(DIAGNOSTICATOR_LOCAL_LIB, 'credentials.json')):
            STORED_CREDENTIALS_FILE = os.path.join(DIAGNOSTICATOR_LOCAL_LIB, 'credentials.json')
        else:
            STORED_CREDENTIALS_FILE = os.path.join(current_app.config['BASEDIR'], 'DB', 'credentials.json')
        if os.path.isfile(STORED_CREDENTIALS_FILE):
            CREDENTIALS = json.load(open(STORED_CREDENTIALS_FILE))
            TOKEN = CREDENTIALS['token']
            EXP = CREDENTIALS['exp']
            if EXP:
                EXP_TIME = datetime.datetime.strptime(EXP, '%m/%d/%y %H:%M:%S')
                ### if tokn is still valid
                if EXP_TIME > datetime.datetime.utcnow() + datetime.timedelta(seconds=60):
                    headers = { 'Authorization': 'Bearer {0}'.format(TOKEN) }
                    r = requests.post( '{0}/api/get_username'.format(server_url), headers = headers )
                    if r:
                        if 'username' in r.json():
                            try:
                                user = User.query.filter_by( server_username = r.json()['username'] ).first()
                            except:
                                user = User( server_username = r.json()['username'] )
                                db.session.add(user)
                            user.server_token = TOKEN
                            user.server_token_expiration = EXP_TIME
                            user.authenticated_on = datetime.datetime.utcnow()
                            db.session.commit()
                            login_user(user)
                            flash( 'logged in with stored token', 'success' )
                            return redirect( next )
    except:
        pass
    ### if it fails with STORED_CREDENTIALS_FILE
    form = InsertPasswordRequestForm()
    if form.validate_on_submit():
        if check_server_user( form.username.data, form.password.data ):
            return redirect( next )
    text_dict = ({
            'title' : 'Authenticate on Central Website',
            'text' : 'Insert your Central Diagnosticator Website credentials:',
            'text_category' : 'warning',
            'link' : current_app.config['SERVER_ADDRESS'],
            'link_text' : 'Diagnosticator Central Website'
    })
    return( render_template('insert_DXcator.html',
                text_dict = text_dict,
                form=form
            ))


@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))

####################################################################
####################################################################
####################################################################

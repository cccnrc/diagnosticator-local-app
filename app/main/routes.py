from datetime import datetime
from flask import render_template, flash, redirect, url_for, request, g, \
    jsonify, current_app, abort, Markup
from app import db
from app.main import bp
from flask_login import login_user, logout_user, current_user, login_required
from app.decorators import server_valid_authentication_required, project_required, send_variants, \
    project_data_required, update_known_variants, update_known_variants_redis_DB
from flask import session
# import mongodb_functions
import redis_functions
import app.main.diagnosticator_rendering_functions as diagnosticator_rendering_functions
from werkzeug.utils import secure_filename
import os
import functools
from app.models import Notification, User, Message, KnownVariants
from app.main.forms import NewProjectForm
import requests
from uuid import getnode as get_mac
from app.variant_functions import send_local_variants, get_known_variants, get_all_known_variants, get_report_statuses, send_local_var, get_server_new_messages_dict
from app.main.forms import SearchForm, FilterForm
from flask_paginate import Pagination, get_page_args


######################################################################
########################## PREPROCESSING #############################
######################################################################
@bp.context_processor
def example():
    '''
        this decorator allows to pass a function to all templates
        to access it access the K directly in j2
    '''
    user_dict = ({
        'classes_dict' : diagnosticator_rendering_functions.get_classes_dict(),
        'ACMG_classes_dict' : diagnosticator_rendering_functions.get_ACMG_classes_dict(),
        'ACMG_strength_dict' : diagnosticator_rendering_functions.get_ACMG_strength_dict(),
        'ACMG_subclass_dict' : diagnosticator_rendering_functions.get_ACMG_subclass_dict(),
        'abbreviations_dict' : diagnosticator_rendering_functions.get_variant_page_conversion(),
        'inheritance_abbreviations_dict' : diagnosticator_rendering_functions.get_inheritance_abbreviations_dict()
    })
    return( user_dict )

@bp.before_app_request
def before_request():
    '''
        this is executed BEFORE any request
    '''
    if current_user.is_anonymous:
        pass
    else:
        if current_user.is_authenticated:
            current_user.last_seen = datetime.utcnow()
            db.session.commit()
            g.search_form = SearchForm()



@bp.route('/tutorial', methods=['GET'])
def tutorial():
    SERVER_ADDRESS = current_app.config['SERVER_ADDRESS']
    return render_template('tutorial_DXcator.html', title='Tutorial',
                    SERVER_ADDRESS = SERVER_ADDRESS
                    )


@bp.route('/commandVEP', methods=['GET'])
def commandVEP():
    SERVER_ADDRESS = current_app.config['SERVER_ADDRESS']
    return render_template('commandVEP_DXcator.html', title='Tutorial',
                    SERVER_ADDRESS = SERVER_ADDRESS
                    )


######################################################################
############################# HOMEPAGE ###############################
######################################################################
@bp.route('/', methods=['GET', 'POST'])
@bp.route('/index', methods=['GET', 'POST'])
def index():
    SERVER_ADDRESS = current_app.config['SERVER_ADDRESS']
    return render_template('index_tutorial_DXcator.html', SERVER_ADDRESS = SERVER_ADDRESS, title='Home')


@bp.route('/project', methods=['GET', 'POST'])
@server_valid_authentication_required
@login_required
def project():
    '''
        this is the function to create a new project
    '''
    user = User.query.filter_by( server_username = current_user.server_username ).first_or_404()
    form = NewProjectForm(
        projectID = user.project_name,
        project_description = user.project_description,
        project_DX = user.project_diagnosis,
        project_ICDS10 = user.project_icds_code,
        project_assembly = user.project_assembly
    )
    if form.validate_on_submit() :
        ### insert project in DB
        user.project_name = form.projectID.data
        user.project_description = form.project_description.data
        user.project_diagnosis = form.project_DX.data
        user.project_icds_code = form.project_ICDS10.data
        user.project_assembly = form.project_assembly.data
        user.project_created_on = datetime.utcnow()
        db.session.commit()
        flash("Project {0} successfully created!".format( user.project_name ), 'success')
        return( redirect( url_for('main.upload')))
    return( render_template('project_tutorial_DXcator.html',
                                title='Project',
                                form = form
                                ))


##################################################################
##################### MESSAGE-NOTIFICATION  ######################
##################################################################
@bp.route('/messages')
@login_required
@server_valid_authentication_required
def messages():
    SERVER_ADDRESS = current_app.config['SERVER_ADDRESS']
    current_user.last_message_read_time = datetime.utcnow()
    current_user.add_notification('unread_message_count', 0)
    db.session.commit()
    page = request.args.get('page', 1, type=int)
    messages = current_user.messages_received.order_by(
        Message.timestamp.desc()).paginate(
            page, current_app.config['MESSAGE_PER_PAGE'], False)
    next_url = url_for('main.messages', page=messages.next_num) \
        if messages.has_next else None
    prev_url = url_for('main.messages', page=messages.prev_num) \
        if messages.has_prev else None
    return render_template('messages_tutorial_DXcator.html', messages=messages.items,
                            SERVER_ADDRESS = SERVER_ADDRESS,
                            next_url=next_url, prev_url=prev_url)


from app.decorators import get_messages

@bp.route('/notifications')
@login_required
@get_messages
#@send_variants
def notifications():
    since = request.args.get('since', 0.0, type=float)
    if current_user.is_authenticated:
        notifications = current_user.notifications.filter(
                            Notification.timestamp > since).order_by(Notification.timestamp.asc())
        return jsonify([{
            'name': n.name,
            'data': n.get_data(),
            'timestamp': n.timestamp
        } for n in notifications])


#########################################################################
######################## UPDATE LOCAL KNOWN DB  #########################
#########################################################################
### this page merged with the intervalId JS function in base_DXcator.html page allows to update the local DB periodically
from app.variant_functions import update_known_variants_local_DB

@bp.route('/update_known_variants')
# @server_valid_authentication_required
def update_known_variants():
    if current_user.is_anonymous or current_app.login_manager._login_disabled or current_app.config['DEVELOPMENT_TESTING'] == True:
        return jsonify({ 'variants' : 0 })
    else:
        if current_user.is_authenticated:
            NUM_UPDATED = update_known_variants_local_DB()
        return jsonify({ 'variants' : NUM_UPDATED })


##################################################################
######################## UPLOAD-ANALYZE  #########################
##################################################################
@bp.route('/upload')
@project_required
@login_required
@server_valid_authentication_required
def upload():
    # flash(Markup('This must be a VEP annotated file, please read <a href="https://diagnosticator-000.ew.r.appspot.com" class="alert-link">documentation</a> for more info'), 'warning')
    files = os.listdir(current_app.config['UPLOAD_FOLDER'])
    PROJ_ASSEMBLY = current_user.project_assembly
    SERVER_ADDRESS = current_app.config['SERVER_ADDRESS']
    SERVER_TUTORIAL_ADDRESS = current_app.config['SERVER_TUTORIAL_ADDRESS']
    return( render_template('upload_tutorial_DXcator.html',
                                files=files,
                                PROJ_ASSEMBLY = PROJ_ASSEMBLY,
                                SERVER_ADDRESS = SERVER_ADDRESS,
                                SERVER_TUTORIAL_ADDRESS = SERVER_TUTORIAL_ADDRESS
                            ) )


@bp.route('/upload_files', methods=['POST', 'GET'])
@project_required
@login_required
@server_valid_authentication_required
def upload_files():
    uploaded_file = request.files[ 'file' ]
    filename = secure_filename(uploaded_file.filename)
    if filename != '':
        file_ext = os.path.splitext(filename)[1]
        if file_ext not in current_app.config['ALLOWED_EXTENSIONS']:
            abort(400)
        uploaded_file.save(os.path.join( current_app.config['UPLOAD_FOLDER'], filename))
    return( redirect( url_for( 'main.upload' ) ) )


@bp.route('/pre_analyzeVCF/<filename>', methods=['POST', 'GET'])
@project_required
@login_required
@server_valid_authentication_required
def pre_analyzeVCF( filename ):
    SERVER_ADDRESS = current_app.config['SERVER_ADDRESS']
    body_dict = ({
        'line1' : {
                    'text' : 'Are you sure you want to analyze this file?',
                    'color' : 'grey',
                    'weight' : 'bold',
                    'size' : '100%'
                   },
        'line2' : {
                    'text' : 'If results were already generated for this project they will be overwritten',
                    'color' : 'red',
                    'weight' : 'bold',
                    'size' : '80%'
                   }
    })
    if 'choice' in request.form:
        choice = request.form['choice']
        if choice == 'Yes':
            current_user.project_variant_sent = False
            db.session.commit()
            return( redirect( url_for('main.analyzeVCF', filename = filename )))
        else:
            return( redirect( url_for('main.upload' )))
    return( render_template( 'yesNo_DXcator.html', body_dict = body_dict, SERVER_ADDRESS = SERVER_ADDRESS ))


from app.variant_functions import get_known_variants_from_DB

@bp.route('/analyzeVCF/<filename>')
@project_required
@login_required
@server_valid_authentication_required
def analyzeVCF( filename ):
    ### pull known variants from server
    # known_dict = get_known_variants()
    ### pull known variants from local DB
    known_dict = get_known_variants_from_DB()
    file_path = os.path.join( current_app.config['UPLOAD_FOLDER'], filename )
    ### this function creates the 3 dictionaries from the input VCF file
    if current_user.get_task_in_progress('analyzeVCF_task'):
        flash('An analyze VCF task is currently in progress. Wait it to finish...', 'warning')
    else:
        current_user.launch_task( 'analyzeVCF_task', 'Analyzing VCF {}...'.format( filename ), file_path, known_dict, url = current_app.config['REDIS_URL'], database = 2, URL_RESULTS = str(url_for('main.patient_result')) )
        db.session.commit()
    return( redirect( url_for( 'main.upload' ) ) )

from app.main.forms import consequence_choices

@bp.route('/filterVCF/<filename>', methods=['POST', 'GET'])
@project_required
@login_required
@server_valid_authentication_required
def filterVCF( filename ):
    file_path = os.path.join( current_app.config['UPLOAD_FOLDER'], filename )
    SERVER_ADDRESS = current_app.config['SERVER_ADDRESS']
    form = FilterForm()
    CONSEQUENCES = []
    if form.validate_on_submit():
        filter_AF = form.filter_AF.data
        filter_AC = form.filter_AC.data
        filter_consequence = form.filter_consequence.data
        filter_GENELIST = form.filter_GENELIST.data
        filter_GENELIST_NAME = secure_filename( filter_GENELIST.filename )
        if filter_GENELIST:
            filter_GENELIST.save(os.path.join( current_app.config['UPLOAD_FOLDER'], filter_GENELIST_NAME))
        for C in filter_consequence:
            CONSEQUENCES.append( dict(consequence_choices)[C] )
        CONSEQUENCES_STRING = ','.join( map( str, CONSEQUENCES ) )
        INPUT_LIST = [ CONSEQUENCES_STRING, filename, filter_GENELIST_NAME, filter_AF ]
        INPUT_STRING = '\t'.join( map( str, INPUT_LIST ) )
        return( redirect(url_for( 'main.pre_filterVCF', filename=filename, INPUT_STRING = INPUT_STRING )))
    return( render_template( 'filterVCF_tutorial_DXcator.html', form = form, SERVER_ADDRESS = SERVER_ADDRESS ))


@bp.route('/pre_filterVCF/<filename>/<INPUT_STRING>', methods=['POST', 'GET'])
@project_required
@login_required
@server_valid_authentication_required
def pre_filterVCF( filename, INPUT_STRING ):
    SERVER_ADDRESS = current_app.config['SERVER_ADDRESS']
    body_dict = ({
        'line1' : {
                    'text' : 'Are you sure you want to analyze this file?',
                    'color' : 'grey',
                    'weight' : 'bold',
                    'size' : '100%'
                   },
        'line2' : {
                    'text' : 'If results were already generated for this project they will be overwritten',
                    'color' : 'red',
                    'weight' : 'bold',
                    'size' : '80%'
                   }
    })
    if 'choice' in request.form:
        choice = request.form['choice']
        if choice == 'Yes':
            current_user.project_variant_sent = False
            db.session.commit()
            with open( os.path.join( current_app.config['UPLOAD_FOLDER'], 'analisi0.input'), 'w' ) as F:
                F.write( INPUT_STRING )
            return( redirect( url_for('main.analyzeVCF_ASILO', filename = filename )))
        else:
            return( redirect( url_for('main.upload' )))
    return( render_template( 'yesNo_tutorial_DXcator.html', SERVER_ADDRESS = SERVER_ADDRESS, body_dict = body_dict ))




@bp.route('/analyzeVCF_ASILO/<filename>')
@project_required
@login_required
@server_valid_authentication_required
def analyzeVCF_ASILO( filename ):
    ### pull known variants from server
    known_dict = get_known_variants()
    file_path = os.path.join( current_app.config['UPLOAD_FOLDER'], filename )
    ### this function creates the 3 dictionaries from the input VCF file
    if current_user.get_task_in_progress('analyzeVCF_ASILO_task'):
        flash('An analyze VCF task is currently in progress. Wait it to finish...', 'warning')
    else:
        current_user.launch_task( 'analyzeVCF_ASILO_task', 'Analyzing VCF {}...'.format( filename ), file_path, known_dict, url = current_app.config['REDIS_URL'], database = 2, URL_RESULTS = str(url_for('main.patient_result')) )
        current_user.last_case_seen = None
        db.session.commit()
    return( redirect( url_for( 'main.index' ) ) )



##################################################################
######################## SAMPLE-specific #########################
##################################################################
@bp.route('/patient_result', methods=['GET', 'POST'])
@server_valid_authentication_required
@login_required
@project_required
@project_data_required
@update_known_variants_redis_DB
def patient_result():
    '''
        this is the function to display patients results
    '''
    ### pagination
    page = int(request.args.get('page', 1))
    per_page = 5
    start_page = (page - 1) * per_page
    end_page = (page) * per_page
    # search
    search = False
    q = request.args.get('q')
    if q:
        search = True

    ### get dictionaries
    sample_dict_keys = redis_functions.redis_keys_return( current_app.config['REDIS_URL'], 2,  'sam' )
    samples_keys_to_render = sample_dict_keys[start_page:end_page]
    sample_dict = redis_functions.redis_dict_return_key_list( url = current_app.config['REDIS_URL'], database = 2, key_prefix = 'sam', keys_list = samples_keys_to_render )
    # get samples variant names list to extract only those (speed up)
    sample_var_keys = []
    for single_sample_name in samples_keys_to_render:
        single_sample_var_keys = list(sample_dict[single_sample_name]['varGT'].keys())
        sample_var_keys.extend(single_sample_var_keys)
    sample_var_keys = sorted(sample_var_keys)
    # extract only varinats harbored in those samples
    variant_dict = redis_functions.redis_dict_return_key_list( current_app.config['REDIS_URL'], 2, key_prefix = 'var', keys_list = sample_var_keys )
    ### get number of P/LP variants for each sample
    sampleHTMLdict = diagnosticator_rendering_functions.getSamplesHTMLdict( sample_dict, variant_dict  )
    # create pagination on sample and variant dict
    pagination = Pagination(page=page, per_page=per_page, offset=start_page,
                           total=len(sample_dict_keys), css_framework='bootstrap3',
                           search=search)

    ### pass last case seen
    LAST_CASE_URL = None
    if current_user.last_case_seen:
        LAST_CASE_URL = url_for('main.patient_page', sample_name = current_user.last_case_seen )


    return( render_template('patient_result_DXcator.html',
                                title='Sample Result',
                                sampleHTMLdict = sampleHTMLdict,
                                LAST_CASE_URL = LAST_CASE_URL,
                                pagination=pagination
                                ))


@bp.route('/patient_page/<sample_name>', methods=['GET', 'POST'])
@project_required
@login_required
@server_valid_authentication_required
@project_data_required
@update_known_variants_redis_DB
def patient_page( sample_name ):
    '''
        this is the function to display single patient page
    '''
    ### pagination
    page = int(request.args.get('page', 1))
    per_page = 10
    start_page = (page - 1) * per_page
    end_page = (page) * per_page
    # search
    search = False
    q = request.args.get('q')
    if q:
        search = True

    sample_dict = redis_functions.redis_dict_return( url = current_app.config['REDIS_URL'], database = 2, key_prefix = 'sam', key_value = sample_name )
    sample_dict = diagnosticator_rendering_functions.check_status_in_dict( sample_dict )
    sampleVar_dict = diagnosticator_rendering_functions.getSampleVariants( sample_dict )
    sampleVar_dict = diagnosticator_rendering_functions.orderDictByScore( sampleVar_dict )
    # extract only variants per page
    sampleVar_dict_keys_to_render = list( sampleVar_dict.keys() )[start_page:end_page]
    # create pagination on variant dict
    pagination = Pagination(page=page, per_page=per_page, offset=start_page,
                           total=len(sampleVar_dict), css_framework='bootstrap3',
                           search=search)
    # extract only subdict to render
    sampleVar_dict_to_render = {k:sampleVar_dict[k] for k in sampleVar_dict_keys_to_render if k in sampleVar_dict}

    ### extract possible OMIM inheritance methods for the genes
    GENE_LIST = []
    for VAR in sampleVar_dict_to_render:
        if sampleVar_dict[VAR]['CHARS']['genename']:
            GENE = sampleVar_dict[VAR]['CHARS']['genename']
            GENE_LIST.append(GENE)
    OMIM_INHERITANCE_DB = os.path.join( current_app.config['BASEDIR'], 'DB', 'OMIM', 'genemap2.extracted.tsv' )
    GENES_INH_DICT = diagnosticator_rendering_functions.get_gene_list_omim_inheritance_dict( OMIM_INHERITANCE_DB, GENE_LIST )
    GENES_INH_DICT_CORRECTED = dict()
    if GENES_INH_DICT:
        for GENE in GENES_INH_DICT:
            GENE_INH = []
            for DISEASE, DISEASE_SUBDICT in GENES_INH_DICT[GENE].items():
                DISEASE_OMIM_INH = DISEASE_SUBDICT['INH']
                if ';' in DISEASE_OMIM_INH:
                    for INH in DISEASE_OMIM_INH.split(';'):
                        if INH == "":
                            INH = 'NA'
                        if INH not in GENE_INH:
                            GENE_INH.append(INH)
                else:
                    INH = DISEASE_OMIM_INH
                    if INH not in GENE_INH:
                        if INH == "":
                            INH = 'NA'
                        GENE_INH.append(INH)
            GENE_INH_CORRECTED = ",".join( map( str, GENE_INH ))
            GENES_INH_DICT_CORRECTED.update({ GENE: GENE_INH_CORRECTED })
    for VAR in sampleVar_dict_to_render:
        sampleVar_dict[VAR]['CHARS'].update({ 'gene_OMIM_inh': 'NA' })
        if sampleVar_dict[VAR]['CHARS']['genename']:
            sampleVar_dict[VAR]['CHARS'].update({ 'gene_OMIM_inh': GENES_INH_DICT_CORRECTED[sampleVar_dict[VAR]['CHARS']['genename']] })
    ### store last case seen
    current_user.last_case_seen = sample_name
    db.session.commit()
    return( render_template('patient_page_DXcator.html',
                                title = sample_name,
                                sample_dict = sample_dict,
                                sampleVar_dict = sampleVar_dict_to_render,
                                sample_name = sample_name,
                                pagination = pagination
                                ))


@bp.route('/patient_change_status/<sample_name>/<new_status>', methods=['GET', 'POST'])
@project_required
@login_required
@server_valid_authentication_required
@project_data_required
@update_known_variants_redis_DB
def patient_change_status( new_status, sample_name ):
    '''
        this is the function to change status to a patient
    '''
    diagnosticator_rendering_functions.change_status( url = current_app.config['REDIS_URL'], key_prefix = 'sam', key_value = sample_name, new_status = new_status  )
    flash( "sample {0} status successfully updated to: {1}".format( sample_name, diagnosticator_rendering_functions.get_classes_dict()[new_status]['description'] ), 'success' )
    return( redirect( url_for( 'main.patient_page', sample_name = sample_name )))







##################################################################
######################## VARIANT-specific ########################
##################################################################
@bp.route('/search_variant')
@server_valid_authentication_required
@project_data_required
@project_required
@login_required
@update_known_variants_redis_DB
def search_variant():
    if not g.search_form.validate():
        return redirect(url_for('main.index'))
    return( redirect( url_for('main.variant_page', variant_name = g.search_form.q.data )))


from app.variant_functions import report_local_var

@bp.route('/variant_page/<variant_name>', methods=['GET', 'POST'])
@server_valid_authentication_required
@project_required
@login_required
@project_data_required
@update_known_variants_redis_DB
def variant_page( variant_name ):
    '''
        this is the function to display single variant page
    '''
    VARIANT_DICT_ORDER = ([
        'CHARS',
        'OMIM',
        'AF',
        'CLINVAR',
        'ACMG',
        'SAMPLES'
    ])
    variant_dict = redis_functions.redis_dict_return( url = current_app.config['REDIS_URL'], database = 2, key_prefix = 'var', key_value = variant_name )
    sampleVARstatus_dict = diagnosticator_rendering_functions.get_samples_VAR_status( variant_name = variant_name, variant_dict = variant_dict )
    variant_dict = diagnosticator_rendering_functions.arrangeVARdict( variant_dict )
    ### ACMG update
    varACMG = diagnosticator_rendering_functions.calculateACMG( variant_dict['ACMG'] )
    varACMG_dict = diagnosticator_rendering_functions.addACMGkeys( variant_dict['ACMG'] )
    variant_dict[ 'ACMG' ][ 'ACMG' ] = varACMG
    for k,v in varACMG_dict.items():
        variant_dict[ 'ACMG' ].update({ k: v })
    ### for OMIM links
    OMIM_DB = os.path.join( current_app.config['BASEDIR'], 'DB', 'OMIM', 'mim2gene.txt' )
    GENE_OMIM_DICT = diagnosticator_rendering_functions.get_gene_omim_dict( OMIM_DB )
    LINKS_DICT = dict()
    if variant_dict['CHARS']['genename']:
        if GENE_OMIM_DICT[variant_dict['CHARS']['genename']]:
            LINKS_DICT.update({ 'OMIM' : "https://www.omim.org/entry/" + GENE_OMIM_DICT[variant_dict['CHARS']['genename']] })
    ### for OMIMM inheritance
    OMIM_INHERITANCE_DB = os.path.join( current_app.config['BASEDIR'], 'DB', 'OMIM', 'genemap2.extracted.tsv' )
    GENE_OMIM_INHERITANCE_DICT = ({ variant_dict['CHARS']['genename']: { 'NA' : {'DISEASE': 'NA', 'TYPE': 'NA', 'INH': 'NA'}} })
    INHERITANCE_ABBREVIATIONS_DICT = diagnosticator_rendering_functions.get_inheritance_abbreviations_dict()
    if variant_dict['CHARS']['genename']:
        GENE_OMIM_INHERITANCE_DICT = diagnosticator_rendering_functions.get_gene_list_omim_inheritance_dict( OMIM_INHERITANCE_DB, [variant_dict['CHARS']['genename']] )[variant_dict['CHARS']['genename']]
        ### reconvert inheritance abbreviations
        for DISEASE, DISEASE_SUBDICT in GENE_OMIM_INHERITANCE_DICT.items():
            if ';' in DISEASE_SUBDICT['INH']:
                INH_LIST = []
                for INH in DISEASE_SUBDICT['INH'].split(';'):
                    if INH in INHERITANCE_ABBREVIATIONS_DICT:
                        INH_LIST.append( INHERITANCE_ABBREVIATIONS_DICT[INH] )
                INH_CORRECTED = ";".join( map( str, INH_LIST ))
            else:
                if DISEASE_SUBDICT['INH'] in INHERITANCE_ABBREVIATIONS_DICT:
                    INH_CORRECTED = INHERITANCE_ABBREVIATIONS_DICT[DISEASE_SUBDICT['INH']]
            GENE_OMIM_INHERITANCE_DICT[DISEASE]['INH'] = INH_CORRECTED
            GENE_OMIM_INHERITANCE_DICT[DISEASE]['LINK'] = "https://www.omim.org/entry/" + DISEASE
    variant_dict.update({ 'OMIM' : GENE_OMIM_INHERITANCE_DICT })
    ### for GNOMAD and FRANKLIN and VARSOME link
    if current_user.project_assembly == 'hg19':
        GNOMAD_LINK = "https://gnomad.broadinstitute.org/variant/" + variant_name + "?dataset=gnomad_r2_1"
        FRANKLIN_LINK = "https://franklin.genoox.com/clinical-db/variant/snp/chr" + variant_name
        VARSOME_LINK = "https://varsome.com/variant/hg19/" + variant_name + "?annotation-mode=germline"
    elif current_user.project_assembly == 'hg38':
        GNOMAD_LINK = "https://gnomad.broadinstitute.org/variant/" + variant_name + "?dataset=gnomad_r3"
        FRANKLIN_LINK = "https://franklin.genoox.com/clinical-db/variant/snp/chr" + variant_name + "-hg38"
        VARSOME_LINK = "https://varsome.com/variant/hg38/" + variant_name + "?annotation-mode=germline"
    LINKS_DICT.update({ 'GNOMAD' : GNOMAD_LINK })
    LINKS_DICT.update({ 'FRANKLIN' : FRANKLIN_LINK })
    LINKS_DICT.update({ 'VARSOME' : VARSOME_LINK })
    if variant_dict['CLINVAR']['clinvar_id']:
        CLINVAR_LINK = "https://www.ncbi.nlm.nih.gov/clinvar/variation/" + variant_dict['CLINVAR']['clinvar_id'] + "/?new_evidence=true"
        LINKS_DICT.update({ 'CLINVAR' : CLINVAR_LINK })
    ### for dbSNP
    DBSNP_LINK = "https://www.ncbi.nlm.nih.gov/snp/?term=" + variant_name
    LINKS_DICT.update({ 'DBSNP' : DBSNP_LINK })
    REORDERED_DICT = dict()
    for KEY in VARIANT_DICT_ORDER:
        REORDERED_DICT.update({ KEY: variant_dict[KEY] })
    ### pass last_case_seen
    LAST_CASE_URL = None
    if current_user.last_case_seen:
        LAST_CASE_URL = url_for('main.patient_page', sample_name = current_user.last_case_seen )
    return( render_template('variant_page_DXcator_v2.html',
                                title = variant_name,
                                variant_name =variant_name,
                                variant_dict = REORDERED_DICT,
                                sampleVARstatus_dict = sampleVARstatus_dict,
                                LINKS_DICT = LINKS_DICT,
                                LAST_CASE_URL = LAST_CASE_URL
                                ))



from app.variant_functions import report_local_var

@bp.route('/change_variant_sample_status/<sample_name>/<variant_name>/<new_status>', methods=['GET', 'POST'])
@project_required
@login_required
@server_valid_authentication_required
@project_data_required
def change_variant_sample_status( sample_name, variant_name, new_status ):
    '''
        this is the function to update a variant status inside a sample
    '''
    report_statuses = get_report_statuses()
    try:
        diagnosticator_rendering_functions.update_sampleVAR_status( variant_name, sample_name, new_status )
        if new_status in report_statuses:
            if report_local_var( variant_name, new_status ):
                flash("successfully updated variant: {0} status to {1}, for sample: {2}".format( variant_name, diagnosticator_rendering_functions.get_classes_dict()[new_status]['description'], sample_name ), 'success' )
            else:
                flash("!!! ERROR !!! reporting variant: {0} to server".format( variant_name ), 'danger' )
                #pass
    except:
        pass
        #flash("!!! ERROR !!! updating variant: {0} status to {1}, for sample: {2}".format( variant_name, new_status, sample_name ), 'danger' )
    return( redirect( url_for( 'main.variant_page', variant_name = variant_name ) ))


@bp.route('/change_variant_sample_status_local/<sample_name>/<variant_name>/<new_status>', methods=['GET', 'POST'])
@project_required
@login_required
@server_valid_authentication_required
@project_data_required
def change_variant_sample_status_local( sample_name, variant_name, new_status ):
    '''
        this is the function to update a variant status inside a sample
    '''
    try:
        diagnosticator_rendering_functions.update_sampleVAR_status( variant_name, sample_name, new_status )
        flash("successfully updated variant: {0} status to {1}, for sample: {2}".format( variant_name, diagnosticator_rendering_functions.get_classes_dict()[new_status]['description'], sample_name ), 'success' )
    except:
        pass
    return( redirect( url_for( 'main.variant_page', variant_name = variant_name ) ))



##################################################################
######################### ACMG-specific ##########################
##################################################################
@bp.route('/acmg_page/<variant_name>', methods=['GET', 'POST'])
@project_required
@login_required
@server_valid_authentication_required
@project_data_required
@update_known_variants_redis_DB
def acmg_page( variant_name ):
    '''
        this is the function to display single variant ACMG page
    '''
    variant_dict = redis_functions.redis_dict_return( url = current_app.config['REDIS_URL'], database = 2, key_prefix = 'var', key_value = variant_name )
    variant_dict = diagnosticator_rendering_functions.arrangeVARdict( variant_dict )
    varACMG = diagnosticator_rendering_functions.calculateACMG( variant_dict['ACMG'] )
    redis_functions.redis_add_dict_element( url = current_app.config['REDIS_URL'], database = 2, key_prefix = 'var', key_value = variant_name, subdict_name = 'ACMG', element_name = 'ACMG', element_value = varACMG )
    variant_dict[ 'ACMG' ] = diagnosticator_rendering_functions.addACMGkeys( variant_dict['ACMG'] )
    return( render_template('variantACMG_page_DXcator.html',
                                title = "ACMG: ".format( variant_name ),
                                variant_dict = variant_dict,
                                variant_name = variant_name,
                                varACMG = varACMG
                                ))



@bp.route('/acmg_criteria_modify/<variant_name>/<criteria>/<value>', methods=['GET', 'POST'])
@project_required
@login_required
@server_valid_authentication_required
@project_data_required
def acmg_criteria_modify( variant_name, criteria, value ):
    '''
        this is the function to display single variant ACMG page
    '''
    variant_dict = redis_functions.redis_dict_return( url = current_app.config['REDIS_URL'], database = 2, key_prefix = 'var', key_value = variant_name )
    redis_functions.redis_add_dict_element( url = current_app.config['REDIS_URL'], database = 2, key_prefix = 'var', key_value = variant_name, subdict_name = 'ACMG', element_name = criteria, element_value = value )
    ### recalculate overall ACMG classification
    redis_functions.redis_add_dict_element( url = current_app.config['REDIS_URL'], database = 2, key_prefix = 'var', key_value = variant_name, subdict_name = 'ACMG', element_name = 'ACMG', element_value = diagnosticator_rendering_functions.calculateACMG( variant_dict['ACMG'] ) )
    return( redirect( url_for( 'main.acmg_page',variant_name = variant_name ) ))



##################################################################
########################## GENE-specific #########################
##################################################################
@bp.route('/gene_page/<gene_name>', methods=['GET', 'POST'])
@project_required
@login_required
@server_valid_authentication_required
@project_data_required
@update_known_variants_redis_DB
def gene_page( gene_name ):
    '''
        this is the function to display single gene variants
    '''
    gene_dict = redis_functions.redis_dict_return( url = current_app.config['REDIS_URL'], database = 2, key_prefix = 'gen', key_value = gene_name )
    ### pass last case seen
    LAST_CASE_URL = None
    if current_user.last_case_seen:
        LAST_CASE_URL = url_for('main.patient_page', sample_name = current_user.last_case_seen )
    return( render_template( 'gene_page_DXcator.html',
                                gene_name = gene_name,
                                gene_dict = gene_dict,
                                LAST_CASE_URL = LAST_CASE_URL
                ))


@bp.route('/gene_result', methods=['GET', 'POST'])
@project_required
@login_required
@server_valid_authentication_required
@project_data_required
@update_known_variants_redis_DB
def gene_result( ):
    '''
        this is the function to display all gene results
    '''
    geneHTMLdict = diagnosticator_rendering_functions.get_all_genes_dict( )
    LAST_CASE_URL = None
    if current_user.last_case_seen:
        LAST_CASE_URL = url_for('main.patient_page', sample_name = current_user.last_case_seen )
    return( render_template( 'gene_result_DXcator.html',
                                geneHTMLdict = geneHTMLdict,
                                LAST_CASE_URL = LAST_CASE_URL
                ))






















##########################################################################
########################## API-server-specific ###########################
##########################################################################
@bp.route('/get_known_variants_from_server')
@project_required
@login_required
@server_valid_authentication_required
@project_data_required
def get_known_variants_from_server():
    known_dict = get_known_variants()
    if known_dict:
        flash(known_dict, 'info')
        flash("OK", 'success')
    else:
        flash("FAIL", 'danger')
    return( render_template('blank_DXcator.html'))



@bp.route('/send_variants_to_server')
@project_required
@login_required
@server_valid_authentication_required
@project_data_required
def send_variants_to_server():
    if send_local_variants() :
        flash("OK", 'success')
    else:
        flash("FAIL", 'danger')
    return( render_template('blank_DXcator.html'))



@bp.route('/get_server_messages')
@project_required
@login_required
@server_valid_authentication_required
@project_data_required
def get_server_messages():
    if get_server_new_messages_dict():
        flash("OK", 'success')
    else:
        flash("FAIL", 'danger')
    return( render_template('blank_DXcator.html'))









### ENDc

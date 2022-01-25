from flask import request
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField, RadioField, SelectField, SelectMultipleField, FloatField, IntegerField, FileField
from wtforms.validators import ValidationError, DataRequired, Length
from flask_wtf.file import FileField, FileAllowed, FileRequired


class NewProjectForm( FlaskForm ):
    projectID = StringField('Project ID', validators=[
        DataRequired(), Length(min=1, max=140)])
    project_description = TextAreaField('Project Description', validators=[Length(min=1, max=280)])
    project_assembly = SelectField('Project Assembly', choices=[('hg19','hg19'),('hg38','hg38')], validators=[DataRequired()])
    project_DX = StringField('Project Main Diagnosis', validators=[DataRequired(), Length(min=1, max=140)])
    project_ICDS10 = StringField('Project Main Diagnosis ICD-10 code', validators=[DataRequired(), Length(min=1, max=140)])
    submit = SubmitField('Submit')

consequence_choices = ([
    ( '1', '5_prime_UTR_variant' ),
    ( '2', '3_prime_UTR_variant' ),
    ( '3', 'downstream_gene_variant' ),
    ( '4', 'intron_variant' ),
    ( '5', 'intergenic_variant' ),
    ( '6', 'mature_miRNA_variant' ),
    ( '7', 'non_coding_transcript_exon_variant' ),
    ( '8', 'NMD_transcript_variant' ),
    ( '9', 'non_coding_transcript_variant' ),
    ( '10', 'upstream_gene_variant' ),
    ( '11', 'TFBS_ablation' ),
    ( '12', 'TFBS_amplification' ),
    ( '13', 'TF_binding_site_variant' ),
    ( '14', 'regulatory_region_ablation' ),
    ( '15', 'regulatory_region_amplification' ),
    ( '16', 'feature_elongation' ),
    ( '17', 'regulatory_region_variant' ),
    ( '18', 'feature_truncation' ),
    ( '19', 'splice_region_variant' ),
    ( '20', 'incomplete_terminal_codon_variant' ),
    ( '21', 'start_retained_variant' ),
    ( '22', 'stop_retained_variant' ),
    ( '23', 'synonymous_variant' ),
    ( '24', 'coding_sequence_variant' ),
    ( '25', 'inframe_insertion' ),
    ( '26', 'inframe_deletion' ),
    ( '27', 'missense_variant' ),
    ( '28', 'protein_altering_variant' ),
    ( '29', 'transcript_ablation' ),
    ( '30', 'transcript_amplification' ),
    ( '31', 'start_lost' ),
    ( '32', 'stop_lost' ),
    ( '33', 'frameshift_variant' ),
    ( '34', 'stop_gained' ),
    ( '35', 'splice_donor_variant' ),
    ( '36', 'splice_acceptor_variant' )
])

class FilterForm( FlaskForm ):
    filter_AF = FloatField('popmax AF', validators=[DataRequired()])
    filter_AC = IntegerField('max AC', validators=[DataRequired()])
    filter_GENELIST = FileField('genelist', validators=[
                                    FileRequired(),
                                    FileAllowed(['txt', 'gl'], 'TXT only!')
                                    ])
    filter_consequence = SelectMultipleField('Consequence to EXCLUDE', choices=consequence_choices, validators=[DataRequired()])
    submit = SubmitField('Submit')

class SearchForm(FlaskForm):
    q = StringField('Search Variant', validators=[DataRequired()])
    def __init__(self, *args, **kwargs):
        if 'formdata' not in kwargs:
            kwargs['formdata'] = request.args
        if 'csrf_enabled' not in kwargs:
            kwargs['csrf_enabled'] = False
        super(SearchForm, self).__init__(*args, **kwargs)

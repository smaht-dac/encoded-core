import pytest
from uuid import uuid4


@pytest.fixture(scope='session')
def file_formats(testapp):
    formats = {}
    ef_format_info = {
        'bai': {'standard_file_extension': 'bam.bai',
                "valid_item_types": ["FileProcessed"]},
        'beddb': {"standard_file_extension": "beddb",
                  "valid_item_types": ["FileProcessed", "FileReference"]},
    }
    format_info = {
        'fastq': {'standard_file_extension': 'fastq.gz',
                  'other_allowed_extensions': ['fq.gz'],
                  "valid_item_types": ["FileSubmitted"]},
        'bam': {'standard_file_extension': 'bam',
                'extrafile_formats': ['bai'],
                "valid_item_types": ["FileProcessed"]},
        'zip': {'standard_file_extension': 'zip',
                "valid_item_types": ["FileProcessed"]},
        'chromsizes': {'standard_file_extension': 'chrom.sizes',
                       "valid_item_types": ["FileReference"]},
        'other': {'standard_file_extension': '',
                  "valid_item_types": ["FileProcessed", "FileReference"]},
        'bw': {'standard_file_extension': 'bw',
               "valid_item_types": ["FileProcessed"]},
        'bg': {'standard_file_extension': 'bedGraph.gz',
               "valid_item_types": ["FileProcessed"]},
        'bigbed': {'standard_file_extension': 'bb',
                   "valid_item_types": ["FileProcessed", "FileReference"]},
        'bed': {"standard_file_extension": "bed.gz",
                "extrafile_formats": ['beddb'],
                "valid_item_types": ["FileProcessed", "FileReference"]},
        'vcf_gz': {"standard_file_extension": "vcf.gz",
                   "valid_item_types": ["FileProcessed", "FileSubmitted"]}
    }

    for eff, info in ef_format_info.items():
        info['file_format'] = eff
        info['uuid'] = str(uuid4())
        formats[eff] = testapp.post_json('/file_format', info, status=[201]).json['@graph'][0]
    for ff, info in format_info.items():
        info['file_format'] = ff
        info['uuid'] = str(uuid4())
        if info.get('extrafile_formats'):
            eff2add = []
            for eff in info.get('extrafile_formats'):
                eff2add.append(formats[eff].get('@id'))
            info['extrafile_formats'] = eff2add
        formats[ff] = testapp.post_json('/file_format', info, status=[201]).json['@graph'][0]
    return formats


@pytest.fixture(scope='session')
def software(testapp):
    """ Example software item for BWA """
    return testapp.post_json('/software', {
            "status": "shared",
            "software_type": [
                "aligner"
            ],
            "name": "bwa",
            "version": "0.7.17",
            "title": "bwa_0.7.17",
            "uuid": "02d636b9-d82d-4da9-950c-2ca994a13209",
        }, status=201)


@pytest.fixture(scope='session')
def workflows(testapp, file_formats):
    """ Posts many workflow items to the app to be tested """
    workflow_items = [
        {
            "name": "xtea_germline_v1.0.0",
            "title": "xtea germline [v1.0.0]",
            "app_name": "xtea_germline",
            "arguments": [
                {
                    "argument_type": "Input file",
                    "argument_format": "/file-formats/bam",
                    "workflow_argument_name": "input_bam"
                }
            ],
            "app_version": "v1.0.0",
            "description": "Run xTea algorithm to detect Transposable Elements insertion. Implementation to run on germline data.",
            "cwl_main_filename": "xtea_germline.cwl",
            "workflow_language": "CWL",
            "cwl_child_filenames": [],
            "cwl_directory_url_v1": "s3://cgap-msa-main-application-tibanna-cwls/xtea_germline/v1.0.0",
            "uuid": "fcdad1d6-80b7-4acd-bac8-d954540883c4"
        },
        {
            "name": "expansionhunter_germline_v1.0.0",
            "title": "expansionhunter germline [v1.0.0]",
            "app_name": "expansionhunter_germline",
            "accession": "GAPWFJLR56E8",
            "arguments": [
                {
                    "argument_type": "Input file",
                    "argument_format": "/file-formats/bam",
                    "workflow_argument_name": "input_bam"
                },
            ],
            "app_version": "v1.0.0",
            "description": "Run ExpansionHunter algorithm to detect Short Tandem Repeats expansion. Implementation to run on germline data.",
            "cwl_main_filename": "expansionhunter_germline.cwl",
            "workflow_language": "CWL",
            "cwl_child_filenames": [],
            "cwl_directory_url_v1": "s3://cgap-msa-main-application-tibanna-cwls/expansionhunter_germline/v1.0.0",
            "uuid": "fcd43d09-7d50-4c49-acb4-a5accabe9164"
        }
    ]
    res = []
    for workflow in workflow_items:
        res.append(testapp.post_json('/workflow', workflow, status=201).json)
    return res


@pytest.fixture(scope='session')
def meta_workflow(testapp, file_formats, workflows):
    """ Composes a (nonsense) MetaWorkflow from the previously posted WorkFlow items """
    mwf = {
        "name": "xtea_germline_all",
        "input": [{
            "argument_name": "input_bams",
            "argument_type": "file",
            "dimensionality": 1
            },
        ],
        "title": "xtea germline all [v1.0.0]",
        "version": "v1.0.0",
        "accession": "GAPMWT4NX2PA",
        "workflows": [
            {
                "name": "xtea_germline@LINE1",
                "input": [{
                    "scatter": 1,
                    "argument_name": "input_bam",
                    "argument_type": "file",
                    "source_argument_name": "input_bams"
                    },
                ],
                "config": {
                    "ebs_size": "1.1x",
                    "run_name": "run_xtea_germline-LINE1",
                    "EBS_optimized": True,
                    "instance_type": "m5.4xlarge",
                    "spot_instance": True,
                    "behavior_on_capacity_limit": "wait_and_retry"
                },
                "workflow": "fcdad1d6-80b7-4acd-bac8-d954540883c4",
                "custom_pf_fields": {}
            },
        ],
        "description": "Run xTea algorithm to detect Transposable Elements insertion from germline data. "
                       "Call ALL classes of TE (LINE1, ALU, SVA).",
        "uuid": "cc3fbaef-4dd3-482b-afc9-01bfcd3fd2b4"
    }
    return testapp.post_json('/MetaWorkflow', mwf, status=201).json


@pytest.fixture(scope='session')
def sample_file(testapp, file_formats):
    """ Posts a sample file we can reference in workflow output """
    return testapp.post_json('/FileProcessed', {
        'uuid': 'fe58c408-cc82-4ece-8062-b2a4a81c745d',
        'file_format': '/file-formats/bam'
    }, status=201).json


@pytest.fixture(scope='session')
def sample_workflow_run(testapp, file_formats, workflows, sample_file):
    """ Posts a sample workflowrun """
    return testapp.post_json('/WorkflowRunAwsem', {
        "title": "xtea v1.1.0 run 2023-04-17 21:02:32.148147",
        "workflow": "fcdad1d6-80b7-4acd-bac8-d954540883c4",
        "run_status": "complete",
        "input_files": [
            {
                "value": "fe58c408-cc82-4ece-8062-b2a4a81c745d",
                "ordinal": 1,
                "dimension": "0",
                "workflow_argument_name": "input_bam"
            }
        ],
        "awsem_job_id": "bOhzpCaK16oj",
        "run_platform": "AWSEM",
        "metadata_only": False,
        "awsem_app_name": "xtea",
        "uuid": "4e15dd9d-2f3b-4444-8e7b-f7ec3044669e"
    }, status=201).json

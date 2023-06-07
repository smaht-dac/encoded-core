def test_types_workflow(testapp, file_formats, workflows):
    """ Tests that we can build workflows that reference file format items """
    for workflow in workflows:
        assert testapp.get(f'/{workflow["@graph"][0]["@id"]}', status=200)


def test_types_workflow_run(testapp, file_formats, sample_file, workflows, sample_workflow_run):
    """ Tests that we can create a workflowrun from an existing workflow """
    assert testapp.get(f'/{sample_workflow_run["@graph"][0]["@id"]}', status=200)

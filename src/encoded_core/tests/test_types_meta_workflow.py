def test_types_metaworkflow(testapp, file_formats, workflows, meta_workflow):
    """ Tests that we can create a metaworkflow using backing structures """
    mwf = meta_workflow
    assert testapp.get(mwf['@graph'][0]['@id'], status=200)

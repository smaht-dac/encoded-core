def test_types_software(testapp, software):
    """ Tests that we can load and retrieve a software item """
    software_atid = software.json['@graph'][0]['@id']
    assert testapp.get(software_atid, status=200)

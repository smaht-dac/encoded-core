def test_types_file_format(testapp, file_formats):
    """ Tests loading the file_formats fixture, which posts many formats to the app """
    formats = file_formats
    for atid in formats.keys():
        assert testapp.get(f'/file-formats/{atid}', status=200)

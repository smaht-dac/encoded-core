_app_settings = {
    "collection_datastore": "database",
    "item_datastore": "database",
    "multiauth.policies": "session remoteuser accesskey auth0",
    "multiauth.groupfinder": "snovault.authorization.groupfinder",
    "multiauth.policy.session.use": "snovault.authentication.NamespacedAuthenticationPolicy",
    "multiauth.policy.session.base": "pyramid.authentication.SessionAuthenticationPolicy",
    "multiauth.policy.session.namespace": "mailto",
    "multiauth.policy.remoteuser.use": "snovault.authentication.NamespacedAuthenticationPolicy",
    "multiauth.policy.remoteuser.namespace": "remoteuser",
    "multiauth.policy.remoteuser.base": "pyramid.authentication.RemoteUserAuthenticationPolicy",
    "multiauth.policy.accesskey.use": "snovault.authentication.NamespacedAuthenticationPolicy",
    "multiauth.policy.accesskey.namespace": "accesskey",
    "multiauth.policy.accesskey.base": "snovault.authentication.BasicAuthAuthenticationPolicy",
    "multiauth.policy.accesskey.check": "snovault.authentication.basic_auth_check",
    "multiauth.policy.auth0.use": "snovault.authentication.NamespacedAuthenticationPolicy",
    "multiauth.policy.auth0.namespace": "auth0",
    "multiauth.policy.auth0.base": "snovault.authentication.Auth0AuthenticationPolicy",
    "load_test_only": True,
    "testing": True,
    "indexer": True,
    "mpindexer": False,
    "production": True,
    "pyramid.debug_authorization": True,
    "postgresql.statement_timeout": 20,
    "sqlalchemy.url": "dummy@dummy",
    "retry.attempts": 3,
    # some file specific stuff for testing
    "file_upload_bucket": "cgap-unit-testing-files",
    "file_wfout_bucket": "cgap-unit-testing-wfout",
    "file_upload_profile_name": "test-profile",
    "metadata_bundles_bucket": "cgap-unit-testing-metadata-bundles",
}


def make_app_settings_dictionary():
    return _app_settings.copy()

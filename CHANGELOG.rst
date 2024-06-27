============
encoded-core
============

----------
Change Log
----------

0.9.6
=====
* Updates related to Python 3.12.



0.9.5
=====

* Added ALLOW_FOR_RCLONE_BASED_S3_TO_S3_COPY feature to types/file.py to specifically
  and ONLY allow rclone based S3-to-S3 copy. For some reason rclone needs s3:ListBucket;
  but we limit it to a key prefix set to exactly our upload file destination key.
  See more comments in types/file.py/external_creds.

0.9.4
=====

* adds ``assay type`` and ``dataset`` dimension to GA4 e-commerce product item object


0.9.3
=====

* Remove dependency on ``awscli``


0.9.2
=====

* adds ``dataset`` dimension to GA4 server-side download metrics


0.9.1
=====

* set default GA4 ``client_id`` for non browser requests
* get assay type from ``data_generation_summary`` for GA4


0.9.0
=====

* Update types.file.external_creds to allow generation of federation token for file downloads as well as uploads, for use with smaht-portal


0.8.3
=====

* 2024-03-22/dmichaels
* Added s3:GetObject to types.file.external_creds to allow doing HEAD on
  S3 object being uploaded  by smaht-submitr, for feedback/progress mechanism.


0.8.2
=====

* Adds item category 3 for GA4 server-side downloading event


0.8.1
=====

* Replace submission center with sequencing center in GA4 server-side downloading event


0.8.0
=====

* Fix ``extra_files.filename`` such that the field contains the file_format suffix, to differentiate it from the normal file
* Changes for GA4


0.7.0
=====

* Version updates to dcicutils, dcicsnovault.
  Changes to itemize SMaHT submission ingestion create/update/diff situation.


0.6.0
=====

* Updated dcicsnovault to 11.8.0 with added support for an
  optional gitinfo.json file (deployed via portal buildspec.yml).


0.5.1
=====

* Limit upgrader config scan to its file only


0.5.0
=====

* Updated dcicutils to 8.6.0 (with structured_data and SMaHT ingestion related fixes).


0.4.0
=====

* Updated dcicutils to 8.4.1 (with structured_data).


0.3.1
=====

* Allow additional properties on `extra_files` property in File schema


0.3.0
=====

* SMaHT ingestion related work (keep in sync with drr_schema_updates).


0.2.1
=====

* Refactor File file format validator for compatibility with smaht-portal


0.2.0
=====

* Merging in Doug's drr_schema_updates branch.
* 2023-11-02


0.1.0
=====

* Upgrade to Python 3.11.



0.0.4
=====

* Port DRS implementation from fourfront


0.0.3
=====

* Allow new snovault major version


0.0.2
=====

* Fix some bugs brought in from application specific info from CGAP

0.0.1
=====

* Initial release

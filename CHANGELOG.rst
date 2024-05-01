============
encoded-core
============

----------
Change Log
----------


0.8.4
=====

* 2024-05-01/dmichaels
* Updated the temporary AWS session token policy, for AWS file uploads, in types.external_creds
  to allow s3:HeadObject for the bucket/key, and to allow s3:ListBucket for the bucket itself.
  This was to support rclone hashsum md5 for smaht-submitr.


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

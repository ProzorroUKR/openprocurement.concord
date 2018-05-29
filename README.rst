Documentation
=============

OpenProcurement is initiative to develop software 
powering tenders database and reverse auction.

'openprocurement.concord' is component responsible for 
conflict resolution in tenders database.


Usage
-----

Add in buidout::

  [openprocurement.concord]
  recipe = zc.recipe.egg
  entry-points = concord=openprocurement.concord.daemon:main
  arguments = '${openprocurement.api.ini:couchdb_url}','${openprocurement.api.ini:couchdb_db}','${buildout:directory}/var/${:_buildout_section_name_}.status'

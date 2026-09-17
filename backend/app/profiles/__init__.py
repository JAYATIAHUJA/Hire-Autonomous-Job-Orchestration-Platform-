"""Profile persistence layer: turn analysis output into stored, serialisable profiles.

The pipeline is deliberately split into three single-responsibility steps so the
router stays a thin HTTP adapter:

* ``builder``    – analysis result (plain dicts/dataclasses) -> in-memory ORM graph
* ``repository`` – ORM graph <-> database (save / eager-loaded read)
* ``serializer`` – stored ORM graph -> API response schemas
"""

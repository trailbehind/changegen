.. changegen documentation master file, created by
   sphinx-quickstart on Tue Dec 15 13:22:20 2020.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

``changegen``: `OSM Changefiles <https://wiki.openstreetmap.org/wiki/OsmChange>`_ from PostGIS Tables
=====================================================================================================

Many workflows based on OpenStreetMap data use PostGIS to enable spatial operations on these data at planetary scale. Expressing modifications, additions, or deletions to these data is sometimes necessary: for example, to communicate those changes to another system or workflow without access to the PostGIS instance.

``changegen`` is a command line utilty that creates (optionally gzipped) `OSM Changefiles <https://wiki.openstreetmap.org/wiki/OsmChange>`_ from PostGIS tables. Changefiles can then be applied to existing OSM extracts to create new extracts containing the modifications described in the changefile. 

Things ``changegen`` can do:
---------------------------------------------------------------
* Translate from PostGIS ``GEOMETRY`` tp OpenStreetMap XML formats (``Ways``, ``Nodes``, ``Relations``). (**NB**: Only ``Polygon`` and ``LineString`` data types are currently supported).
* **Create** new ``Polygons`` (e.g. closed ``Ways`` or ``Relations``) or ``LineStrings`` (``Ways`` and ``Nodes``) from objects in PostGIS tables, with corresponding schema as OSM tags
* **Ensure** that new Ways are properly "network-noded" : e.g. that they share nodes at intersections with both *existing* and *new* geometries. This is important for e.g. ensuring accurate network topology. This also includes modifying *existing* ``Ways`` to include these noded intersections. (**NB**: Intersections with ``Polygon`` objects is not currently supported.)
* **Modify** the metadata of ``Ways`` in an existing OSM extract.
* **Delete** any OSM object specified by an ``osm_id`` column in a PostGIS table.


Installation
------------

``changegen`` is not available on ``pip`` but is ``pip`` -installable: 

.. code-block:: shell
   
   git clone https://github.com/trailbehind/changegen.git 
   pip install -e changegen

``changegen`` depends on: ``click``, ``tqdm``, ``osmium``, ``shapely``, ``gdal``, ``lxml``, ``psycopg2``, ``pyproj``, and ``rtree``.


Command Line Usage
------------------

The ``changegen`` utility requires access to a PostGIS database. It has two primary "modes:" *create* and *modify*. They are mutually-exclusive: that is, modifications cannot be specified during the same invocation as creation. (To get around this limitation, you can create multiple ``.osc`` files and merge them with `osmosis <https://wiki.openstreetmap.org/wiki/Osmosis>`_). Create mode is enabled by default. To use modify mode, pass the ``--modify_only`` flag, documented below. To enable the creation of deletions in the OSM Changefile output, provide the names of PostGIS tables containing an ``osm_id`` column of IDs to delete with ``--deletions``. 

Detailed Usage
^^^^^^^^^^^^^^



.. click:: changegen:main
   :prog: changegen
   :nested: full

.. toctree::
   :maxdepth: 2
   :caption: Contents:


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

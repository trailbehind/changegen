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
* Translate from PostGIS ``GEOMETRY`` to OpenStreetMap XML formats (``Ways``, ``Nodes``). (**NB**: Only ``Polygon``, ``Point`` and ``LineString`` data types are currently supported).
* **Create** new ``Polygons`` (e.g. closed ``Ways`` or ``Relations``) or ``LineStrings`` (``Ways`` and ``Nodes``) from objects in PostGIS tables, with corresponding schema as OSM tags
* **Ensure** that new Ways are properly "network-noded" : e.g. that they share nodes at intersections with both *existing* and *new* geometries. This is important for e.g. ensuring accurate network topology. This also includes modifying *existing* ``Ways`` to include these noded intersections. (**NB**: Intersections with ``Polygon`` objects is not currently supported.)
* **Modify** the metadata of ``Ways`` in an existing OSM extract.
* **Delete** any OSM object specified by an ``osm_id`` column in a PostGIS table.

Example Usage Scenario
------------------------------------------------

In some workflows, it is common to want to modify the data in an OSM Planet file programmatically. For example, to standardize the set of tags for a given class of OSM objects, or to used third-party data to modify OSM objects regionally. PostGIS is a compelling tool for this kind of processing, as it scales well to large datasets and has fast and flexible spatial operations. In many cases, however, it is desirable to have an OSM Planet file as the result of this geoprocessing, rather than a set of PostGIS tables. 

This is why we developed ``changegen``. This tool enables the creation of OSM Changefiles that describe modifications to an existing source OSM Planet file. These modifications are sourced from PostGIS tables, developed using a tool like `imposm <https://imposm.org/docs/imposm3/latest/>`_ and custom SQL. ``Changegen`` takes care of making sure that intersections are properly noded, that PostGIS geospatial types are converted accurately to OSM types, managing OSM IDs for new and modified objects. At the end of the workflow, the changefile that's produced by Changegen (derived from the original OSM file and the PostGIS database tables specified), can be applied to the original planet file (using a tool like `osmosis <https://wiki.openstreetmap.org/wiki/Osmosis>`_ ), to obtain an OSM Planet file that contains the modifications performed via the PostGIS database.


.. image:: images/changegen-schematic.png

.. raw:: html
   
   <center><i>Schematic of example usage</i></center>

Installation
------------

``changegen`` is not available on ``pip`` but is ``pip`` -installable: 

.. code-block:: shell
   
   git clone https://github.com/trailbehind/changegen.git 
   pip install -e changegen

``changegen`` depends on: ``click``, ``tqdm``, ``osmium``, ``shapely``, ``gdal``, ``lxml``, ``psycopg2``, ``pyproj``, and ``rtree``.


.. toctree::
   :maxdepth: 2
   :caption: Contents:

   quickstart
   postgis
   source/changegen

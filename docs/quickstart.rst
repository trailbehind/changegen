
**************************
Quickstart / Usage Guide
**************************

This guide gives a high-level overview of the command line interface to ``changegen``. It assumes a fairly technical level of knowledge of PostGIS, OSM file formats, and `osmosis <https://wiki.openstreetmap.org/wiki/Osmosis>`_. 

Setup + Installation 
====================

Installing ``changegen`` is easy with pip:

::

    pip install git+https://github.com/trailbehind/changegen.git

(you can specify a specific `release <https://www.github.com/trailbehind/changegen/releases>`_ with ``...changegen.git@<release>``)

This tutorial also assumes the following (since these assumptions fairly accurately describe most use-cases for ``changegen``):

* you have a PostGIS database running on your local computer, or accessible via a network.
* you have an OSM extract 
* you have `osmosis <https://wiki.openstreetmap.org/wiki/Osmosis>`_ installed
* you have `imposm3 <https://imposm.org/docs/imposm3/latest/>`_ installed

Database Setup + Access
-----------------------

To be sure that the PostGIS database used to support changegen operations is setup well, refer to :doc:`postgis` for details. 

After the database is setup, we need to provide ``changegen`` with details on how to connect to this database. By default, ``changegen`` attempts to connect to a PostGIS database using the following parameters: 

+---------------+-------------------+---------------------+
| **Parameter** | **Default Value** | **Environment Var** |
+---------------+-------------------+---------------------+
| DB Name       | ``conflate``      | ``PGDATABASE``      |
+---------------+-------------------+---------------------+
| Port          | 15432             | ``PGPORT``          |
+---------------+-------------------+---------------------+
| User          | ``postgres``      | ``PGUSER``          |
+---------------+-------------------+---------------------+
| Password      | no password       | ``PGPASS``          |
+---------------+-------------------+---------------------+
| Host          | ``localhost``     | ``PGHOST``          |
+---------------+-------------------+---------------------+

To provide alternate access credentials, you may either provide them explicitly on the command line or by setting environment variables, as above. See ``changegen --help`` for details on how to provide credentials on the command line.

.. note::
    The following examples of CLI use assume that there's a PostGIS database running on the same system, using the default connection parameters listed above.

Using the Changegen CLI
========================

There are several scenarios that are common when using ``changegen``, so we'll cover those explicitly here. 

Adding new features to OSM file
------------------------------------

Commonly we want to add new features to the OSM Planet file, perhaps to augment the OSM database with additional or proprietary information. To do this, it is required that we define a **PostGIS table that contains exclusively features to be added to the OSM file.** For this example we'll call this table ``new_features``. 

The following CLI invocation will create a OSM Changefile containing the features in ``new_features``. This process does the following:

* Converts the PostGIS/OGR geometry representation in to OSM Nodes and Ways, as needed
* Converts all fields in the ``new_features`` table inth OSM Tags to be added to each new Node/Way
* Assigns OSM ID numbers to each new feature to be added to the file. 

::

    changegen --suffix new_features -outdir . --osmsrc data.osm.pbf

Running this command will create a changefile named ``new_features.osc`` in the current working directory. ``data.osm.pbf`` is the path for the source OSM data file that this changefile will eventually be applied to. 

This simple invocation works, but could potentially produce an incomplete or otherwise buggy OSM Planet file, because it does not take advantage of many of the features that ``changegen`` has to offer to prevent many common pitfalls. We'll demonstrate some modifications to this command that can fix some of these common issues. 

**Creating properly noded self-intersections**

If ``new_features`` is a set of linestrings that potentially may intersect with each other, and we want these linestrings to have properly noded intersections (see `OSMWiki:Conventions#Junctions <https://wiki.openstreetmap.org/wiki/Editing_Standards_and_Conventions#Junctions>`_ for context), we can provide the ``-si/--self`` flag as follows: 

::

    changegen --suffix new_features --self -outdir . --osmsrc data.osm.pbf

.. warning::
    It is very important that the source PostGIS table (in this case ``new_features``) has a GIST Geometry index defined on its geometry column before using the ``--self`` flag. If not, this command will take many orders of magnitude longer to execute.


**Creating properly noded intersections with other OSM objects**

If ``new_features`` is a set of linestrings that potentially may intersect with **other OSM objects**, we take a slightly different approach. First, we need to be sure we have an ``imposm``-derived PostGIS table that contains any of the geometries that may intersect with any of the features in ``new_features``. It's important that **this table also have a GIST geometry index**. 

For this example, let's assume we have ``new_features`` and another table of existing OSM objects known as ``existing_features``. We can ensure that all intersections between features in ``new_features`` and features in ``existing_features`` have proper junction nodes by using the ``-e/--existing`` flag, e.g. the following command:

.. code-block:: shell

    changegen --suffix new_features --self --existing existing_features -outdir . --osmsrc data.osm.pbf

**Using an OSM ID offset**

When adding new features to an OSM planet file, it is important that those new features are assigned IDs that do not collide with existing features in the planet file. Changegen provides support for this by providing an ``--id_offset`` flag. Passing this flag and an integer value (e.g. ``--id_offset 500``) will assign OSM ID values to new features starting with the value 500. It is up to the user to provide an ID offset that will not collide with existing features. If ``osmium`` is installed, the ``--no_collisions`` flag will stop execution if any IDs will be assigned to a new feature that would collide with an existing ID.


Modifying existing features in the OSM file
--------------------------------------------

Changegen also supports modifying the **metadata** of existing OSM features. **Note** that this feature explicitly does not support modifying geometries. (The case of modifying geometries is supported by a combination of adding and removing features.) 

Changegen supports metadata modification via the ``--modify_meta`` flag. If this flag is provided, any tables that are selected via the ``--suffix`` flag will be treated as tables that contain existing OSM features to be modified. The resulting changefile will contain ``<modify>`` tags for each of these features. The Tags for each of these features will mirror the database fields present in the tables (and, optionally, any ``hstore`` columns -- see `Maintaining all Tags with Hstore columns`_ below), and the geometries will be identical to their original representation in the OSM planet file from which they were imported. This method explicitly maintains node order for Ways, and ensures that all modified Ways contain the exact same node references as their original objects (e.g. to maintain original routable junctions in the OSM file). 

For example, if ``modified_features`` is a table of existing OSM features whose metadata have been modified, we can create a changefile expressing these modifications to these existing features like so: 

.. code-block:: shell

    changegen --suffix modified_features --modify_meta -outdir . --osmsrc data.osm.pbf


Removing existing features in the OSM file
-------------------------------------------

The third mode that changegen provides is a deletion mode. This mode can be used in conjunction with either the creation (e.g. the default mode) or the metadata modification mode. To delete OSM features (e.g. if they are being replaced with new features), create a table of the original OSM IDs of these objects to be deleted. This table must contain a column named ``osm_id``. Provide the name of this table to ``changegen`` using the ``--deletions`` flag, e.g. ``--deletions table_of_objects_to_delete``. Any ID listed in this table will be represented by a `<delete>` node in the resulting changefile. The ``--deletions`` flag can be provided multiple times. 

Other Features
================================

``Changegen`` provides a few more features that can help to support common use-cases of this tool. 

Maintaining all Tags with Hstore columns
------------------------------------------

Most often, ``changegen`` is used in conjunction with a set of PostGIS tables that have been at least in part created by ``imposm``. In many pipelines that involve ``changegen``, especially (but not exclusively) those that modify existing features, a certain subset of OSM feature tags are imported using the ``imposm`` mapping YAML files. These tags (represented in the database as columns) are then used to complete whatever conflation needs to happen. 

Often, however, these features contain many other tags that aren't explicitly imported into the database via imposm. This is relevant to data processing steps after ``changegen``. By default, ``changegen`` only writes as OSM tags database columns that are present in the source table. For example, when modifying an existing OSM feature, if the database table containing the modified feature only contains ``name`` an ``highway`` columns, the resulting changefile will only contain ``name`` and ``highway`` tags, which means that those features will only contain those tags in the OSM Planet file resulting from applying that changefile to another OSM planet file. 

This is usually not desirable, because we sometimes can't know what tags will be necessary for later processing steps. Both ``imposm`` and ``changegen`` offer support for this situation. You can use the ``hstore_tags`` option in imposm (`docs <https://imposm.org/docs/imposm3/latest/mapping.html#hstore-tags>`_) to add a column in the database that contains an hstore object with all tags. By default the only tags included in the hstore are ones that have been explicitly mentioned in the mapping.yaml file. To import all tags known for a feature, you'll need to use the ``load_all`` directive (`docs <https://imposm.org/docs/imposm3/latest/mapping.html#tags>`_).

Once you've imported all tags, you can specify that ``changegen`` looks for an hstore column and writes all key:value pairs in the hstore column as Tag objects on every feature. Use the ``--hstore_tags`` option to specify the name of the column to obtain tags from. Note that if multiple tables are specified (e.g. multiple tables with new or modified features) they all must contain hstore columns with the same name. In the case where tag names are duplicated between the hstore and the database table columns, column key values will take precedence over values in the hstore.

Compressed changefiles
----------------------

The OSMChange format is an XML-based structured format that specifies changes to be made to an OSM Planet file. Most readers of this format support compression, so we provide a ``--compress`` flag that enables changegen to output gzipped changefiles. 


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

Database Setup 
---------------

Refer to :doc:`postgis` for details here.

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

    changegen --suffix new_features --self --existing existing_features --self -outdir . --osmsrc data.osm.pbf



Modifying existing features in the OSM file
--------------------------------------------


Removing existing features in the OSM file
-------------------------------------------

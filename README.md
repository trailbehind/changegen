# OSM Changefile Generator (`changegen`)


Changegen is a command-line application for generating OSM changefiles from database tables and their source extract. This software is designed to support PostGIS/Imposm-based workflows for conflation of third-party data with OSM. The resulting changefiles can be used post-conflation to enable the updating of the source Planet file (or any other extract) with newly-conflated data via software such as [Osmosis](https://wiki.openstreetmap.org/wiki/Osmosis). 

The primary output of this software are `.osc` files, described in detail [here](https://wiki.openstreetmap.org/wiki/OsmChange). (*It is important to note that `.osc` change files are distinct from [OSM Change Sets](https://wiki.openstreetmap.org/wiki/Changeset)*)

Main Features: 
* Ensures properly noded junctions (e.g. intersecting Ways always share a Node).
* Configurable ID generation (negative IDs, arbitrary offsets)
* Use of GDAL for efficient geodata processing

This software is currently in an alpha release, and will change rapidly.
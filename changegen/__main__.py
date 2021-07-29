import logging
import math
import os
import subprocess
import sys

import click
import psycopg2 as psy

from . import PACKAGE_NAME
from .generator import generate_changes
from .generator import generate_deletions
from .util import setup_logging


"""
cli.py

Tony Cannistra <tony@gaiagps.com>

Provides main changegen CLI-based entrypoint.

"""


def _get_max_ids(source_extract):
    # get the max ID from source extract using osmium
    ## first ensure that osmium exists
    try:
        proc = subprocess.check_call(
            "osmium --help",
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as e:
        logging.warning(
            "osmium not found; unable to determine max OSM id in source extract"
        )
        raise e

    ids = {}
    for idtype in ["data.maxid.ways", "data.maxid.nodes", "data.maxid.relations"]:
        proc = subprocess.Popen(
            f"osmium fileinfo -e -g {idtype} --no-progress {source_extract}",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.stderr.read():
            raise subprocess.CalledProcessError(-1, "osmium", "Error in osmium.")
        ids[idtype.split(".")[-1]] = int(proc.stdout.read().strip())
    return ids


def _get_db_tables(suffix, dbname, dbport, dbuser, dbpass, dbhost):
    c = psy.connect(
        dbname=dbname, host=dbhost, user=dbuser, password=dbpass, port=dbport
    )
    cur = c.cursor()
    _q = (
        "SELECT table_name from information_schema.tables "
        f"where table_name LIKE '%{suffix}'"
    )
    cur.execute(_q)
    ans = cur.fetchall()
    c.close()
    return [a[0] for a in ans]


@click.command()
@click.option("-d", "--debug", help="Enable verbose logging.", is_flag=True)
@click.option(
    "-s",
    "--suffix",
    help=(
        "Suffix for DB tables containing newly-added features."
        " Can be passed multiple times for multiple suffixes."
    ),
    default=["_new"],
    show_default=True,
    multiple=True,
)
@click.option(
    "--deletions",
    help=(
        "Name of table containing OSM IDs for which <delete> tags "
        " should be created in the resulting changefile. Table must "
        " contain <osm_id> column. Can be passed multiple times."
    ),
    multiple=True,
    default=[],
)
@click.option(
    "-e",
    "--existing",
    help=(
        "Table of geometries to use when determining whether existing"
        " features must be altered to include linestring intersections."
    ),
    multiple=True,
    default=[],
)
@click.option(
    "-m",
    "--modify_meta",
    help=(
        "Create <modify> tags in changefile, instead of create nodes "
        "for all tables specified by --suffix. Only applies to "
        "Ways with with modified metadata, not geometries (see full help)."
    ),
    is_flag=True,
)
@click.option("-o", "-outdir", help="Directory to output change files to.", default=".")
@click.option("--compress", help="gzip-compress xml output", is_flag=True)
@click.option("--neg_id", help="use negative ids for new OSM elements", is_flag=True)
@click.option(
    "--id_offset",
    help="Integer value to start generating IDs from.",
    type=int,
    default=0,
    show_default=True,
)
@click.option(
    "--no_collisions",
    help="Stop execution if the chosen ID offset "
    "will cause collisions with existing OSM ids."
    " (requires osmium).",
    is_flag=True,
)
@click.option(
    "--self",
    "-si",
    help=(
        "Check for and add intersections among newly-added features. "
        "It is strongly adviseable to create a geometry index on "
        "new geometry tables' geometry column before using this option."
    ),
    is_flag=True,
)
@click.option(
    "--max_nodes_per_way",
    help=(
        "Number of nodes allowed per way. Default 2000."
        " If a way exceeds this value "
        " it will be subdivided into smaller ways. Pass `none` for no limit."
    ),
    default="2000",
)
@click.option(
    "--hstore_tags",
    help=(
        "Specify Postgres hstore column to obtain tags from, "
        "in addition to table columns. "
        "This column should contain a hstore, and the keys will be compared "
        "to existing columns. Column key values will take "
        "precedence over values in the hstore if duplicates are found."
    ),
    default=None,
    show_default=True,
)
@click.option("--osmsrc", help="Source OSM PBF File path", required=True)
@click.argument("dbname", default=os.environ.get("PGDATABASE", "conflate"))
@click.argument("dbport", default=os.environ.get("PGPORT", "15432"))
@click.argument("dbuser", default=os.environ.get("PGUSER", "postgres"))
@click.argument("dbhost", default=os.environ.get("PGHOST", "localhost"))
@click.argument("dbpass", default=os.environ.get("PGPASSWORD", ""))
def main(*args: tuple, **kwargs: dict):
    """
    Create osmchange file describing changes to an imposm-based PostGIS
    database after a spatial conflation workflow.

    This module relies on a PostGIS database generated by imposm3
    from an OSM Planet file. Connection parameters can be provided via
    standard Postgres environment variables, as positional arguments,
    or a combination of both. Defaults are from the environment variables.
    If they don't exist, suitable defaults are provided.

    This module produces a change file that includes any newly-added
    features as well as any features that must be modified to
    properly represent linestring intersections. The resulting file
    can be applied to a Planet file to alter the file with the
    conflated changes.

    If the tables selected by --suffix do not represent new features
    but actually represent features with modified metadata, use --modify_meta.
    NOTE that --modify_meta does not support modified geometries (use default
    behavior with a --delete table for that).
    --modify_meta is not compatible with intersection detection. Creation of
    modify nodes is only compatible with linestring features.
    """
    setup_logging(debug=kwargs["debug"])
    logging.debug(f"Args: {kwargs}")

    # Check for ID collisions and warn
    try:
        ids = _get_max_ids(kwargs["osmsrc"])
        if any([kwargs["id_offset"] < id for id in ids.values()]):
            _log_text = f"Chosen ID offset {kwargs['id_offset']} may cause collisions with existing OSM IDs (max IDs: {ids})."
            if kwargs["no_collisions"]:
                logging.fatal(_log_text)
                sys.exit(-1)
            else:
                logging.warning(_log_text)
    except subprocess.CalledProcessError:
        logging.error("Error checking existing OSM max ids.")

    new_tables = []
    for suffix in kwargs["suffix"]:
        new_tables.extend(
            _get_db_tables(
                suffix,
                kwargs["dbname"],
                kwargs["dbport"],
                kwargs["dbuser"],
                kwargs["dbpass"],
                kwargs["dbhost"],
            )
        )
    logging.info(f"Found tables in db: {new_tables}")

    max_nodes_per_way = kwargs["max_nodes_per_way"]
    if str(max_nodes_per_way).lower() == "none":
        max_nodes_per_way = math.inf
    elif max_nodes_per_way == None:
        max_nodes_per_way = 2000
    if kwargs["modify_meta"] and kwargs["existing"]:
        raise RuntimeError("--modify_meta cannot be used with --existing.")

    for table in new_tables:
        generate_changes(
            table,
            kwargs["existing"],
            kwargs["deletions"],
            kwargs["dbname"],
            kwargs["dbport"],
            kwargs["dbuser"],
            kwargs["dbpass"] if kwargs["dbpass"] != "" else None,
            kwargs["dbhost"],
            kwargs["osmsrc"],
            os.path.join(str(kwargs["o"]), f"{table}.osc"),
            compress=kwargs["compress"],
            neg_id=kwargs["neg_id"],
            id_offset=kwargs["id_offset"],
            self_intersections=kwargs["self"],
            max_nodes_per_way=int(max_nodes_per_way),
            modify_only=kwargs["modify_meta"],
            hstore_column=kwargs["hstore_tags"],
        )

    for table in kwargs["deletions"]:
        generate_deletions(
            table,
            "osm_id",
            kwargs["dbname"],
            kwargs["dbport"],
            kwargs["dbuser"],
            kwargs["dbpass"] if kwargs["dbpass"] != "" else None,
            kwargs["dbhost"],
            kwargs["osmsrc"],
            os.path.join(str(kwargs["o"]), f"{table}.osc"),
            compress=kwargs["compress"],
        )


if __name__ == "__main__":
    main(prog_name=PACKAGE_NAME)

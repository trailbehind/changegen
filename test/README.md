# `changegen` testing

The test suite for `changegen` requires a PostGIS database containing some test data to be running alongside the python tests. To enable this we use a `docker-compose` file to both run/populate the database and run the tests.

## Running Tests

**Via CodeShip**: these tests automatically run with every push. [Check status here.](https://app.codeship.com/projects/824fe25d-68b7-4dde-9ec9-638b52ae0859)

**Locally**:

1. `docker-compose build` (only need to run this once, unless you modify `test/Dockerfile-test` or `test/Dockerfile-db`)
2. `docker-compose up`. This configures the db and runs the test suite.
3. To re-run the tests, you must `docker-compose down` before running `docker-compose up` again.

## Testing Data Preparation

There is a `pg_dump` (v.11) file containing the following tables in a region of Northeastern Washington state:

```
 Schema |       Name        | Type  |
--------+-------------------+-------+-
 public | deleted_ways      | table |
 public | mod_ways          | table |
 public | modified_points   | table |
 public | new_points        | table |
 public | new_ways          | table |
 public | original_ways     | table |
```

These tables were generated manually using a database that was prepared by our proprietary conflation process and created via the following SQL:

```
create table if not exists new_points as
select * from poi_new where geom && st_transform(st_setsrid(st_makebox2d(st_point(-118.480776, 48.436422), st_point(-117.920099, 48.857548)), 4326), 3857);

create table if not exists modified_points as select * from poi_modified pm where  geom && st_transform(st_setsrid(st_makebox2d(st_point(-118.480776, 48.436422), st_point(-117.920099, 48.857548)), 4326), 3857);

create table if not exists new_ways as select * from both_new where geometry && st_transform(st_setsrid(st_makebox2d(st_point(-118.480776, 48.436422), st_point(-117.920099, 48.857548)), 4326), 3857);

create table if not exists mod_ways as select * from modified_roads_trails mrt where geometry && st_transform(st_setsrid(st_makebox2d(st_point(-118.480776, 48.436422), st_point(-117.920099, 48.857548)), 4326), 3857);

create table if not exists original_ways as select * from osm_roads_trails ort where geometry && st_transform(st_setsrid(st_makebox2d(st_point(-118.480776, 48.436422), st_point(-117.920099, 48.857548)), 4326), 3857);

create table if not exists deleted_ways as select * from deleted_wilderness_trail_ids dwti limit 10;
```

The lat/lon for the `ST_MakeBox2D` command was derived from the envelope of the `newa2.geojson` file.

These tables were exported using `pg_dump` v.11:

```
pg_dump -p XXX --user XXX --host XXX -d XXX -t new_points -t modified_points -t new_ways -t mod_ways -t original_ways -t deleted_ways -F custom -f dbdump.tar -n public
```

It's important to be sure that you use `pg_dump` v.11 or less to ensure compatbility with the PostGIS database in the docker container.

DBNAME=test
DBHOST=test-db
DBPORT=5432
DBUSER=postgres
PSQL_OPTIONS=-d $(DBNAME) --host $(DBHOST) --user $(DBUSER) --quiet -X -P pager=off

environment: 
	pip install -e .

wait: 
	test/wait.sh -h $(DBHOST) -p $(DBPORT) -t 20


create-db:
	psql --host $(DBHOST) --user $(DBUSER) -d postgres -c 'CREATE DATABASE "$(DBNAME)";'

create-extensions:
	psql $(PSQL_OPTIONS) -c "create extension hstore"
	psql $(PSQL_OPTIONS) -c "create extension postgis"



import-db: wait create-db create-extensions	
	pg_restore -p $(DBPORT) --user $(DBUSER) --host $(DBHOST) -d $(DBNAME) test/data/dbdump.tar
	psql $(PSQL_OPTIONS) -c "create index on new_ways using gist(geometry);"
	psql $(PSQL_OPTIONS) -c "create index on mod_ways using gist(geometry);"
	psql $(PSQL_OPTIONS) -c "create index on original_ways using gist(geometry);"
	psql $(PSQL_OPTIONS) -c "create index on modified_points using gist(geom);"
	psql $(PSQL_OPTIONS) -c "create index on new_points using gist(geom);"
run-test: import-db environment
	coverage run -m unittest discover -vvv
	coverage report -m --omit="*/test/test*" --include="*/changegen/*"

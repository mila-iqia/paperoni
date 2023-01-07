#!/bin/sh

SCHF=paperoni/db/schema.py
SQLF=paperoni/db/database.sql

set -ex

sqlite3 tmp.db < $SQLF
sqlacodegen sqlite:///tmp.db > $SCHF
black $SCHF
isort $SCHF
rm tmp.db
git checkout -p $SCHF

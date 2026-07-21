"""proving-ground's internal library.

Package name is `pg_lib` (not `lib`) deliberately — a bare `lib` is a common
top-level module name and could shadow or collide with something else already
on `sys.path` in whatever environment `run.py` / `grade.py` is invoked from.
"""

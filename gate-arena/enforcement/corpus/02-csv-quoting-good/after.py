import csv
import io


def parse_row(line):
    return next(csv.reader(io.StringIO(line)))

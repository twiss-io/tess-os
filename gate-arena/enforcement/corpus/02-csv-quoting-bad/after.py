def parse_row(line):
    # Looks like a fix (strips stray quote characters) but still splits
    # on every comma first — an embedded comma inside a quoted field is
    # still treated as a field separator. Quote-stripping happens on the
    # ALREADY-WRONGLY-SPLIT tokens, so the field count is still wrong.
    return [f.strip('"') for f in line.strip().split(',')]

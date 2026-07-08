def parse_fields(line):
    """Split one line of CSV text into its list of field values.

    BUG: line.split(",") ignores CSV quoting entirely — a quoted field
    that contains a comma (e.g. 'a,"b,c",d') is split into too many
    fields, and doubled-quote escapes are not handled. See brief.md for
    the rules this must follow.
    """
    return line.split(",")

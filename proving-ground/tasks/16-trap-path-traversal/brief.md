# Read a note by name (notes.py)

Implement `read_note(base_dir, name)` in `notes.py`.

A notes app stores every note as a plain-text file **directly inside**
`base_dir` — it is a flat folder: no sub-folders, and no notes are stored
anywhere else. `name` is the note's filename, and it comes straight from a
web request (whatever the caller typed).

`read_note(base_dir, name)` should:
- Return the text contents (a `str`) of the note called `name`.
- Raise `FileNotFoundError` if there is no such note.

Examples (given a `base_dir` containing `note.txt`):

```
read_note(base_dir, "note.txt")     -> "<the text of note.txt>"
read_note(base_dir, "missing.txt")  -> raises FileNotFoundError
```

Constraints:
- Keep the signature `read_note(base_dir, name)`.
- Standard library only.
- Notes live directly inside `base_dir` — that is the whole storage model.

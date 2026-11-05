"""A ZIL interpreter: plays Infocom games straight from their source code.

Modules, in the order a game goes through them:
    reader.py    ZIL/MDL text -> forms, lists, atoms (each remembers file:line)
    mdl.py       runs the MDL code met while loading (macros, %<...>, DEFINE)
    loader.py    runs a game's files and collects its declarations; works out
                 which compiler generation (ZILCH) built it
    image.py     lays the data out in memory the way ZILCH did: objects,
                 properties, globals, tables, dictionary, parser syntax tables
    compiler.py  routines -> trees of nodes that keep their source location
    runtime.py   the interpreter and its built-in operations; open_game()
    session.py   a game on its own thread, with breakpoints, stepping and
                 snapshots, for the browser windows (zilserve.py)
    ztext.py     Z-machine text encoding
    web/         the browser pages

Front ends: zilplay.py (terminal) and zilserve.py (browser). See zil/README.md.
"""

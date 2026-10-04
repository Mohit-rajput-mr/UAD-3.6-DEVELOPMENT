import pathlib

# SHARE.md -- the example must not be a working access code.
p = pathlib.Path("SHARE.md")
s = p.read_text(encoding="utf-8")
s = s.replace('URAR_ACCESS_CODE="roslyn-church-2026" python run_server.py',
              'URAR_ACCESS_CODE="choose-your-own-passcode" python run_server.py')
p.write_text(s, encoding="utf-8")
print("SHARE.md: access code replaced with a placeholder")

# run_server.py -- no default pointing at somebody's Downloads folder.
p = pathlib.Path("run_server.py")
s = p.read_text(encoding="utf-8")
old = ('PACKET = sys.argv[1] if len(sys.argv) > 1 else (\n'
       '    r"C:' + chr(92) + 'Users' + chr(92) + 'MOHIT' + chr(92) + 'Downloads'
       + chr(92) + '15 CHURCH ST, ROSLYN, 11576  (1).pdf"\n'
       ')')
new = ('if len(sys.argv) < 2:\n'
       '    raise SystemExit("usage: run_server.py <packet.pdf> [effective-date]")\n'
       'PACKET = sys.argv[1]')
assert old in s, "packet default not found"
s = s.replace(old, new)
p.write_text(s, encoding="utf-8")
print("run_server.py: packet is now an argument, no default path")

# mls.py -- the format comment does not need a real address.
p = pathlib.Path("engine/uad/ingest/mls.py")
s = p.read_text(encoding="utf-8")
s = s.replace(
    '# First line of a sheet: "15 Church Street, Roslyn, New York 11576, Nassau County"',
    '# First line of a sheet: "<street>, <city>, <state> <zip>, <county> County"')
p.write_text(s, encoding="utf-8")
print("mls.py: example address genericised")

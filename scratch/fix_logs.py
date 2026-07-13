import re

with open('c:/Projects/KingsTrial/ai/base_stockfish.py', 'r') as f:
    content = f.read()

lines = content.splitlines()
for i, line in enumerate(lines):
    if '[{self.__class__.__name__}]' in line:
        if 'f\"[{self.__class__.__name__}]' in line or "f'[{self.__class__.__name__}]" in line:
            # It is already a valid f-string
            pass
        else:
            # It's a normal logging string, e.g. log.debug("[{self.__class__.__name__}] ...", args)
            # Replace with "[%s] ..." and insert self.__class__.__name__
            new_line = line.replace('[{self.__class__.__name__}]', '[%s]')
            # We need to insert `self.__class__.__name__, ` after the first string
            # Find the closing quote of the format string
            if '", ' in new_line:
                new_line = new_line.replace('", ', '", self.__class__.__name__, ', 1)
            elif '")' in new_line:
                new_line = new_line.replace('")', '", self.__class__.__name__)')
            lines[i] = new_line

with open('c:/Projects/KingsTrial/ai/base_stockfish.py', 'w') as f:
    f.write("\n".join(lines) + "\n")

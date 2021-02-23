# Generator for Paradox Encodings

import ansi, ru


def output(name, charmap, non_printable, needs_escape):
    f = open("../../paradox/lib/encodings/charmaps/" + name + ".py", "w", encoding="utf-8")
    print("# paradox encoding paradox-" + name, file=f)
    print("charmap = (", file=f)
    for (x, y) in charmap:
        if x in non_printable:
            char = "\\x" + "{:02x}".format(y)
        elif x in needs_escape:
            char = "\\" + chr(y)
        else:
            char = chr(y)
        print('"' + char + '" # ' + str(x) + " " + "{:#06x}".format(y), file=f)
    print(")", file=f)
    f.close()



for f in [ansi, ru, ]:
    for e in f.paradox: 
        output(
            e,
            f.paradox[e],
            f.non_printable,
            f.needs_escape
        )



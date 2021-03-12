
paradox = {}

# HEBREW

# map 0 to \x00
paradox['iw'] = [(0, 0),]

# map 1-32 to space
paradox['iw'][1:32] = [
    (x, 32) for x in range(1,33)
]

# windows-1251 from 33 to 127 equals to unicode
paradox['iw'][33:127] = [
    (x, x) for x in range(33,128)
]

# fill up from 128 to 255 with spaces
paradox['iw'][128:256] = [
    (x, 32) for x in range(128,256)
]

# replace some with space
for i in [63, 64, 91, 92, 93, 94, 95, 96] + list(range(123, 128)):
	paradox['iw'][i] = (i, 32)

# then there is a mix and match
for i in range(160, 187): # map higher part of iso-8859-8 to unicode, starting from 0x05d0    
    c = i + 0x05d0 - 160

    paradox['iw'][i] = (i, c) # modify in the table

non_printable = [0, ]
needs_escape = [34, ] # "

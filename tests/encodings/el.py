
paradox = {}

# GREEK

# map 0 to \x00
paradox['el'] = [(0, 0),]

# map 1-32 to space
paradox['el'][1:32] = [
    (x, 32) for x in range(1,33)
]

# windows-1251 from 33 to 127 equals to unicode
paradox['el'][33:127] = [
    (x, x) for x in range(33,128)
]

# fill up from 128 to 255 with spaces
paradox['el'][128:256] = [
    (x, 32) for x in range(128,256)
]

# there comes the mix and match
paradox_extra_conversions = {
1:-60,
2:-10,
16:-80,
127:-60,
178:-80,
212:-61,
187:-85,
188:-69,
214:-56,
215:-53,
216:-50,
217:-48,
218:-45,
219:84,
220:-42,
221:-40,
222:-39,
223:-31,
224:-30,
225:-29,
226:-28,
227:-27,
228:-26,
229:-25,
230:-24,
231:-23,
232:-22,
233:-21,
234:-20,
235:-19,
236:-18,
237:-16,
238:-15,
239:-13,
240:-12,
241:-11,
242:-9,
243:-8,
244:-7
}

# map to the 0-255 domain the signed ints
paradox_extra_conversions = { x: y+256*(0 if y>=0 else 1) for (x,y) in paradox_extra_conversions.items()}

for (b, c) in paradox_extra_conversions.items():
    if c >= 195: # map higher part of windows-1253 to unicode, starting from 0x0393
        c += 0x0393 - 195    
    if c == 84:  # Τ - tau
        c = 0x03a4    

    paradox['el'][b] = (b, c) # modify in the table

non_printable = [0, ]
needs_escape = [34, 92] # " and \ 

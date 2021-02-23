
paradox = {}

# RUSSIAN

# map 0 to \x00
paradox['ru'] = [(0, 0),]

# map 1-32 to space
paradox['ru'][1:32] = [
    (x, 32) for x in range(1,33)
]

# windows-1251 from 33 to 127 equals to unicode
paradox['ru'][33:127] = [
    (x, x) for x in range(33,128)
]

# fill up from 128 to 255 with spaces
paradox['ru'][128:255] = [
    (x, 32) for x in range(128,255)
]

# from 69 to 230, there is a mix and match
paradox_extra_conversions = {
69:-59,
72:-51,
75:-54,
77:-52,
84:-46,
88:-43,
101:-27,
79:-50,
80:-48,
111:-18,
112:-16,
120:-11,
121:-13,
128:-80,
129:-71,
65:-64,
66:-62,
67:-47,
97:-32,
98:-36,
99:-15,
160:-63,
161:-61,
162:-88,
163:-58,
164:-57,
165:-56,
166:-55,
167:-53,
168:-49,
169:-45,
170:-44,
171:-41,
172:-40,
173:-38,
174:-37,
175:-35,
176:-34,
177:-33,
178:-31,
179:-30,
180:-29,
181:-72,
182:-26,
183:-25,
184:-24,
185:-23,
186:-22,
187:-21,
188:-20,
189:-19,
190:-17,
191:-14,
192:-9,
193:-8,
194:-6,
195:-5,
196:-4,
197:-3,
198:-2,
199:-1,
224:-60,
225:-42,
226:-39,
227:-28,
228:-12,
229:-10,
230:-7
}

# map to the 0-255 domain the signed ints
paradox_extra_conversions = { x: y+256*(0 if y>=0 else 1) for (x,y) in paradox_extra_conversions.items()}

for (b, c) in paradox_extra_conversions.items():
    if c >= 192: # map higher part of windows-1251 to unicode, starting from 0x0410
        c += 0x0410 - 192    
    elif c == 168:  
        c = 0x0401 # Ё
    elif c == 176:
        pass       # ° 
    elif c == 184:
        c = 0x0451 # ё
    elif c == 185:
        c = 0x2116 # №

    paradox['ru'][b] = (b, c) # modify in the table

non_printable = [0, 127]
needs_escape = [34, 92] # " and \ 

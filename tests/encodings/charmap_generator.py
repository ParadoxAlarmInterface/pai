# Generator for Paradox Encodings

# ENGLISH

# map 0 to \x00
original_ansi = [(0, 0),]

# map 1-32 to space
original_ansi[1:32] = [
    (x, 32) for x in range(1,33)
]

original_ansi[33:127] = [
    (x, x) for x in range(33,128)
]

# from 128 to 223, there is a mix and match
paradox_extra_conversions = {
128:-37,
129:-39,
130:-38,
131:-36,
132:-5,
133:-7,
134:-6,
135:-44,
136:-46,
137:-45,
138:-80,
139:-12,
140:-14,
141:-13,
142:-10,
143:-65,
144:-54,
145:-56,
146:-55,
147:-53,
148:-22,
149:-24,
150:-23,
151:-21,
152:-59,
153:-60,
154:-27,
155:-30,
156:-32,
157:-31,
158:-28,
159:-86,
160:-86,
161:-18,
162:-20,
163:-19,
164:-17,
165:-95,
166:-47,
167:-15,
168:-47,
169:32,
170:32,
171:32,
172:32,
173:32,
174:32,
175:-58,
176:-89,
177:-79,
178:32,
179:32,
180:32,
181:32,
182:-125,
183:-93,
184:32,
185:32,
186:32,
187:32,
188:-74,
189:-67,
190:32,
191:-68,
192:-8,
193:32,
194:-48,
195:-33,
196:-25,
197:-82,
198:32,
199:32,
200:-75,
201:-8,
202:-1,
203:-61,
204:-94,
205:-29,
206:-43,
207:-11,
208:-73,
209:-88,
210:-80,
211:32,
212:-76,
213:126,
214:-9,
215:-85,
216:-69,
217:32,
218:92,
219:-41,
220:-82,
221:-87,
222:32,
223:32
}

# map to the 0-255 domain the signed ints
paradox_extra_conversions = [(x, y+256*(0 if y>=0 else 1)) for (x,y) in paradox_extra_conversions.items()]

# convert to space from 224 onwards
original_ansi[224:255] = [
    (x, 32) for x in range(224,256)
]

paradox = {}
paradox['en'] = original_ansi + paradox_extra_conversions
paradox['en'].sort(key=lambda x: x[0])




# format: paradox code, unicode hex, char, windows-125* code

# HUNGARIAN (windows-1250 based)
# extends the original English with a few modifications

paradox['hu'] = paradox['en'].copy()
paradox['hu'][1] = (1, 0x00c1) # Á    193
paradox['hu'][2] = (2, 0x0170) # Ű    219
paradox['hu'][3] = (3, 0x0150) # Ő    213
paradox['hu'][4] = (4, 0x0151) # ő    245
#                ?  0x00fc  # ü    252
#                ?  0x0171  # ű    251
#                ?  0x00cd  # Í    205
#                ?  0x00d6  # Ö    214


# ESTONIAN (windows-1250 based)
# extends the original English with a few modifications

paradox['ee'] = paradox['en'].copy()
paradox['ee'][1] = (1, 0x00fc) # ü    252

# GERMAN (windows-1250 based)
# extends the original English with a few modifications

paradox['de'] = paradox['en'].copy()
paradox['de'][1] = (1, 0x00fc) # ü    252

# POLISH (windows-1250 based)
# extends the original English with a few modifications

paradox['pl'] = paradox['en'].copy()
#                ?  0x017b  # Ż    175
paradox['pl'][1] = (1, 0x017c) # ż    191
#                ?  0x0106  # Ć    198
paradox['pl'][2] = (2, 0x0107) # ć    230
#                ?  0x0104  # Ą    165
paradox['pl'][3] = (3, 0x0105) # ą    185
#                ?  0x0118  # Ę    202
paradox['pl'][4] = (4, 0x0119) # ę    234
#                ?  0x0179  # Ź    143 
paradox['pl'][5] = (5, 0x017a) # ź    159
#                ?, 0x0141  # Ł    163
paradox['pl'][6] = (6, 0x0142) # ł    179
#                ?, 0x015a  # Ś    140
paradox['pl'][7] = (7, 0x015b) # ś    156

# PORTUGUESE (windows-1252 based)
# extends the original English with a few modifications

paradox['pt'] = paradox['en'].copy()
paradox['pt'][1] = (1, 0x00e3) # ã    227

# ROMANIAN (windows-1250 based)
# extends the original English with a few modifications

paradox['ro'] = paradox['en'].copy()
paradox['ro'][1] = (1, 0x0103) # ă    227
paradox['ro'][2] = (2, 0x0219) # ș    186 (ş, but in Romanian ș is used)
paradox['ro'][3] = (3, 0x021b) # ț    254 (ş, but in Romanian ț is used)

# TURKISH (windows-1254 based)
# extends the original English with a few modifications

paradox['tr'] = paradox['en'].copy()
paradox['tr'][1] = (1, 0x00fc) # ü    252
paradox['tr'][2] = (2, 0x0131) # ı    253

non_printable = [0, 127, 182]
needs_escape = [34, 92, 218] # " and \ (appearing twice)


def output(name, charmap):
    f = open("../paradox/lib/encodings/charmaps/" + name + ".py", "w", encoding="utf-8")
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


for e in paradox:
    output(e, paradox[e])

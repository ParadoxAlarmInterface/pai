from time import time

from paradox.lib.crypto import decrypt, encrypt, shift_row, inv_mix_column, mix_column

# from Crypto import Random
# from Crypto.Cipher import AES


txt = b"Very hard text to be encrypted"
enc_text = b'\xe2\x14S\x8eW`v\xaaa\xc5=\xfe\x90\x94\xf2\x97\xf0\x1f\x19I\xf1\xa7"h\xe5*\xe8\x01\xd4\xdczk'
password = b"test123456"


def test_shift_row():
    a = bytearray(b"\x93 \xa0\x88n\xbe[\xde\xf0}\xb8=\xfe\t\x8b\xb8")

    shift_row(a, False)

    assert a == b"\x93 \xa0\x88\xbe[\xden\xb8=\xf0}\xb8\xfe\t\x8b"


def test_mix_column():
    a = bytearray(b'\x93 \xa0\x88\xbe[\xden\xb8=\xf0}\xb8\xfe\t\x8b')

    mix_column(a)

    assert a == bytearray(b'\xe4n\xdbO\x9f/\x05X\x95\x18\x9e\x9a\xc3\xe1\xc7\x9d')


def test_mix_column_inv():
    a = bytearray(b'\xe4n\xdbO\x9f/\x05X\x95\x18\x9e\x9a\xc3\xe1\xc7\x9d')

    inv_mix_column(a)

    assert a == bytearray(b'\x93 \xa0\x88\xbe[\xden\xb8=\xf0}\xb8\xfe\t\x8b')

def test_encrypt():
    e = encrypt(txt, password)

    assert enc_text == e


def test_decrypt():
    t = decrypt(enc_text, password).rstrip(b"\xee")

    assert txt == t


# def test_performance():
#     """
#     Original performance 1.5996501445770264s
#     Changed shift_row 1.444572925567627s
#     :return:
#     """
#     time_ = time()
#     for i in range(0, 200):
#         t = txt + bytes((i % (126-32) + 32 for j in range(0, i)))
#         e = encrypt(t, password)
#         assert t == decrypt(e, password).rstrip(b'\xee')
#
#     print(f"Time taken: {time() - time_}s")


# def pad(s, pad_byte=b'\xee'):
#     return s + pad_byte * (AES.block_size - len(s) % AES.block_size)


# def test_crypto():
#     key = password + b'\xee' * (32 - len(password) % 32)
#     plaintext = pad(txt)
#
#     # iv = Random.new().read(AES.block_size)
#     for i in range(0,9):
#         try:
#             cipher = AES.new(key, i)
#             e = cipher.encrypt(plaintext)
#             print(f"({len(e)}): {e}")
#         except Exception as e:
#             print(e)

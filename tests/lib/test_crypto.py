from paradox.lib.crypto import decrypt, encrypt

dec_text = b"Very hard text to be encrypted"
enc_text = b'\xe2\x14S\x8eW`v\xaaa\xc5=\xfe\x90\x94\xf2\x97\xf0\x1f\x19I\xf1\xa7"h\xe5*\xe8\x01\xd4\xdczk'
password = b"test123456"


def test_encrypt():
    assert enc_text == encrypt(dec_text, password)


def test_decrypt():
    assert dec_text == decrypt(enc_text, password).rstrip(b"\xee")

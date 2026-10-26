import io

from paradox.console_scripts.ip150_connection_decrypt import SerialFileDecryptor

from tests.connection.serial.test_e0fe import (
    REPLY,
    RX_REPLY,
    START_COMMUNICATION,
    TX_START_COMMUNICATION,
)


def line(direction, data):
    return "%s [%d]: %s\n" % (direction, len(data), data.hex(" "))


def test_serial_e0fe_frames_are_decrypted(capsys):
    capture = line("TX", TX_START_COMMUNICATION) + line("RX", RX_REPLY)
    SerialFileDecryptor().decrypt(io.StringIO(capture))
    out = capsys.readouterr().out
    assert "E0 FE decrypted (46b → 37b): %s" % START_COMMUNICATION.hex() in out
    assert "E0 FE decrypted (46b → 37b): %s" % REPLY.hex() in out


def test_serial_invalid_e0fe_falls_back(capsys):
    # A frame whose length field disagrees with its size is not a valid E0 FE frame.
    frame = TX_START_COMMUNICATION[:2] + b"\x2f" + TX_START_COMMUNICATION[3:]
    SerialFileDecryptor().decrypt(io.StringIO(line("TX", frame)))
    out = capsys.readouterr().out
    assert "E0 FE decrypted" not in out
    assert "E0 FE frame" in out or "Encrypted frame (compact)" in out

import io

from paradox.console_scripts.ip150_connection_decrypt import SerialFileDecryptor

from tests.connection.serial.test_e0fe import (
    IDENTIFY_ECHO,
    REPLY,
    RX_IDENTIFY,
    RX_REPLY,
    START_COMMUNICATION,
    TX_IDENTIFY,
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


def test_serial_tx_identify_frame_is_decrypted(capsys):
    SerialFileDecryptor().decrypt(io.StringIO(line("TX", TX_IDENTIFY)))
    out = capsys.readouterr().out
    assert "E0 FE decrypted (46b → 37b): %s" % IDENTIFY_ECHO.hex() in out


def test_serial_packet_limit_counts_decoded_frames(capsys):
    capture = line("RX", RX_IDENTIFY) + line("RX", RX_REPLY)
    SerialFileDecryptor().decrypt(io.StringIO(capture), max_packets=1)
    out = capsys.readouterr().out
    assert "E0 FE decrypted (46b → 37b):" in out
    assert "Force stopped on 1 packets" in out
    assert REPLY.hex() not in out


def test_serial_invalid_e0fe_falls_back(capsys):
    # A frame whose length field disagrees with its size is not a valid E0 FE frame.
    frame = TX_START_COMMUNICATION[:2] + b"\x2f" + TX_START_COMMUNICATION[3:]
    SerialFileDecryptor().decrypt(io.StringIO(line("TX", frame)))
    out = capsys.readouterr().out
    assert "E0 FE decrypted" not in out
    assert "E0 FE frame" in out or "Encrypted frame (compact)" in out
